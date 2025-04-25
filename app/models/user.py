from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, Annotated, ClassVar, List
from datetime import datetime
from bson import ObjectId
import json

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema_generator, _field_schema):
        return {"type": "string"}

class ShippingAddress(BaseModel):
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str
    phone: str

class User(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    email: EmailStr
    name: str  # Will be split into first_name and last_name in purchase_service
    shipping_addresses: list[ShippingAddress]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "email": "Customer@example.com",
                "name": "John Doe",  # Will be split into first_name and last_name
                "shipping_addresses": [
                    {
                        "full_name": "John Doe",
                        "address_line1": "123 Main St",
                        "city": "Anytown",
                        "state": "CA",
                        "postal_code": "12345",
                        "country": "USA",
                        "phone": "555-123-4567"
                    }
                ]
            }
        }
    } 