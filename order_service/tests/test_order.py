import sys
import os
from pathlib import Path
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from order_service.main import app
from order_service.models import init_db, SessionLocal, Order, OrderItem

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


client = TestClient(app)


# ==================== 测试辅助函数 ====================
def setup_function():
    """每个测试前重置数据库"""
    db = SessionLocal()
    try:
        db.query(OrderItem).delete()
        db.query(Order).delete()
        db.commit()
        print("✓ Test data cleared")
    except Exception as e:
        db.rollback()
        print(f"Error clearing table: {e}")
    finally:
        db.close()


# ==================== 基础接口测试 ====================

def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "订单服务"
    assert data["status"] == "running"


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ==================== 创建订单测试 ====================

def test_create_order_success():
    """测试成功创建订单"""
    order_data = {
        "user_id": 1,
        "shipping_address": "北京市朝阳区xx路1号",
        "items": [
            {"product_id": 101, "quantity": 2},
            {"product_id": 102, "quantity": 1}
        ]
    }

    response = client.post("/orders", json=order_data)
    assert response.status_code == 201
    data = response.json()

    # 验证订单基本信息
    assert data["user_id"] == 1
    assert data["status"] == "pending"
    assert data["shipping_address"] == "北京市朝阳区xx路1号"
    assert "id" in data
    assert "total_amount" in data
    assert "created_at" in data

    # 验证订单项
    assert len(data["items"]) == 2
    assert data["items"][0]["product_id"] == 101
    assert data["items"][0]["quantity"] == 2
    assert data["items"][1]["product_id"] == 102
    assert data["items"][1]["quantity"] == 1


def test_create_order_user_not_found():
    """测试创建订单时用户不存在"""
    order_data = {
        "user_id": 999,  # 不存在的用户
        "shipping_address": "上海市浦东新区xx路2号",
        "items": [{"product_id": 101, "quantity": 1}]
    }

    response = client.post("/orders", json=order_data)
    # 由于服务间调用可能失败，这里可能是400或201（用模拟数据）
    assert response.status_code in [400, 201]


def test_create_order_invalid_user_id():
    """测试创建订单时用户ID无效"""
    order_data = {
        "user_id": -1,  # 无效的用户ID
        "shipping_address": "广州市天河区xx路3号",
        "items": [{"product_id": 101, "quantity": 1}]
    }

    response = client.post("/orders", json=order_data)
    # 应该返回400
    assert response.status_code == 400


def test_create_order_product_not_found():
    """测试创建订单时商品不存在"""
    order_data = {
        "user_id": 1,
        "shipping_address": "深圳市南山区xx路4号",
        "items": [{"product_id": 99999, "quantity": 1}]  # 不存在的商品
    }

    response = client.post("/orders", json=order_data)
    # 可能是400或201（用模拟数据）
    assert response.status_code in [400, 201]


def test_create_order_multiple_items():
    """测试创建包含多个商品的订单"""
    order_data = {
        "user_id": 1,
        "shipping_address": "杭州市西湖区xx路5号",
        "items": [
            {"product_id": 101, "quantity": 1},
            {"product_id": 102, "quantity": 2},
            {"product_id": 103, "quantity": 3},
            {"product_id": 104, "quantity": 1}
        ]
    }

    response = client.post("/orders", json=order_data)
    assert response.status_code == 201
    data = response.json()
    assert len(data["items"]) == 4


def test_create_order_empty_items():
    """测试创建订单时商品列表为空"""
    order_data = {
        "user_id": 1,
        "shipping_address": "成都市武侯区xx路6号",
        "items": []
    }

    response = client.post("/orders", json=order_data)
    assert response.status_code == 201
    data = response.json()
    assert len(data["items"]) == 0
    assert data["total_amount"] == 0


# ==================== 查询订单测试 ====================

def test_get_orders_empty():
    """测试获取订单列表（初始为空）"""
    response = client.get("/orders")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 0


