from fastapi import FastAPI, HTTPException, Response, Depends, status #web框架相关
from fastapi.responses import Response
from pydantic import BaseModel #数据验证
from typing import List, Optional#类型提示
import uuid #生成唯一id
import time #时间处理
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY #监控指标收集
import prometheus_client
import psutil #系统资源监控
import os
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import text
from passlib.context import CryptContext
# ==================== 关键：统一从models导入所有数据库相关 ====================
try:
    from user_service.models import User, get_db, init_db, SessionLocal
except ImportError:
    from models import User, get_db, init_db, SessionLocal #数据库模型
import bcrypt #密码加密
from datetime import datetime, timedelta #时间计算
from jose import JWTError, jwt #jwt令牌处理

# ==================== OpenTelemetry 链路追踪 ====================
import sys
sys.path.append('/app/monitoring')
try:
    from tracing import init_tracing
    TRACING_ENABLED = True
except ImportError:
    TRACING_ENABLED = False
    print("Tracing not available")
# ==================== 配置 bcrypt，设置截断策略（只定义一次，移到文件顶部）====================
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False  # 自动截断过长的密码
)

# ==================== 修复 Prometheus 指标重复注册 ====================
# 清除默认的 process collector，也就是重复的监控收集器,避免重复注册
try:
    REGISTRY.unregister(prometheus_client.ProcessCollector)
except KeyError:
    pass

# 清除其他可能重复的 collector
try:
    REGISTRY.unregister(prometheus_client.PlatformCollector)
except KeyError:
    pass


# ==================== Prometheus 监控指标（保持原有）====================
#统计HTTP请求总数（按方法、端点、状态码分类）
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

#记录请求延迟时间
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

#当前正在处理的请求数
ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

#系统中的用户总数
TOTAL_USERS = Gauge(
    'user_service_total_users',
    'Total number of users in the system'
)

#进程内存使用量
PROCESS_MEMORY = Gauge(
    'user_service_process_memory_bytes',
    'Process memory usage in bytes'
)

#进程CPU使用时间
PROCESS_CPU = Gauge(
    'user_service_process_cpu_seconds_total',
    'Process CPU time in seconds'
)

# ==================== JWT配置 ====================
SECRET_KEY = os.getenv("SECRET_KEY", "ecommerce-dev-secret-key")
ALGORITHM = "HS256" # 加密算法
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # Token有效期30分钟

# ==================== FastAPI应用 ====================
app = FastAPI(title="User Service", description="用户服务")

# ==================== 初始化链路追踪 ====================
if TRACING_ENABLED:
    init_tracing("user-service", app=app)


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
'''
startup_event（启动时执行）：
初始化数据库（创建表）
启动后台任务更新系统指标
'''
@app.on_event("startup")
async def startup_event():
    init_db()
    import asyncio
    asyncio.create_task(update_system_metrics())


'''
update_system_metrics（每15秒执行）：
从数据库查询用户总数
获取进程内存和CPU使用率
更新Prometheus指标
'''
async def update_system_metrics():
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
#监控指标。作用：暴露Prometheus格式的监控数据，供监控系统采集。
@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 数据模型 ====================
#定义API请求和响应的数据结构，自动进行数据验证。

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

# ==================== 密码加密配置 ====================

#使用bcrypt算法加密密码
def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    # 确保密码是字符串并编码
    password_bytes = str(password).encode('utf-8')
    # bcrypt 会自动处理长度，超过72字节会截断
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

#验证明文密码是否与哈希匹配
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    plain_bytes = str(plain_password).encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)

#创建包含用户信息的JWT访问令牌
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
#根路径。返回服务信息和可用端点列表。
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

#健康检查。检查服务和数据库状态，用于K8s健康探针。
@app.get("/health")
async def health_check():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "service": "user_service",
        "database": db_status
    }


#获取所有用户。返回所有用户列表（可能不安全，生产环境需要权限控制）。
@app.get("/users/", response_model=List[UserResponse])
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "email": u.email} for u in users]

#获取单个用户。根据ID查询用户信息，不存在返回404。
@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "username": user.username, "email": user.email}

'''
创建用户。流程：
检查用户名是否已存在
检查邮箱是否已存在
生成UUID作为用户ID
加密密码
保存到数据库
返回用户信息（不含密码）
'''
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

'''
用户登录。流程：
根据用户名查找用户
验证密码
生成JWT令牌（包含用户ID和用户名）
返回访问令牌
'''
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

#删除用户。根据ID删除用户，返回删除确认。
@app.delete("/users/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    # 确保返回包含 id 字段
    return {
        "id": user_id,
        "message": "User deleted successfully"
    }

#更新用户。更新用户信息（用户名、邮箱、密码），如果字段为空则保持原值。
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



