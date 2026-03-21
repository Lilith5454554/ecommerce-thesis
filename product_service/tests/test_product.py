import sys
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from product_service.models import init_db
# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from product_service.main import app

client = TestClient(app)

# ==================== 创建数据库表 ====================
init_db()
print("✓ Product service tables created")


# ==================== 测试辅助函数 ====================
def setup_function():
    """每个测试前重置数据库"""
    # 注意：如果你的 main.py 中有全局变量，可以在这里重置
    # 这里假设你的商品服务有 products_db 全局变量
    import product_service.main
    if hasattr(product_service.main, 'products_db'):
        product_service.main.products_db.clear()
    if hasattr(product_service.main, 'current_product_id'):
        product_service.main.current_product_id = 1


# ==================== 基础接口测试 ====================

def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "商品服务" in data["service"] or "product" in data["service"].lower()


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


# ==================== 创建商品测试 ====================

def test_create_product():
    """测试创建商品"""
    product_data = {
        "name": "测试商品",
        "description": "这是一个测试商品",
        "price": 99.9,
        "stock": 100,
        "category": "电子产品"
    }

    response = client.post("/products/", json=product_data)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "测试商品"
    assert data["description"] == "这是一个测试商品"
    assert data["price"] == 99.9
    assert data["stock"] == 100
    assert data["category"] == "电子产品"
    assert "id" in data
    assert "created_at" in data


def test_create_product_minimal():
    """测试创建商品（仅必填字段）"""
    product_data = {
        "name": "最小商品",
        "price": 29.9,
        "stock": 50
    }

    response = client.post("/products/", json=product_data)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "最小商品"
    assert data["price"] == 29.9
    assert data["stock"] == 50
    assert data.get("description") is None or data.get("description") == ""
    assert "id" in data


def test_create_product_invalid_price():
    """测试创建商品时价格无效"""
    product_data = {
        "name": "无效价格商品",
        "price": -10,  # 负数价格
        "stock": 50
    }

    response = client.post("/products/", json=product_data)
    # 应该返回 422 验证错误
    assert response.status_code == 422


def test_create_product_invalid_stock():
    """测试创建商品时库存无效"""
    product_data = {
        "name": "无效库存商品",
        "price": 100,
        "stock": -5  # 负数库存
    }

    response = client.post("/products/", json=product_data)
    assert response.status_code == 422


def test_create_product_missing_name():
    """测试创建商品时缺少名称"""
    product_data = {
        "price": 100,
        "stock": 50
    }

    response = client.post("/products/", json=product_data)
    assert response.status_code == 422


# ==================== 查询商品测试 ====================

