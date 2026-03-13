import sys
import os
from pathlib import Path
import uuid

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from order_service.main import app

client = TestClient(app)


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "订单服务"


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_orders():
    """测试获取订单列表（初始应为空）"""
    response = client.get("/orders/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    # 初始状态应该是空列表
    assert len(response.json()) == 0


def test_create_order():
    """测试创建订单"""
    order_data = {
        "user_id": 1,
        "items": [
            {"product_id": 1, "quantity": 2}
        ],
        "shipping_address": "北京市朝阳区"
    }
    response = client.post("/orders/", json=order_data)
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == 1
    assert data["status"] == "pending"
    assert "total_amount" in data
    assert "id" in data
    assert "created_at" in data


def test_get_order_by_id():
    """测试获取单个订单"""
    # 先创建一个订单
    order_data = {
        "user_id": 2,
        "items": [
            {"product_id": 1, "quantity": 1}
        ],
        "shipping_address": "上海市浦东新区"
    }
    create_response = client.post("/orders/", json=order_data)
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    # 获取该订单
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 2
    assert data["id"] == order_id


def test_order_not_found():
    """测试订单不存在的情况"""
    fake_id = 99999
    response = client.get(f"/orders/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "订单不存在"


def test_update_order_status():
    """测试更新订单状态"""
    # 先创建订单
    order_data = {
        "user_id": 3,
        "items": [
            {"product_id": 1, "quantity": 3}
        ],
        "shipping_address": "广州市天河区"
    }
    create_response = client.post("/orders/", json=order_data)
    order_id = create_response.json()["id"]

    # 更新状态为已支付
    response = client.patch(f"/orders/{order_id}/status", params={"status": "paid"})
    assert response.status_code == 200
    assert response.json()["status"] == "paid"

    # 获取订单验证状态已更新
    get_response = client.get(f"/orders/{order_id}")
    assert get_response.json()["status"] == "paid"


def test_cancel_order():
    """测试取消订单"""
    # 先创建订单
    order_data = {
        "user_id": 4,
        "items": [
            {"product_id": 1, "quantity": 1}
        ],
        "shipping_address": "深圳市南山区"
    }
    create_response = client.post("/orders/", json=order_data)
    order_id = create_response.json()["id"]

    # 取消订单
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # 验证订单状态已更新
    get_response = client.get(f"/orders/{order_id}")
    assert get_response.json()["status"] == "cancelled"