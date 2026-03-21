# product_service/main.py
from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os
import time
import uuid
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
from sqlalchemy.orm import Session
from sqlalchemy import func


from product_service.models import Product, get_db, init_db, SessionLocal


# ==================== Prometheus监控指标 ====================
REQUEST_COUNT = Counter(
    'product_service_requests_total',
    'Total number of requests to product service',
    ['method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'product_service_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

PRODUCT_COUNT = Gauge(
    'product_service_product_count',
    'Total number of products in database'
)

TOTAL_STOCK = Gauge(
    'product_service_total_stock',
    'Total stock of all products'
)

CATEGORY_COUNT = Gauge(
    'product_service_category_count',
    'Number of distinct product categories'
)

MEMORY_USAGE = Gauge(
    'product_service_memory_usage_bytes',
    'Memory usage in bytes'
)

CPU_USAGE = Gauge(
    'product_service_cpu_usage_percent',
    'CPU usage percentage'
)

# ==================== FastAPI应用 ====================
app = FastAPI(title="商品服务", description="电商平台商品管理服务")


# ==================== 中间件 ====================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=status_code
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

    return response


# ==================== 后台任务 ====================
@app.on_event("startup")
async def startup_event():
    init_db()
    import asyncio
    asyncio.create_task(update_system_metrics())


async def update_system_metrics():
    import asyncio
    while True:
        db = SessionLocal()
        try:
            product_count = db.query(Product).count()
            PRODUCT_COUNT.set(product_count)

            total_stock = db.query(func.sum(Product.stock)).scalar() or 0
            TOTAL_STOCK.set(total_stock)

            categories = db.query(Product.category).distinct().count()
            CATEGORY_COUNT.set(categories)
        finally:
            db.close()

        process = psutil.Process()
        MEMORY_USAGE.set(process.memory_info().rss)
        CPU_USAGE.set(process.cpu_percent())

        await asyncio.sleep(15)


# ==================== 数据模型 ====================
class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int = 0
    category: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None


class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    category: Optional[str] = None
    created_at: datetime


# ==================== 关键修正：库存操作Pydantic模型 ====================
class ReserveRequest(BaseModel):
    quantity: int


class ReleaseRequest(BaseModel):
    quantity: int


# ==================== 监控端点 ====================
@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {
        "service": "商品服务",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    product_count = db.query(Product).count()

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "service": "product_service",
        "database": db_status,
        "products_count": product_count
    }


# ==================== 商品CRUD ====================
@app.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    product_id = str(uuid.uuid4())

    db_product = Product(
        id=product_id,
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        category=product.category
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return {
        "id": db_product.id,
        "name": db_product.name,
        "description": db_product.description,
        "price": db_product.price,
        "stock": db_product.stock,
        "category": db_product.category,
        "created_at": db_product.created_at
    }


@app.get("/products", response_model=List[ProductResponse])
async def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = db.query(Product).offset(skip).limit(limit).all()
    return [{
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "stock": p.stock,
        "category": p.category,
        "created_at": p.created_at
    } for p in products]


@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "stock": product.stock,
        "category": product.category,
        "created_at": product.created_at
    }


@app.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, product: ProductUpdate, db: Session = Depends(get_db)):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="商品不存在")

    update_data = product.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)
    return {
        "id": db_product.id,
        "name": db_product.name,
        "description": db_product.description,
        "price": db_product.price,
        "stock": db_product.stock,
        "category": db_product.category,
        "created_at": db_product.created_at
    }


@app.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    db.delete(product)
    db.commit()
    return None


# ==================== 库存管理（关键修正：使用Pydantic模型）====================

@app.get("/products/{product_id}/stock")
async def check_stock(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"product_id": product_id, "stock": product.stock}


# 关键修正：使用 ReserveRequest Pydantic模型
@app.post("/products/{product_id}/stock/reserve")
async def reserve_stock(
        product_id: str,
        req: ReserveRequest,  # 修正：使用Pydantic模型
        db: Session = Depends(get_db)
):
    """
    预留库存：直接扣减库存，用于订单创建
    如果订单后续失败，需要调用 /stock/release 释放
    """
    quantity = req.quantity  # 直接访问属性

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < quantity:
        return {
            "success": False,
            "message": f"Insufficient stock: available {product.stock}, requested {quantity}"
        }

    product.stock -= quantity
    db.commit()

    return {
        "success": True,
        "reserved": quantity,
        "remaining_stock": product.stock,
        "price": product.price
    }


# 关键修正：使用 ReleaseRequest Pydantic模型
@app.post("/products/{product_id}/stock/release")
async def release_stock(
        product_id: str,
        req: ReleaseRequest,  # 修正：使用Pydantic模型
        db: Session = Depends(get_db)
):
    """
    释放库存：将预留的库存加回来（订单取消或失败时调用）
    """
    quantity = req.quantity  # 直接访问属性

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.stock += quantity
    db.commit()

    return {
        "success": True,
        "released": quantity,
        "current_stock": product.stock
    }


@app.post("/products/{product_id}/stock/decrease")
async def decrease_stock(product_id: str, quantity: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="库存不足")

    product.stock -= quantity
    db.commit()

    return {"product_id": product_id, "remaining_stock": product.stock}