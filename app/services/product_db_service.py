from motor.motor_asyncio import AsyncIOMotorClient
from app.models.product import Product, ProductRecommendation
from typing import List, Optional
from datetime import datetime
from loguru import logger
from app.db.mongodb import get_database

class ProductDBService:
    def __init__(self):
        self.db = None
        self.collection = None

    async def initialize(self):
        if not self.db:
            self.db = await get_database()
            self.collection = self.db.recommendations

    @staticmethod
    async def get_instance():
        service = ProductDBService()
        await service.initialize()
        return service

    async def find_recommendations(self, product_name: str, price: float) -> Optional[ProductRecommendation]:
        # Search with case-insensitive product name and price range (±30%)
        result = await self.collection.find_one({
            "query_product.name": {"$regex": f"^{product_name}$", "$options": "i"},
            "query_product.price": {"$gte": price * 0.7, "$lte": price * 1.3}
        })
        
        if result:
            # Convert the MongoDB document to ProductRecommendation
            return ProductRecommendation(
                query_product=Product(**result["query_product"]),
                recommendations=[Product(**p) for p in result["recommendations"]],
                created_at=result["created_at"]
            )
        return None

    async def save_recommendations(self, query_product: Product, recommendations: List[Product]) -> None:
        recommendation = ProductRecommendation(
            query_product=query_product,
            recommendations=recommendations
        )
        
        # Store as dictionary
        await self.collection.insert_one(recommendation.dict())

    async def create_indexes(self) -> None:
        # Create indexes for efficient querying
        await self.collection.create_index([
            ("query_product.name", 1),
            ("query_product.price", 1)
        ]) 