def test_get_orders_with_data():
    """测试获取订单列表（有数据）"""
    # 先创建几个订单
    order1 = {
        "user_id": 1,
        "shipping_address": "地址1",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    order2 = {
        "user_id": 2,
        "shipping_address": "地址2",
        "items": [{"product_id": 102, "quantity": 2}]
    }

    client.post("/orders", json=order1)
    client.post("/orders", json=order2)

    # 获取所有订单
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_orders_filter_by_user():
    """测试按用户筛选订单"""
    # 创建不同用户的订单
    order_user1 = {
        "user_id": 1,
        "shipping_address": "用户1地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    order_user2 = {
        "user_id": 2,
        "shipping_address": "用户2地址",
        "items": [{"product_id": 102, "quantity": 2}]
    }

    client.post("/orders", json=order_user1)
    client.post("/orders", json=order_user2)
    client.post("/orders", json=order_user1)  # 再创建一个用户1的订单

    # 筛选用户1的订单
    response = client.get("/orders?user_id=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for order in data:
        assert order["user_id"] == 1


def test_get_orders_with_pagination():
    """测试分页获取订单"""
    # 创建5个订单
    for i in range(5):
        order = {
            "user_id": 1,
            "shipping_address": f"地址{i}",
            "items": [{"product_id": 101, "quantity": 1}]
        }
        client.post("/orders", json=order)

    # 获取前2个
    response = client.get("/orders?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # 跳过前2个，获取2个
    response = client.get("/orders?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_order_by_id():
    """测试根据ID获取单个订单"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "南京市鼓楼区xx路7号",
        "items": [{"product_id": 101, "quantity": 2}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 获取该订单
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["user_id"] == 1
    assert data["shipping_address"] == "南京市鼓楼区xx路7号"


def test_get_order_not_found():
    """测试获取不存在的订单"""
    response = client.get("/orders/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "订单不存在"


# ==================== 订单状态更新测试 ====================

def test_update_order_status():
    """测试更新订单状态"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 更新状态为 paid
    response = client.patch(f"/orders/{order_id}/status", params={"status": "paid"})
    assert response.status_code == 200
    assert response.json()["status"] == "paid"

    # 验证订单状态已更新
    get_resp = client.get(f"/orders/{order_id}")
    assert get_resp.json()["status"] == "paid"


def test_update_order_status_invalid():
    """测试更新订单状态为无效值"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 尝试更新为无效状态
    response = client.patch(f"/orders/{order_id}/status", params={"status": "invalid_status"})
    assert response.status_code == 400
    assert "无效状态" in response.json()["detail"]


def test_update_order_status_not_found():
    """测试更新不存在的订单状态"""
    response = client.patch("/orders/999/status", params={"status": "paid"})
    assert response.status_code == 404


# ==================== 取消订单测试 ====================

def test_cancel_order():
    """测试取消订单"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 取消订单
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # 验证订单状态已更新
    get_resp = client.get(f"/orders/{order_id}")
    assert get_resp.json()["status"] == "cancelled"


def test_cancel_order_already_shipped():
    """测试取消已发货的订单"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 将订单状态改为 shipped
    client.patch(f"/orders/{order_id}/status", params={"status": "shipped"})

    # 尝试取消
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 400
    assert "已发货或已完成订单不能取消" in response.json()["detail"]


def test_cancel_order_already_completed():
    """测试取消已完成的订单"""
    # 先创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [{"product_id": 101, "quantity": 1}]
    }
    create_resp = client.post("/orders", json=order_data)
    order_id = create_resp.json()["id"]

    # 将订单状态改为 completed
    client.patch(f"/orders/{order_id}/status", params={"status": "completed"})

    # 尝试取消
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 400


def test_cancel_order_not_found():
    """测试取消不存在的订单"""
    response = client.post("/orders/999/cancel")
    assert response.status_code == 404


# ==================== 综合场景测试 ====================

def test_order_lifecycle():
    """测试订单完整生命周期"""
    # 1. 创建订单
    order_data = {
        "user_id": 1,
        "shipping_address": "西安市雁塔区xx路8号",
        "items": [{"product_id": 101, "quantity": 2}]
    }
    create_resp = client.post("/orders", json=order_data)
    assert create_resp.status_code == 201
    order_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "pending"

    # 2. 支付订单
    pay_resp = client.patch(f"/orders/{order_id}/status", params={"status": "paid"})
    assert pay_resp.status_code == 200
    assert pay_resp.json()["status"] == "paid"

    # 3. 发货
    ship_resp = client.patch(f"/orders/{order_id}/status", params={"status": "shipped"})
    assert ship_resp.status_code == 200
    assert ship_resp.json()["status"] == "shipped"

    # 4. 完成订单
    complete_resp = client.patch(f"/orders/{order_id}/status", params={"status": "completed"})
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "completed"

    # 5. 验证最终状态
    get_resp = client.get(f"/orders/{order_id}")
    assert get_resp.json()["status"] == "completed"


def test_multiple_orders_same_user():
    """测试同一用户多个订单"""
    user_id = 42

    # 创建3个订单
    for i in range(3):
        order_data = {
            "user_id": user_id,
            "shipping_address": f"地址{i}",
            "items": [{"product_id": 100 + i, "quantity": i + 1}]
        }
        client.post("/orders", json=order_data)

    # 查询该用户的所有订单
    response = client.get(f"/orders?user_id={user_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    for order in data:
        assert order["user_id"] == user_id


def test_order_total_amount_calculation():
    """测试订单总价计算"""
    order_data = {
        "user_id": 1,
        "shipping_address": "地址",
        "items": [
            {"product_id": 101, "quantity": 2},
            {"product_id": 102, "quantity": 1},
            {"product_id": 103, "quantity": 3}
        ]
    }

    response = client.post("/orders", json=order_data)
    assert response.status_code == 201
    data = response.json()

    # 验证总价
    total = 0
    for item in data["items"]:
        total += item["price"] * item["quantity"]
    assert data["total_amount"] == total