def test_get_products_empty():
    """测试获取商品列表（初始为空）"""
    response = client.get("/products/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 0


def test_get_products_with_data():
    """测试获取商品列表（有数据）"""
    # 先创建几个商品
    products = [
        {"name": "商品1", "price": 10.0, "stock": 100},
        {"name": "商品2", "price": 20.0, "stock": 200},
        {"name": "商品3", "price": 30.0, "stock": 300}
    ]

    for p in products:
        client.post("/products/", json=p)

    # 获取所有商品
    response = client.get("/products/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_get_products_with_pagination():
    """测试分页获取商品"""
    # 创建5个商品
    for i in range(5):
        product = {
            "name": f"商品{i}",
            "price": 10.0 * (i + 1),
            "stock": 100 * (i + 1)
        }
        client.post("/products/", json=product)

    # 测试分页参数
    response = client.get("/products/?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    response = client.get("/products/?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    response = client.get("/products/?skip=4&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_get_products_filter_by_category():
    """测试按分类筛选商品"""
    # 创建不同分类的商品
    products = [
        {"name": "手机", "price": 1999, "stock": 50, "category": "电子产品"},
        {"name": "电脑", "price": 5999, "stock": 30, "category": "电子产品"},
        {"name": "T恤", "price": 99, "stock": 200, "category": "服装"},
        {"name": "裤子", "price": 199, "stock": 150, "category": "服装"}
    ]

    for p in products:
        client.post("/products/", json=p)

    # 筛选电子产品
    response = client.get("/products/?category=电子产品")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for p in data:
        assert p["category"] == "电子产品"

    # 筛选服装
    response = client.get("/products/?category=服装")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for p in data:
        assert p["category"] == "服装"


def test_get_product_by_id():
    """测试根据ID获取单个商品"""
    # 先创建商品
    product_data = {
        "name": "特定商品",
        "price": 88.8,
        "stock": 88
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 获取该商品
    response = client.get(f"/products/{product_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["name"] == "特定商品"
    assert data["price"] == 88.8


def test_get_product_not_found():
    """测试获取不存在的商品"""
    response = client.get("/products/99999")
    # 根据你的API设计，可能是404或422
    # 404: 资源不存在
    # 422: 请求参数格式错误（如果ID类型不匹配）
    assert response.status_code in [404, 422]

    if response.status_code == 404:
        # 如果返回404，检查错误信息
        error_data = response.json()
        assert "detail" in error_data
        assert "不存在" in error_data["detail"] or "not found" in error_data["detail"].lower()


# ==================== 更新商品测试 ====================

def test_update_product():
    """测试更新商品"""
    # 先创建商品
    product_data = {
        "name": "原商品名",
        "description": "原描述",
        "price": 99.9,
        "stock": 100,
        "category": "原分类"
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 更新商品（使用 model_dump 替代 dict，避免弃用警告）
    update_data = {
        "name": "新商品名",
        "price": 199.9,
        "category": "新分类"
    }

    response = client.put(f"/products/{product_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()

    # 验证更新的字段
    assert data["name"] == "新商品名"
    assert data["price"] == 199.9
    assert data["category"] == "新分类"
    # 未更新的字段应该保持不变
    assert data["description"] == "原描述"
    assert data["stock"] == 100


def test_update_product_partial():
    """测试部分更新商品（PATCH）"""
    # 先创建商品
    product_data = {
        "name": "原商品名",
        "price": 99.9,
        "stock": 100
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 部分更新
    update_data = {
        "price": 199.9
    }

    # 使用 PATCH 方法（如果你的API支持）
    response = client.patch(f"/products/{product_id}", json=update_data)
    # 可能是 200 或 204
    assert response.status_code in [200, 204]

    # 验证更新结果
    get_response = client.get(f"/products/{product_id}")
    data = get_response.json()
    assert data["price"] == 199.9
    assert data["name"] == "原商品名"  # 未变
    assert data["stock"] == 100  # 未变


def test_update_product_not_found():
    """测试更新不存在的商品"""
    update_data = {
        "name": "新名称",
        "price": 100
    }

    response = client.put("/products/99999", json=update_data)
    # 根据你的API设计，可能是404或422
    assert response.status_code in [404, 422]


def test_update_product_invalid_data():
    """测试更新商品时提供无效数据"""
    # 先创建商品
    product_data = {"name": "商品", "price": 100, "stock": 50}
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 尝试更新为负数价格
    update_data = {"price": -50}
    response = client.put(f"/products/{product_id}", json=update_data)
    assert response.status_code == 422


# ==================== 删除商品测试 ====================

def test_delete_product():
    """测试删除商品"""
    # 先创建商品
    product_data = {
        "name": "待删除商品",
        "price": 99.9,
        "stock": 100
    }
    create_response = client.post("/products/", json=product_data)
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    # 删除商品
    delete_response = client.delete(f"/products/{product_id}")
    # REST API 规范中，DELETE 成功常返回 204 No Content，也可能返回 200
    assert delete_response.status_code in [200, 204]

    # 验证商品已被删除
    get_response = client.get(f"/products/{product_id}")
    assert get_response.status_code in [404, 422]


def test_delete_product_not_found():
    """测试删除不存在的商品"""
    response = client.delete("/products/99999")
    # 根据你的API设计，可能是404或422
    assert response.status_code in [404, 422]


# ==================== 库存操作测试 ====================

def test_decrease_stock():
    """测试减少库存"""
    # 先创建商品
    product_data = {
        "name": "库存测试商品",
        "price": 100,
        "stock": 50
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 减少库存
    response = client.post(f"/products/{product_id}/stock/decrease", params={"quantity": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 40


def test_decrease_stock_insufficient():
    """测试库存不足时减少库存"""
    # 先创建商品
    product_data = {
        "name": "库存不足测试",
        "price": 100,
        "stock": 5
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 减少超过当前库存的数量
    response = client.post(f"/products/{product_id}/stock/decrease", params={"quantity": 10})
    assert response.status_code == 400
    assert "库存不足" in response.json()["detail"]


def test_increase_stock():
    """测试增加库存"""
    # 先创建商品
    product_data = {
        "name": "增加库存测试",
        "price": 100,
        "stock": 30
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 增加库存
    response = client.post(f"/products/{product_id}/stock/increase", params={"quantity": 20})
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 50


# ==================== 综合场景测试 ====================

def test_product_lifecycle():
    """测试商品完整生命周期"""
    # 1. 创建商品
    product_data = {
        "name": "生命周期测试商品",
        "description": "测试完整流程",
        "price": 199.9,
        "stock": 100,
        "category": "测试类"
    }
    create_resp = client.post("/products/", json=product_data)
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    # 2. 查询商品
    get_resp = client.get(f"/products/{product_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "生命周期测试商品"

    # 3. 更新商品
    update_data = {"price": 299.9, "stock": 80}
    update_resp = client.put(f"/products/{product_id}", json=update_data)
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 299.9
    assert update_resp.json()["stock"] == 80

    # 4. 减少库存
    decrease_resp = client.post(f"/products/{product_id}/stock/decrease", params={"quantity": 20})
    assert decrease_resp.status_code == 200
    assert decrease_resp.json()["stock"] == 60

    # 5. 删除商品
    delete_resp = client.delete(f"/products/{product_id}")
    assert delete_resp.status_code in [200, 204]

    # 6. 验证已删除
    final_resp = client.get(f"/products/{product_id}")
    assert final_resp.status_code in [404, 422]


def test_search_products():
    """测试搜索商品"""
    # 创建一些商品
    products = [
        {"name": "苹果手机", "price": 5999, "stock": 100, "category": "电子产品"},
        {"name": "苹果电脑", "price": 12999, "stock": 50, "category": "电子产品"},
        {"name": "香蕉", "price": 5, "stock": 1000, "category": "水果"},
        {"name": "苹果", "price": 8, "stock": 500, "category": "水果"}
    ]

    for p in products:
        client.post("/products/", json=p)

    # 搜索包含"苹果"的商品
    response = client.get("/products/?search=苹果")
    assert response.status_code == 200
    data = response.json()
    # 应该返回苹果手机、苹果电脑、苹果（水果）
    assert len(data) == 3
    for p in data:
        assert "苹果" in p["name"]

    # 搜索"水果"
    response = client.get("/products/?category=水果")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_bulk_create_products():
    """测试批量创建商品（如果API支持）"""
    products = [
        {"name": "批量商品1", "price": 10, "stock": 100},
        {"name": "批量商品2", "price": 20, "stock": 200},
        {"name": "批量商品3", "price": 30, "stock": 300}
    ]

    # 如果API支持批量创建
    response = client.post("/products/bulk", json={"products": products})
    if response.status_code == 200 or response.status_code == 201:
        data = response.json()
        assert len(data) == 3

    # 验证商品已创建
    get_response = client.get("/products/")
    assert len(get_response.json()) >= 3