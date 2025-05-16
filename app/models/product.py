from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Product(BaseModel):
    name: str
    price: float
    source: str
    url: Optional[str] = None
    thumbnail: Optional[str] = None
    delivery: Optional[str] = None

class ProductRecommendation(BaseModel):
    query_product: Product
    recommendations: List[Product]
    created_at: datetime = datetime.utcnow()

class ProductSearchRequest(BaseModel):
    product_name: str
    price: float
    state: Optional[str] = None  # US state (e.g., "CA", "NY")
    city: Optional[str] = None   # US city (e.g., "Los Angeles", "New York") 