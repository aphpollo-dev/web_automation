from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from bson import ObjectId
from app.models.user import PyObjectId

class BillingAddress(BaseModel):
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str

class AddCardRequest(BaseModel):
    card_number: str
    card_holder: str
    expiry_month: str
    expiry_year: str
    cvv: str
    billing_address: BillingAddress
    is_default: bool = False

class Card(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    card_number: str
    card_holder: str
    expiry_month: str
    expiry_year: str
    cvv: str
    billing_address: BillingAddress
    is_default: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "card_number": "4111111111111111",
                "card_holder": "John Doe",
                "expiry_month": "12",
                "expiry_year": "2025",
                "cvv": "123",
                "billing_address": {
                    "address_line1": "123 Main St",
                    "city": "Anytown",
                    "state": "CA",
                    "postal_code": "12345",
                    "country": "USA"
                },
                "is_default": True
            }
        }
    } 