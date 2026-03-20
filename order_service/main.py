'''from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import httpx
import os

# ==================== 服务地址配置 ====================
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user_service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product_service:8000")


# ==================== 数据模型 ====================
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int


class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItemCreate]
    shipping_address: str


class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    price: float
    subtotal: float


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str  # pending, paid, shipped, completed, cancelled
    shipping_address: str
    items: List[OrderItemResponse]
    created_at: datetime


# ==================== 模拟数据库 ====================
orders_db = {}  # key: order_id, value: order_data
order_items_db = {}  # key: order_id, value: list of items
current_order_id = 1

# ==================== FastAPI 应用 ====================
app = FastAPI(title="订单服务", description="电商平台订单管理服务")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {"service": "订单服务", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ==================== 辅助函数 ====================
async def enrich_order_with_items(order_id: int, order: dict):
    """把订单项添加到订单里"""
    items = order_items_db.get(order_id, [])

    item_responses = []
    for item in items:
        item_responses.append({
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "quantity": item["quantity"],
            "price": item["price"],
            "subtotal": item["price"] * item["quantity"]
        })

    order_dict = dict(order)
    order_dict["items"] = item_responses
    return order_dict


# ==================== 订单接口 ====================

# 1. 创建订单
@app.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate):
    global current_order_id

    # 1. 验证用户是否存在（调用用户服务）
    async with httpx.AsyncClient() as client:
        try:
            user_response = await client.get(f"{USER_SERVICE_URL}/users/{order.user_id}")
            if user_response.status_code == 404:
                raise HTTPException(status_code=400, detail="用户不存在")
        except httpx.RequestError:
            # 服务不可用时，临时用模拟数据
            if order.user_id <= 0:
                raise HTTPException(status_code=400, detail="无效的用户ID")

    # 2. 获取商品信息、验证库存、计算总价
    total_amount = 0
    order_items = []

    async with httpx.AsyncClient() as client:
        for item in order.items:
            try:
                # 获取商品详情
                product_response = await client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
                if product_response.status_code == 404:
                    raise HTTPException(status_code=400, detail=f"商品 {item.product_id} 不存在")

                product = product_response.json()

                # 扣减库存
                stock_response = await client.post(
                    f"{PRODUCT_SERVICE_URL}/products/{item.product_id}/stock/decrease",
                    params={"quantity": item.quantity}
                )
                if stock_response.status_code == 400:
                    raise HTTPException(status_code=400, detail=f"商品 {product['name']} 库存不足")

                # 计算小计
                subtotal = product["price"] * item.quantity
                total_amount += subtotal

                order_items.append({
                    "product_id": item.product_id,
                    "product_name": product["name"],
                    "quantity": item.quantity,
                    "price": product["price"]
                })

            except httpx.RequestError:
                # 服务不可用时，用模拟数据
                mock_product = {
                    "id": item.product_id,
                    "name": f"模拟商品{item.product_id}",
                    "price": 99.9
                }
                subtotal = mock_product["price"] * item.quantity
                total_amount += subtotal
                order_items.append({
                    "product_id": item.product_id,
                    "product_name": mock_product["name"],
                    "quantity": item.quantity,
                    "price": mock_product["price"]
                })

    # 3. 创建订单记录
    new_order = {
        "id": current_order_id,
        "user_id": order.user_id,
        "total_amount": total_amount,
        "status": "pending",
        "shipping_address": order.shipping_address,
        "created_at": datetime.now()
    }

    orders_db[current_order_id] = new_order
    order_items_db[current_order_id] = order_items

    current_order_id += 1

    # 4. 返回完整订单信息
    return await enrich_order_with_items(current_order_id - 1, new_order)


# 2. 获取所有订单
@app.get("/orders", response_model=List[OrderResponse])
async def get_orders(user_id: Optional[int] = None, skip: int = 0, limit: int = 100):
    result = []

    for order_id, order in orders_db.items():
        if user_id and order["user_id"] != user_id:
            continue
        enriched = await enrich_order_with_items(order_id, order)
        result.append(enriched)

    return result[skip:skip + limit]


# 3. 获取单个订单
@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    order = orders_db.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    return await enrich_order_with_items(order_id, order)


# 4. 更新订单状态
@app.patch("/orders/{order_id}/status")
async def update_order_status(order_id: int, status: str):
    order = orders_db.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    valid_statuses = ["pending", "paid", "shipped", "completed", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效状态，可选: {valid_statuses}")

    order["status"] = status
    return {"order_id": order_id, "status": status}


# 5. 取消订单
@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int):
    order = orders_db.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    if order["status"] in ["shipped", "completed"]:
        raise HTTPException(status_code=400, detail="已发货或已完成订单不能取消")

    order["status"] = "cancelled"
    return {"order_id": order_id, "status": "cancelled"}'''

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import time
import logging
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
import os

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建应用 - 正确的写法，没有 static_files 参数
app = FastAPI(title="订单服务", description="电商平台订单管理服务")

# 监控指标
REQUEST_COUNT = Counter('http_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'Request latency', ['method', 'endpoint'])


# 中间件
@app.middleware("http")
async def monitor_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response


# Metrics 端点
@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# 数据模型
class OrderItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItem]
    shipping_address: str


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    shipping_address: str
    items: List[OrderItem]
    created_at: datetime


# 模拟数据库
orders_db = {}
current_order_id = 1


# API 端点
@app.get("/")
async def root():
    return {"service": "订单服务", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate):
    global current_order_id
    total_amount = sum(item.price * item.quantity for item in order.items)

    new_order = {
        "id": current_order_id,
        "user_id": order.user_id,
        "total_amount": total_amount,
        "status": "pending",
        "shipping_address": order.shipping_address,
        "items": [item.dict() for item in order.items],
        "created_at": datetime.now()
    }

    orders_db[current_order_id] = new_order
    current_order_id += 1
    return new_order


@app.get("/orders", response_model=List[OrderResponse])
async def get_orders(skip: int = 0, limit: int = 100):
    orders = list(orders_db.values())
    return orders[skip:skip + limit]


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    order = orders_db.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order