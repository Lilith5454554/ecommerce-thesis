# api_gateway/main.py
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse, Response
import httpx
import os
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
from typing import Dict, Optional

# ==================== 关键：JWT导入和配置 ====================
from jose import JWTError, jwt

# ==================== 配置 ====================
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user_service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product_service:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order_service:8000")

# 关键：与用户服务使用相同的SECRET_KEY（通过环境变量统一配置）
SECRET_KEY = os.getenv("SECRET_KEY", "ecommerce-dev-secret-key")
ALGORITHM = "HS256"

# ==================== Prometheus监控（保持原有）====================
REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total number of requests processed by gateway',
    ['service', 'method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'gateway_request_duration_seconds',
    'Request latency in seconds',
    ['service', 'method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

SERVICE_HEALTH = Gauge(
    'gateway_downstream_service_health',
    'Health status of downstream services (1=healthy, 0=unhealthy)',
    ['service']
)

ACTIVE_REQUESTS = Gauge(
    'gateway_active_requests',
    'Number of active requests being processed'
)

ERROR_COUNT = Counter(
    'gateway_errors_total',
    'Total number of errors by type',
    ['service', 'error_type']
)

CPU_USAGE = Gauge('gateway_cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('gateway_memory_usage_bytes', 'Memory usage in bytes')
MEMORY_PERCENT = Gauge('gateway_memory_usage_percent', 'Memory usage percentage')

# ==================== FastAPI应用 ====================
app = FastAPI(title="API网关", description="电商平台统一入口")


# ==================== 关键：JWT验证依赖 ====================
async def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """
    验证JWT令牌，返回用户ID
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==================== 中间件 ====================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    ACTIVE_REQUESTS.inc()
    start_time = time.time()

    path = request.url.path
    method = request.method

    service = "unknown"
    if path.startswith("/users"):
        service = "user_service"
    elif path.startswith("/products"):
        service = "product_service"
    elif path.startswith("/orders"):
        service = "order_service"

    try:
        response = await call_next(request)
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            service=service,
            method=method,
            endpoint=path
        ).observe(duration)
        REQUEST_COUNT.labels(
            service=service,
            method=method,
            endpoint=path,
            status_code=response.status_code
        ).inc()
        if response.status_code >= 400:
            ERROR_COUNT.labels(
                service=service,
                error_type=f"{response.status_code}"
            ).inc()
        return response
    except Exception as e:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            service=service,
            method=method,
            endpoint=path
        ).observe(duration)
        ERROR_COUNT.labels(
            service=service,
            error_type="exception"
        ).inc()
        raise
    finally:
        ACTIVE_REQUESTS.dec()


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {"service": "API网关", "status": "running"}


@app.get("/health")
async def health():
    services_status = {}
    async with httpx.AsyncClient() as client:
        # 检查用户服务
        try:
            user_resp = await client.get(f"{USER_SERVICE_URL}/health", timeout=3.0)
            user_healthy = user_resp.status_code == 200
            services_status["user_service"] = "healthy" if user_healthy else "unhealthy"
            SERVICE_HEALTH.labels(service="user_service").set(1 if user_healthy else 0)
        except:
            services_status["user_service"] = "unreachable"
            SERVICE_HEALTH.labels(service="user_service").set(0)

        # 检查商品服务
        try:
            product_resp = await client.get(f"{PRODUCT_SERVICE_URL}/health", timeout=3.0)
            product_healthy = product_resp.status_code == 200
            services_status["product_service"] = "healthy" if product_healthy else "unhealthy"
            SERVICE_HEALTH.labels(service="product_service").set(1 if product_healthy else 0)
        except:
            services_status["product_service"] = "unreachable"
            SERVICE_HEALTH.labels(service="product_service").set(0)

        # 检查订单服务
        try:
            order_resp = await client.get(f"{ORDER_SERVICE_URL}/health", timeout=3.0)
            order_healthy = order_resp.status_code == 200
            services_status["order_service"] = "healthy" if order_healthy else "unhealthy"
            SERVICE_HEALTH.labels(service="order_service").set(1 if order_healthy else 0)
        except:
            services_status["order_service"] = "unreachable"
            SERVICE_HEALTH.labels(service="order_service").set(0)

    return {
        "gateway": "healthy",
        "services": services_status
    }


# ==================== 监控端点 ====================
@app.get("/metrics")
async def metrics():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    CPU_USAGE.set(cpu_percent)
    MEMORY_USAGE.set(memory.used)
    MEMORY_PERCENT.set(memory.percent)
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 辅助函数：转发请求 ====================
async def proxy_request(
        service_url: str,
        path: str,
        request: Request,
        extra_headers: Optional[Dict[str, str]] = None
):
    url = f"{service_url}{path}"
    method = request.method
    headers = dict(request.headers)

    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("authorization", None)  # 不转发JWT，下游用X-User-ID

    if extra_headers:
        headers.update(extra_headers)

    body = await request.body()
    params = dict(request.query_params)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body if body else None,
                params=params,
                timeout=30.0
            )
            return JSONResponse(
                content=resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
                status_code=resp.status_code,
                headers=dict(resp.headers)
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="服务超时")
        except httpx.ConnectionError:
            raise HTTPException(status_code=503, detail="服务不可用")


# ==================== 路由（关键：订单路由需要JWT）====================

@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def users_proxy(path: str, request: Request):
    full_path = f"/{path}" if path else "/"
    return await proxy_request(USER_SERVICE_URL, full_path, request)


@app.api_route("/products/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def products_proxy(path: str, request: Request):
    full_path = f"/{path}" if path else "/"
    return await proxy_request(PRODUCT_SERVICE_URL, full_path, request)


# 关键：订单路由需要JWT验证
@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def orders_proxy(
        path: str,
        request: Request,
        user_id: str = Depends(verify_token)  # JWT验证
):
    full_path = f"/{path}" if path else "/"
    return await proxy_request(
        ORDER_SERVICE_URL,
        full_path,
        request,
        extra_headers={"X-User-ID": user_id}
    )


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_proxy(service: str, path: str, request: Request):
    service_urls = {
        "users": USER_SERVICE_URL,
        "products": PRODUCT_SERVICE_URL,
        "orders": ORDER_SERVICE_URL
    }
    if service not in service_urls:
        raise HTTPException(status_code=404, detail=f"未知的服务: {service}")
    full_path = f"/{path}" if path else "/"
    return await proxy_request(service_urls[service], full_path, request)


@app.get("/monitoring/status")
async def monitoring_status():
    return {
        "active_requests": ACTIVE_REQUESTS._value.get(),
        "services_health": {
            "user_service": SERVICE_HEALTH.labels(service="user_service")._value.get(),
            "product_service": SERVICE_HEALTH.labels(service="product_service")._value.get(),
            "order_service": SERVICE_HEALTH.labels(service="order_service")._value.get()
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }
    }