from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
from bson import ObjectId
from app.models.user import PyObjectId

class PurchaseStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    
class PurchaseMethod(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    NONE = "none"

class ProductInfo(BaseModel):
    order_id: str
    product_name: str
    business_name: str
    price: float

class Purchase(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    product_url: str
    product_info: ProductInfo = Field(
        default_factory=lambda: ProductInfo(
            order_id="",
            product_name="",
            business_name="",
            price=0.0
        )
    )
    config: Optional[Dict[str, Any]] = None
    status: str = PurchaseStatus.CREATED
    method: str = PurchaseMethod.NONE
    steps: Dict[str, Dict[str, str]] = {}
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "user_id": "60d5ec9af682dbd12a0a9fb9",
                "product_url": "https://example.com/product/123",
                "product_info": {
                    "order_id": "ORD123456",
                    "product_name": "Example Product",
                    "business_name": "Example Store",
                    "price": 99.99
                },
                "config": {
                    "size": "M",
                    "color": "blue",
                    "quantity": 1
                },
                "status": "created",
                "method": "none",
                "steps": {},
                "created_at": "2023-11-15T12:00:00.000Z",
                "updated_at": "2023-11-15T12:00:00.000Z"
            }
        }
    }