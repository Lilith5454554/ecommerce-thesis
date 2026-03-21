# order_service/main.py
from fastapi import FastAPI, HTTPException, Response, Depends, status
from pydantic import BaseModel
from typing import Optional, List,Dict
from datetime import datetime, timedelta
import time
import uuid
import os
import logging
import asyncio

from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================== 关键修正：显式导入SessionLocal ====================
from order_service.models import (
    Order,
    OrderItem,
    OrderStatus,
    get_db,
    init_db,
    SessionLocal  # 关键：供定时任务使用
)
from saga import OrderSaga

# ==================== 配置 ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")
PAYMENT_TIMEOUT_MINUTES = 30

# ==================== Prometheus监控 ====================
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint']
)

ORDERS_CREATED = Counter('orders_created_total', 'Total orders created', ['status'])
ORDERS_CANCELLED = Counter('orders_cancelled_total', 'Total orders cancelled')
ACTIVE_ORDERS = Gauge('active_orders', 'Number of active (pending) orders')
SAGA_EXECUTIONS = Counter('saga_executions_total', 'Saga executions', ['result'])

# ==================== FastAPI应用 ====================
app = FastAPI(title="订单服务", description="电商平台订单管理服务 - 支持Saga分布式事务")

# ==================== 定时任务调度器 ====================
scheduler = AsyncIOScheduler()


# ==================== 中间件 ====================
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


# ==================== 启动事件 ====================
@app.on_event("startup")
async def startup_event():
    init_db()
    scheduler.start()
    scheduler.add_job(
        cancel_unpaid_orders,
        'interval',
        minutes=1,
        id='cancel_unpaid_orders'
    )
    logger.info("Order service started with Saga support")


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()


# ==================== 关键修正：定时任务使用正确导入的SessionLocal ====================
async def cancel_unpaid_orders():
    """自动取消超过30分钟未支付的订单，并释放库存"""
    db = SessionLocal()  # 使用从models导入的SessionLocal
    try:
        timeout = datetime.utcnow() - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES)

        expired_orders = db.query(Order).filter(
            Order.status == OrderStatus.RESERVED,
            Order.created_at < timeout
        ).all()

        for order in expired_orders:
            logger.info(f"Cancelling expired order: {order.id}")

            # 释放库存
            saga = OrderSaga(PRODUCT_SERVICE_URL)
            for item in order.items:
                result = await saga._release_stock(item.product_id, item.quantity)
                if result["success"]:
                    logger.info(f"Released stock for product {item.product_id}")
                else:
                    logger.error(f"Failed to release stock for {item.product_id}")

            # 更新订单状态
            order.status = OrderStatus.CANCELLED
            db.commit()

            ORDERS_CANCELLED.inc()
            logger.info(f"Order {order.id} cancelled due to payment timeout")

    except Exception as e:
        logger.error(f"Error in cancel_unpaid_orders: {str(e)}")
    finally:
        db.close()


