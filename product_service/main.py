from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os


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
# 用字典模拟数据库，key是商品ID，value是商品数据
products_db = {}
current_id = 1

# ==================== FastAPI 应用 ====================
app = FastAPI(title="商品服务", description="电商平台商品管理服务")


# ==================== 健康检查 ====================
@app.get("/")
async def root():
    return {"service": "商品服务", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


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
    return {"product_id": product_id, "remaining_stock": product["stock"]}
