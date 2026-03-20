from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
import os

# ==================== Prometheus 监控指标定义 ====================

# 请求计数：记录每个端点的请求次数和状态
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# 请求延迟：记录每个端点的响应时间
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

# 活跃请求数：当前正在处理的请求数
ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# 业务指标：用户总数
TOTAL_USERS = Gauge(
    'user_service_total_users',
    'Total number of users in the system'
)

# 系统指标：Python进程资源使用
PROCESS_MEMORY = Gauge(
    'process_memory_bytes',
    'Process memory usage in bytes'
)

PROCESS_CPU = Gauge(
    'process_cpu_seconds_total',
    'Process CPU time in seconds'
)

app = FastAPI(title="User Service", description="用户服务")

# 内存数据库（临时存储）
users_db = {}


# ==================== 中间件：自动收集请求指标 ====================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    """监控中间件：自动记录请求数、延迟、活跃请求数"""
    # 活跃请求数 +1
    ACTIVE_REQUESTS.inc()

    # 记录开始时间
    start_time = time.time()

    # 处理请求
    try:
        response = await call_next(request)
        # 请求计数（成功）
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        return response
    except Exception as e:
        # 请求计数（异常）
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=500
        ).inc()
        raise e
    finally:
        # 记录请求延迟
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        # 活跃请求数 -1
        ACTIVE_REQUESTS.dec()


# ==================== 后台任务：定期更新系统指标 ====================
@app.on_event("startup")
async def startup_event():
    """启动时初始化指标"""
    import asyncio
    asyncio.create_task(update_system_metrics())


async def update_system_metrics():
    """每15秒更新一次系统指标"""
    import asyncio
    process = psutil.Process(os.getpid())

    while True:
        # 更新用户总数业务指标
        TOTAL_USERS.set(len(users_db))

        # 更新进程内存使用
        memory_info = process.memory_info()
        PROCESS_MEMORY.set(memory_info.rss)

        # 更新进程CPU时间
        PROCESS_CPU.set(process.cpu_percent() / 100.0)

        await asyncio.sleep(15)


# ==================== Prometheus 指标暴露端点 ====================
@app.get("/metrics")
async def get_metrics():
    """暴露 Prometheus 监控指标"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain"
    )


# 数据模型
class UserCreate(BaseModel):
    username: str
    email: str
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str


class User(UserResponse):
    password: Optional[str] = None


# ==================== API 端点 ====================
@app.get("/")
async def root():
    """根路径，返回服务信息"""
    return {
        "service": "User Service",
        "version": "1.0.0",
        "endpoints": [
            "/health - 健康检查",
            "/metrics - Prometheus监控指标",
            "/users/ - 获取所有用户",
            "/users/{id} - 获取单个用户",
            "/users/ - 创建用户 (POST)",
            "/users/{id} - 删除用户 (DELETE)",
            "/users/{id} - 更新用户 (PUT)"
        ]
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "user_service"}


@app.get("/users/", response_model=List[UserResponse])
async def get_users():
    """获取所有用户"""
    return list(users_db.values())


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """获取单个用户"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]


@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate):
    """创建新用户"""
    # 生成唯一ID
    user_id = str(uuid.uuid4())

    # 创建用户对象
    new_user = User(
        id=user_id,
        username=user.username,
        email=user.email,
        password=user.password
    )

    # 保存到数据库
    users_db[user_id] = new_user

    return new_user


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """删除用户"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    del users_db[user_id]
    return {"message": "User deleted successfully"}


@app.put("/users/{user_id}")
async def update_user(user_id: str, user_update: UserCreate):
    """更新用户信息"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]
    if user_update.username:
        user.username = user_update.username
    if user_update.email:
        user.email = user_update.email
    if user_update.password:
        user.password = user_update.password

    users_db[user_id] = user
    return user

