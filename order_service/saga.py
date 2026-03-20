# order_service/saga.py
import httpx
import uuid
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class OrderSaga:
    """
    订单创建Saga流程：
    1. 预留库存（商品服务）
    2. （由调用方）创建订单记录
    3. 30分钟支付超时检查

    补偿机制：
    - 库存预留成功但订单创建失败 → 释放库存
    """

    def __init__(self, product_service_url: str, timeout: float = 10.0):
        self.product_service_url = product_service_url
        self.timeout = timeout
        self.saga_id = str(uuid.uuid4())

    async def execute(self, user_id: str, items: List[Dict], shipping_address: str) -> Dict:
        """
        执行Saga事务的前半部分：预留库存
        返回成功/失败，由调用方决定是否在本地数据库创建订单
        """
        try:
            # 预留所有库存
            reserved_stocks = []
            total_amount = 0

            for item in items:
                result = await self._reserve_stock(
                    item["product_id"],
                    item["quantity"]
                )
                if not result["success"]:
                    # 预留失败，回滚已预留的库存
                    await self._compensate_reservations(reserved_stocks)
                    return {
                        "success": False,
                        "error": f"Failed to reserve stock for product {item['product_id']}: {result.get('message')}",
                        "saga_id": self.saga_id
                    }

                reserved_stocks.append({
                    "product_id": item["product_id"],
                    "quantity": item["quantity"]
                })
                total_amount += result["price"] * item["quantity"]
                item["reserved_price"] = result["price"]

            # 库存预留成功，返回给调用方继续创建订单
            return {
                "success": True,
                "order_id": str(uuid.uuid4()),  # 生成订单ID，由调用方使用
                "total_amount": total_amount,
                "reserved_items": reserved_stocks,
                "saga_id": self.saga_id,
                "items_with_price": items  # 带上价格信息
            }

        except Exception as e:
            logger.error(f"Saga {self.saga_id}: Unexpected error: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "saga_id": self.saga_id
            }

    async def _reserve_stock(self, product_id: str, quantity: int) -> Dict:
        """调用商品服务预留库存"""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.product_service_url}/products/{product_id}/stock/reserve",
                    json={"quantity": quantity},  # 匹配Pydantic模型
                    timeout=self.timeout
                )
                return resp.json()
            except httpx.TimeoutException:
                return {"success": False, "message": "Timeout reserving stock"}
            except Exception as e:
                return {"success": False, "message": f"Error: {str(e)}"}

    async def _release_stock(self, product_id: str, quantity: int) -> Dict:
        """调用商品服务释放库存（补偿操作）"""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.product_service_url}/products/{product_id}/stock/release",
                    json={"quantity": quantity},  # 匹配Pydantic模型
                    timeout=self.timeout
                )
                return resp.json()
            except Exception as e:
                logger.error(f"Failed to release stock for {product_id}: {str(e)}")
                return {"success": False, "message": str(e)}

    async def _compensate_reservations(self, reserved_stocks: List[Dict]):
        """补偿：释放所有已预留的库存"""
        for stock in reserved_stocks:
            await self._release_stock(stock["product_id"], stock["quantity"])