# ==================== 数据模型 ====================
class OrderItemCreate(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    user_id: str
    items: List[OrderItemCreate]
    shipping_address: str


class OrderItemResponse(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float


class OrderResponse(BaseModel):
    id: str
    user_id: str
    total_amount: float
    status: str
    shipping_address: str
    items: List[OrderItemResponse]
    created_at: datetime


# ==================== 监控端点 ====================
@app.get("/metrics")
async def get_metrics():
    db = SessionLocal()
    try:
        active_count = db.query(Order).filter(Order.status.in_([OrderStatus.PENDING, OrderStatus.RESERVED])).count()
        ACTIVE_ORDERS.set(active_count)
    finally:
        db.close()

    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {
        "service": "订单服务",
        "status": "running",
        "features": ["Saga distributed transaction", "Auto-cancel timeout"]
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    stats = {
        "total": db.query(Order).count(),
        "pending": db.query(Order).filter(Order.status == OrderStatus.PENDING).count(),
        "reserved": db.query(Order).filter(Order.status == OrderStatus.RESERVED).count(),
        "paid": db.query(Order).filter(Order.status == OrderStatus.PAID).count(),
        "cancelled": db.query(Order).filter(Order.status == OrderStatus.CANCELLED).count()
    }

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "database": db_status,
        "order_stats": stats
    }


# ==================== 核心API：创建订单（Saga事务）====================
@app.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    """
    创建订单 - 使用Saga模式保证分布式事务一致性
    """
    start_time = time.time()

    saga = OrderSaga(PRODUCT_SERVICE_URL)

    items_data = [
        {
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "price": item.price
        }
        for item in order.items
    ]

    saga_result = await saga.execute(
        user_id=order.user_id,
        items=items_data,
        shipping_address=order.shipping_address
    )

    SAGA_EXECUTIONS.labels(result="success" if saga_result["success"] else "failure").inc()

    if not saga_result["success"]:
        raise HTTPException(status_code=400, detail=saga_result["error"])

    # Saga成功，写入本地数据库
    try:
        db_order = Order(
            id=saga_result["order_id"],
            user_id=order.user_id,
            status=OrderStatus.RESERVED,
            total_amount=saga_result["total_amount"],
            shipping_address=order.shipping_address
        )
        db.add(db_order)

        for item in order.items:
            db_item = OrderItem(
                id=str(uuid.uuid4()),
                order_id=db_order.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                price=item.price
            )
            db.add(db_item)

        db.commit()
        db.refresh(db_order)

        ORDERS_CREATED.labels(status="reserved").inc()

        duration = time.time() - start_time
        logger.info(f"Order {db_order.id} created successfully in {duration:.2f}s")

        return {
            "id": db_order.id,
            "user_id": db_order.user_id,
            "total_amount": db_order.total_amount,
            "status": db_order.status.value,
            "shipping_address": db_order.shipping_address,
            "items": [{
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "price": item.price
            } for item in db_order.items],
            "created_at": db_order.created_at
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Database error for order {saga_result['order_id']}: {str(e)}")
        asyncio.create_task(compensate_stock_async(saga_result["reserved_items"]))
        raise HTTPException(status_code=500, detail=f"Order creation failed: {str(e)}")


async def compensate_stock_async(items: List[Dict]):
    """异步补偿释放库存"""
    saga = OrderSaga(PRODUCT_SERVICE_URL)
    for item in items:
        await saga._release_stock(item["product_id"], item["quantity"])


# ==================== 查询API ====================
@app.get("/orders", response_model=List[OrderResponse])
async def get_orders(
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        db: Session = Depends(get_db)
):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status)

    orders = query.offset(skip).limit(limit).all()

    return [{
        "id": o.id,
        "user_id": o.user_id,
        "total_amount": o.total_amount,
        "status": o.status.value,
        "shipping_address": o.shipping_address,
        "items": [{
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "price": item.price
        } for item in o.items],
        "created_at": o.created_at
    } for o in orders]


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    return {
        "id": order.id,
        "user_id": order.user_id,
        "total_amount": order.total_amount,
        "status": order.status.value,
        "shipping_address": order.shipping_address,
        "items": [{
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "price": item.price
        } for item in order.items],
        "created_at": order.created_at
    }


# ==================== 状态管理API ====================
@app.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    valid_transitions = {
        OrderStatus.RESERVED: [OrderStatus.PAID, OrderStatus.CANCELLED],
        OrderStatus.PAID: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
        OrderStatus.SHIPPED: [OrderStatus.COMPLETED]
    }

    new_status = OrderStatus(status)
    if new_status not in valid_transitions.get(order.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition from {order.status.value} to {status}"
        )

    order.status = new_status
    db.commit()

    return {"order_id": order_id, "status": order.status.value}


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    if order.status not in [OrderStatus.PENDING, OrderStatus.RESERVED]:
        raise HTTPException(status_code=400, detail="Cannot cancel order in current status")

    # 释放库存
    saga = OrderSaga(PRODUCT_SERVICE_URL)
    for item in order.items:
        result = await saga._release_stock(item.product_id, item.quantity)
        if not result["success"]:
            logger.error(f"Failed to release stock for {item.product_id} when cancelling")

    order.status = OrderStatus.CANCELLED
    db.commit()

    ORDERS_CANCELLED.inc()

    return {"order_id": order_id, "status": "cancelled", "message": "Order cancelled and stock released"}