# user_service/main.py
from fastapi import FastAPI, HTTPException, Response, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
import os
from sqlalchemy.orm import Session

# ==================== 关键：统一从models导入所有数据库相关 ====================
from user_service.models import User, get_db, init_db, SessionLocal
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt

# ==================== Prometheus 监控指标（保持原有）====================
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

TOTAL_USERS = Gauge(
    'user_service_total_users',
    'Total number of users in the system'
)

PROCESS_MEMORY = Gauge(
    'process_memory_bytes',
    'Process memory usage in bytes'
)

PROCESS_CPU = Gauge(
    'process_cpu_seconds_total',
    'Process CPU time in seconds'
)

# ==================== JWT配置 ====================
SECRET_KEY = os.getenv("SECRET_KEY", "ecommerce-dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ==================== FastAPI应用 ====================
app = FastAPI(title="User Service", description="用户服务")


# ==================== 中间件 ====================
@app.middleware("http")
async def monitor_requests(request, call_next):
    ACTIVE_REQUESTS.inc()
    start_time = time.time()

    try:
        response = await call_next(request)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        return response
    except Exception as e:
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=500
        ).inc()
        raise
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        ACTIVE_REQUESTS.dec()


# ==================== 后台任务 ====================
@app.on_event("startup")
async def startup_event():
    init_db()
    import asyncio
    asyncio.create_task(update_system_metrics())


async def update_system_metrics():
    import asyncio
    process = psutil.Process(os.getpid())
    while True:
        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            TOTAL_USERS.set(user_count)
        finally:
            db.close()

        memory_info = process.memory_info()
        PROCESS_MEMORY.set(memory_info.rss)
        PROCESS_CPU.set(process.cpu_percent() / 100.0)
        await asyncio.sleep(15)


# ==================== Prometheus端点 ====================
@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 数据模型 ====================
class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ==================== JWT工具函数 ====================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ==================== API端点 ====================
@app.get("/")
async def root():
    return {
        "service": "User Service",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/metrics",
            "/users/",
            "/users/{id}",
            "/auth/login"
        ]
    }


@app.get("/health")
async def health_check():
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "service": "user_service",
        "database": db_status
    }


@app.get("/users/", response_model=List[UserResponse])
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "email": u.email} for u in users]


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "username": user.username, "email": user.email}


@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    existing_email = db.query(User).filter(User.email == user.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    db_user = User(
        id=user_id,
        username=user.username,
        email=user.email,
        password_hash=get_password_hash(user.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return {"id": db_user.id, "username": db_user.username, "email": db_user.email}


@app.post("/auth/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "username": user.username},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.delete("/users/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_update: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.username:
        user.username = user_update.username
    if user_update.email:
        user.email = user_update.email
    if user_update.password:
        user.password_hash = get_password_hash(user_update.password)

    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "email": user.email}