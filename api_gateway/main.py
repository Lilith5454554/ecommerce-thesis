from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response
import httpx
import os
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
from typing import Dict

# ==================== 服务地址配置 ====================
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user_service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product_service:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order_service:8000")

# ==================== 监控指标定义 ====================

# 1. 请求计数指标（按服务、方法、状态码细分）
REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total number of requests processed by gateway',
    ['service', 'method', 'endpoint', 'status_code']
)

# 2. 请求延迟指标（按服务、方法细分）
REQUEST_LATENCY = Histogram(
    'gateway_request_duration_seconds',
    'Request latency in seconds',
    ['service', 'method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

# 3. 下游服务健康状态指标
SERVICE_HEALTH = Gauge(
    'gateway_downstream_service_health',
    'Health status of downstream services (1=healthy, 0=unhealthy)',
    ['service']
)

# 4. 活跃请求数指标
ACTIVE_REQUESTS = Gauge(
    'gateway_active_requests',
    'Number of active requests being processed'
)

# 5. 错误率指标（按服务细分）
ERROR_COUNT = Counter(
    'gateway_errors_total',
    'Total number of errors by type',
    ['service', 'error_type']
)

# 6. 网关系统资源指标
CPU_USAGE = Gauge('gateway_cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('gateway_memory_usage_bytes', 'Memory usage in bytes')
MEMORY_PERCENT = Gauge('gateway_memory_usage_percent', 'Memory usage percentage')

# ==================== FastAPI 应用 ====================
app = FastAPI(title="API网关", description="电商平台统一入口")


# ==================== 中间件：监控所有请求 ====================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    """监控中间件：记录所有请求的指标"""

    # 增加活跃请求计数
    ACTIVE_REQUESTS.inc()

    # 记录开始时间
    start_time = time.time()

    # 获取请求信息
    path = request.url.path
    method = request.method

    # 提取服务名（用于指标标签）
    service = "unknown"
    if path.startswith("/users"):
        service = "user_service"
    elif path.startswith("/products"):
        service = "product_service"
    elif path.startswith("/orders"):
        service = "order_service"
    elif path.startswith("/api"):
        path_parts = path.split("/")
        if len(path_parts) > 2:
            service = path_parts[2]

    try:
        # 处理请求
        response = await call_next(request)

        # 记录请求延迟
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            service=service,
            method=method,
            endpoint=path
        ).observe(duration)

        # 记录请求计数
        REQUEST_COUNT.labels(
            service=service,
            method=method,
            endpoint=path,
            status_code=response.status_code
        ).inc()

        # 记录错误（4xx和5xx）
        if response.status_code >= 400:
            ERROR_COUNT.labels(
                service=service,
                error_type=f"{response.status_code}"
            ).inc()

        return response

    except Exception as e:
        # 记录异常错误
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
        # 减少活跃请求计数
        ACTIVE_REQUESTS.dec()


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {"service": "API网关", "status": "running"}


@app.get("/health")
async def health():
    """健康检查，同时更新下游服务健康状态指标"""
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


# ==================== 指标暴露端点 ====================
@app.get("/metrics")
async def metrics():
    """暴露 Prometheus 指标"""
    # 更新系统资源指标
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()

    CPU_USAGE.set(cpu_percent)
    MEMORY_USAGE.set(memory.used)
    MEMORY_PERCENT.set(memory.percent)

    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 路由转发函数 ====================
async def proxy_request(service_url: str, path: str, request: Request):
    """将请求转发到对应的微服务"""
    url = f"{service_url}{path}"

    # 获取请求方法、头部、参数
    method = request.method
    headers = dict(request.headers)
    # 移除不需要转发的头部
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()
    params = dict(request.query_params)

    async with httpx.AsyncClient() as client:
        try:
            # 转发请求
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body if body else None,
                params=params,
                timeout=30.0
            )

            # 返回下游服务的响应
            return JSONResponse(
                content=resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
                status_code=resp.status_code,
                headers=dict(resp.headers)
            )
        except httpx.TimeoutException:
            ERROR_COUNT.labels(service=service_url.split("/")[2].split(":")[0], error_type="timeout").inc()
            raise HTTPException(status_code=504, detail="服务超时")
        except httpx.ConnectionError:
            ERROR_COUNT.labels(service=service_url.split("/")[2].split(":")[0], error_type="connection").inc()
            raise HTTPException(status_code=503, detail="服务不可用")
        except Exception as e:
            ERROR_COUNT.labels(service=service_url.split("/")[2].split(":")[0], error_type="internal").inc()
            raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


# ==================== 用户服务路由 ====================
@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def users_proxy(path: str, request: Request):
    """转发用户服务请求"""
    full_path = f"/{path}" if path else "/"
    return await proxy_request(USER_SERVICE_URL, full_path, request)


# ==================== 商品服务路由 ====================
@app.api_route("/products/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def products_proxy(path: str, request: Request):
    """转发商品服务请求"""
    full_path = f"/{path}" if path else "/"
    return await proxy_request(PRODUCT_SERVICE_URL, full_path, request)


# ==================== 订单服务路由 ====================
@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def orders_proxy(path: str, request: Request):
    """转发订单服务请求"""
    full_path = f"/{path}" if path else "/"
    return await proxy_request(ORDER_SERVICE_URL, full_path, request)


# ==================== 统一API入口（可选）====================
@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_proxy(service: str, path: str, request: Request):
    """统一的API入口：/api/{service}/{path}"""
    service_urls = {
        "users": USER_SERVICE_URL,
        "products": PRODUCT_SERVICE_URL,
        "orders": ORDER_SERVICE_URL
    }

    if service not in service_urls:
        raise HTTPException(status_code=404, detail=f"未知的服务: {service}")

    full_path = f"/{path}" if path else "/"
    return await proxy_request(service_urls[service], full_path, request)


# ==================== 自定义监控端点 ====================
@app.get("/monitoring/status")
async def monitoring_status():
    """返回详细的监控状态"""
    return {
        "active_requests": ACTIVE_REQUESTS._value.get(),
        "services_health": {
            "user_service": SERVICE_HEALTH.labels(service="user_service")._value.get(),
            "product_service": SERVICE_HEALTH.labels(service="product_service")._value.get(),
            "order_service": SERVICE_HEALTH.labels(service="order_service")._value.get()
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": psutil.virtual_memory().used / 1024 / 1024 / 1024
        }
    }
