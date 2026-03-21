import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 1. 先导入 models 并创建数据库表
from user_service.models import init_db, SessionLocal,User

# 2. 创建数据库表（关键步骤！）
init_db()
print("✓ Database tables created for testing")

from fastapi.testclient import TestClient
from user_service.main import app

def setup_function():
    """每个测试前清空表数据，保证测试隔离"""
    db = SessionLocal()
    try:
        # 使用 SQLAlchemy 删除所有数据
        db.query(User).delete()
        db.commit()
        print("✓ Test data cleared")
    except Exception as e:
        db.rollback()
        print(f"Error clearing table: {e}")
    finally:
        db.close()

client = TestClient(app)


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "User Service"


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "user_service"}


def test_get_users():
    """测试获取用户列表（初始应为空）"""
    response = client.get("/users/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    # 初始状态应该是空列表
    assert len(response.json()) == 0


def test_create_user():
    """测试创建用户"""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123"
    }
    response = client.post("/users/", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password" not in data  # 密码不应该返回



def test_get_user_by_id():
    """测试获取单个用户"""
    # 先创建一个用户
    user_data = {
        "username": "getuser",
        "email": "get@example.com"
    }
    create_response = client.post("/users/", json=user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    # 获取该用户
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "getuser"
    assert data["email"] == "get@example.com"
    assert data["id"] == user_id


def test_user_not_found():
    """测试用户不存在的情况"""
    response = client.get("/users/non-existent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_create_duplicate_user():
    """测试创建重复用户（可选）"""
    user_data = {
        "username": "duplicate",
        "email": "duplicate@example.com"
    }
    # 第一次创建
    response1 = client.post("/users/", json=user_data)
    assert response1.status_code == 201

    # 第二次创建相同用户（根据你的业务逻辑决定是否允许）
    response2 = client.post("/users/", json=user_data)
    # 如果允许重复，应该是201；如果不允许，应该是400
    assert response2.status_code in [201, 400]


def test_delete_user():
    """测试删除用户"""
    # 先创建用户
    user_data = {
        "username": "deleteuser",
        "email": "delete@example.com"
    }
    create_response = client.post("/users/", json=user_data)
    user_id = create_response.json()["id"]

    # 删除用户
    delete_response = client.delete(f"/users/{user_id}")
    assert delete_response.status_code == 200

    # 验证用户已被删除
    get_response = client.get(f"/users/{user_id}")
    assert get_response.status_code == 404