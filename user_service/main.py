from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import uuid

app = FastAPI(title="User Service", description="用户服务")

# 内存数据库（临时存储）
users_db = {}


# 数据模型
class UserCreate(BaseModel):
    username: str
    email: str
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str


class User(UserResponse):
    password: Optional[str] = None


# API 端点
@app.get("/")
async def root():
    return {
        "service": "User Service",
        "version": "1.0.0",
        "endpoints": [
            "/health - 健康检查",
            "/users/ - 获取所有用户",
            "/users/{id} - 获取单个用户",
            "/users/ - 创建用户 (POST)"
        ]
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "user_service"}


@app.get("/users/", response_model=List[UserResponse])
async def get_users():
    """获取所有用户"""
    return list(users_db.values())


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """获取单个用户"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]


@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate):
    """创建新用户"""
    # 生成唯一ID
    user_id = str(uuid.uuid4())

    # 创建用户对象
    new_user = User(
        id=user_id,
        username=user.username,
        email=user.email,
        password=user.password  # 实际应用中应该加密
    )

    # 保存到数据库
    users_db[user_id] = new_user

    return new_user


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """删除用户"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    del users_db[user_id]
    return {"message": "User deleted successfully"}


@app.put("/users/{user_id}")
async def update_user(user_id: str, user_update: UserCreate):
    """更新用户信息"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]
    if user_update.username:
        user.username = user_update.username
    if user_update.email:
        user.email = user_update.email
    if user_update.password:
        user.password = user_update.password

    users_db[user_id] = user
    return user
