import sys
import os
from pathlib import Path
import uuid

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from product_service.main import app

client = TestClient(app)


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "商品服务"


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_products():
    """测试获取商品列表（初始应为空）"""
    response = client.get("/products/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    # 初始状态应该是空列表
    assert len(response.json()) == 0


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
    assert data["price"] == 99.9
    assert data["stock"] == 100
    assert "id" in data
    assert "created_at" in data


def test_get_product_by_id():
    """测试获取单个商品"""
    # 先创建一个商品
    product_data = {
        "name": "获取测试商品",
        "price": 199.9,
        "stock": 50
    }
    create_response = client.post("/products/", json=product_data)
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    # 获取该商品
    response = client.get(f"/products/{product_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "获取测试商品"
    assert data["price"] == 199.9
    assert data["id"] == product_id


def test_product_not_found():
    """测试商品不存在的情况"""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/products/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "商品不存在"


def test_update_product():
    """测试更新商品"""
    # 先创建商品
    product_data = {
        "name": "原商品名",
        "price": 99.9,
        "stock": 100
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 更新商品
    update_data = {
        "name": "新商品名",
        "price": 199.9,
        "stock": 80
    }
    response = client.put(f"/products/{product_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "新商品名"
    assert data["price"] == 199.9
    assert data["stock"] == 80


def test_delete_product():
    """测试删除商品"""
    # 先创建商品
    product_data = {
        "name": "待删除商品",
        "price": 9.9,
        "stock": 10
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 删除商品
    delete_response = client.delete(f"/products/{product_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "商品删除成功"

    # 验证商品已被删除
    get_response = client.get(f"/products/{product_id}")
    assert get_response.status_code == 404


def test_check_stock():
    """测试检查库存"""
    # 先创建商品
    product_data = {
        "name": "库存测试商品",
        "price": 29.9,
        "stock": 50
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 检查库存
    response = client.get(f"/products/{product_id}/stock")
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 50


def test_decrease_stock():
    """测试扣减库存"""
    # 先创建商品
    product_data = {
        "name": "扣减库存测试",
        "price": 39.9,
        "stock": 30
    }
    create_response = client.post("/products/", json=product_data)
    product_id = create_response.json()["id"]

    # 扣减库存
    response = client.post(f"/products/{product_id}/stock/decrease", params={"quantity": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["remaining_stock"] == 25

    # 验证库存已更新
    check_response = client.get(f"/products/{product_id}/stock")
    assert check_response.json()["stock"] == 25