from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import psutil
import random

# ==================== Prometheus 监控指标 ====================

# 请求计数：记录每个端点的请求次数和状态码
REQUEST_COUNT = Counter(
    'product_service_requests_total',
    'Total number of requests to product service',
    ['method', 'endpoint', 'status_code']
)

# 请求延迟：记录每个端点的响应时间
REQUEST_LATENCY = Histogram(
    'product_service_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

# 业务指标：商品总数
PRODUCT_COUNT = Gauge(
    'product_service_product_count',
    'Total number of products in database'
)

# 业务指标：库存总量
TOTAL_STOCK = Gauge(
    'product_service_total_stock',
    'Total stock of all products'
)

# 业务指标：商品分类数量
CATEGORY_COUNT = Gauge(
    'product_service_category_count',
    'Number of distinct product categories'
)

# 系统指标：内存使用
MEMORY_USAGE = Gauge(
    'product_service_memory_usage_bytes',
    'Memory usage in bytes'
)

# 系统指标：CPU使用率
CPU_USAGE = Gauge(
    'product_service_cpu_usage_percent',
    'CPU usage percentage'
)


# ==================== 数据模型 ====================
class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    category: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    category: Optional[str] = None
    created_at: datetime


# ==================== 模拟数据库 ====================
products_db = {}
current_id = 1

# ==================== FastAPI 应用 ====================
app = FastAPI(title="商品服务", description="电商平台商品管理服务")


# ==================== 监控中间件 ====================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    """监控所有请求的中间件"""
    # 记录开始时间
    start_time = time.time()

    # 处理请求
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        # 记录异常
        status_code = 500
        raise e
    finally:
        # 计算耗时
        duration = time.time() - start_time

        # 记录请求指标
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


# ==================== 后台任务：更新系统指标 ====================
@app.on_event("startup")
async def startup_event():
    """启动时执行的任务"""
    import asyncio
    asyncio.create_task(update_system_metrics())


async def update_system_metrics():
    """定期更新系统指标的后台任务"""
    import asyncio
    while True:
        # 更新业务指标
        PRODUCT_COUNT.set(len(products_db))

        # 计算总库存
        total_stock = sum(p["stock"] for p in products_db.values())
        TOTAL_STOCK.set(total_stock)

        # 计算分类数量
        categories = set(p.get("category") for p in products_db.values() if p.get("category"))
        CATEGORY_COUNT.set(len(categories))

        # 更新系统指标
        process = psutil.Process()
        MEMORY_USAGE.set(process.memory_info().rss)
        CPU_USAGE.set(process.cpu_percent())

        # 每15秒更新一次
        await asyncio.sleep(15)


# ==================== 监控端点 ====================
@app.get("/metrics")
async def get_metrics():
    """Prometheus 监控指标端点"""
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {
        "service": "商品服务",
        "status": "running",
        "version": "1.0.0",
        "metrics": "/metrics - Prometheus监控指标"
    }


@app.get("/health")
async def health():
    """详细健康检查，包含各个组件的状态"""
    # 检查数据库（模拟）
    db_status = "healthy" if products_db is not None else "unhealthy"

    # 检查内存使用
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024

    return {
        "status": "healthy",
        "service": "product_service",
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "database": db_status,
            "memory": f"{memory_mb:.2f} MB",
            "products_count": len(products_db)
        }
    }


# ==================== 商品接口 ====================

# 1. 创建商品
@app.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(product: ProductCreate):
    global current_id

    new_product = {
        "id": current_id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "stock": product.stock,
        "category": product.category,
        "created_at": datetime.now()
    }

    products_db[current_id] = new_product
    current_id += 1

    # 手动触发指标更新（可选，但后台任务会自动更新）
    PRODUCT_COUNT.inc()

    return new_product


# 2. 获取所有商品
@app.get("/products", response_model=List[ProductResponse])
async def get_products(skip: int = 0, limit: int = 100):
    all_products = list(products_db.values())
    return all_products[skip:skip + limit]


# 3. 获取单个商品
@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int):
    product = products_db.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


# 4. 更新商品
@app.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: int, product: ProductUpdate):
    existing = products_db.get(product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 只更新提供的字段
    update_data = product.dict(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            existing[key] = value

    products_db[product_id] = existing
    return existing


# 5. 删除商品
@app.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="商品不存在")

    del products_db[product_id]
    PRODUCT_COUNT.dec()  # 商品总数减1
    return None


# 6. 检查库存
@app.get("/products/{product_id}/stock")
async def check_stock(product_id: int):
    product = products_db.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"product_id": product_id, "stock": product["stock"]}


# 7. 扣减库存（下单时调用）
@app.post("/products/{product_id}/stock/decrease")
async def decrease_stock(product_id: int, quantity: int):
    product = products_db.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    if product["stock"] < quantity:
        raise HTTPException(status_code=400, detail="库存不足")

    product["stock"] -= quantity
    # 库存变化会自动被后台指标更新任务捕获
    return {"product_id": product_id, "remaining_stock": product["stock"]}


# 8. 批量创建商品（用于测试）
@app.post("/products/batch", status_code=201)
async def create_batch_products(count: int = 10):
    """批量创建商品，用于测试监控"""
    global current_id
    created = []

    categories = ["电子产品", "服装", "食品", "图书", "家居"]

    for i in range(count):
        new_product = {
            "id": current_id,
            "name": f"测试商品{current_id}",
            "description": f"这是第{current_id}个测试商品",
            "price": round(random.uniform(10, 1000), 2),
            "stock": random.randint(0, 200),
            "category": random.choice(categories),
            "created_at": datetime.now()
        }
        products_db[current_id] = new_product
        created.append(new_product)
        current_id += 1

    PRODUCT_COUNT.inc(count)
    return {"message": f"成功创建{count}个商品", "products": created}


# 9. 模拟慢查询（用于测试监控）
@app.get("/products/slow-query")
async def slow_query(delay: float = 2.0):
    """模拟慢查询，测试监控告警"""
    import asyncio
    await asyncio.sleep(delay)
    return {"message": f"慢查询完成，延迟{delay}秒"}


# 10. 模拟错误（用于测试监控）
@app.get("/products/error-test")
async def error_test(error_type: str = "500"):
    """模拟各种错误，测试监控"""
    if error_type == "404":
        raise HTTPException(status_code=404, detail="模拟的404错误")
    elif error_type == "400":
        raise HTTPException(status_code=400, detail="模拟的400错误")
    elif error_type == "500":
        raise HTTPException(status_code=500, detail="模拟的500错误")
    else:
        return {"message": "没有错误"}

