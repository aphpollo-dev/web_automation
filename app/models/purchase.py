from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from bson import ObjectId
from app.models.user import PyObjectId

class PurchaseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    AUTOMATING = "automating"
    CHECKOUT = "checkout"
    PAYMENT = "payment"
    COMPLETED = "completed"
    FAILED = "failed"

class PurchaseStep(BaseModel):
    url: str
    status: PurchaseStatus
    html_snapshot: Optional[str] = None
    llm_analysis: Optional[Dict[str, Any]] = None
    automation_code: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Purchase(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    product_url: str
    current_url: str
    status: PurchaseStatus = PurchaseStatus.PENDING
    steps: List[PurchaseStep] = []
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
                "current_url": "https://example.com/product/123",
                "status": "pending",
                "steps": [],
                "created_at": "2023-11-15T12:00:00.000Z",
                "updated_at": "2023-11-15T12:00:00.000Z"
            }
        }
    } 