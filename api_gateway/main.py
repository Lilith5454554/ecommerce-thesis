from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os

# ==================== 服务地址配置 ====================
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user_service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product_service:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order_service:8000")

# ==================== FastAPI 应用 ====================
app = FastAPI(title="API网关", description="电商平台统一入口")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {"service": "API网关", "status": "running"}


@app.get("/health")
async def health():
    # 检查所有下游服务状态
    services_status = {}

    async with httpx.AsyncClient() as client:
        # 检查用户服务
        try:
            user_resp = await client.get(f"{USER_SERVICE_URL}/health", timeout=3.0)
            services_status["user_service"] = "healthy" if user_resp.status_code == 200 else "unhealthy"
        except:
            services_status["user_service"] = "unreachable"

        # 检查商品服务
        try:
            product_resp = await client.get(f"{PRODUCT_SERVICE_URL}/health", timeout=3.0)
            services_status["product_service"] = "healthy" if product_resp.status_code == 200 else "unhealthy"
        except:
            services_status["product_service"] = "unreachable"

        # 检查订单服务
        try:
            order_resp = await client.get(f"{ORDER_SERVICE_URL}/health", timeout=3.0)
            services_status["order_service"] = "healthy" if order_resp.status_code == 200 else "unhealthy"
        except:
            services_status["order_service"] = "unreachable"

    return {
        "gateway": "healthy",
        "services": services_status
    }


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
            raise HTTPException(status_code=504, detail="服务超时")
        except httpx.ConnectionError:
            raise HTTPException(status_code=503, detail="服务不可用")
        except Exception as e:
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
