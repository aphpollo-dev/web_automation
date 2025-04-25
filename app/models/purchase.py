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

class Purchase(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    product_url: str
    product_info: Dict[str, Any] = Field(default_factory=dict)
    config: Optional[Dict[str, Any]] = None
    status: str = PurchaseStatus.CREATED
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
                    "name": "Example Product",
                    "price": "99.99",
                    "currency": "USD",
                    "options": {
                        "size": ["S", "M", "L"],
                        "color": ["Red", "Blue", "Green"]
                    }
                },
                "config": {
                    "size": "M",
                    "color": "blue",
                    "quantity": 1
                },
                "status": "created",
                "steps": {},
                "created_at": "2023-11-15T12:00:00.000Z",
                "updated_at": "2023-11-15T12:00:00.000Z"
            }
        }
    }