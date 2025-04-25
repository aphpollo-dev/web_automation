from pydantic import BaseModel
from datetime import datetime
from bson import ObjectId
from typing import Dict

# Base model for Event
class EventBase(BaseModel):
  hash: str
  ip_address: str
  event_type: str
  details: Dict

# Model for Event creation (inherits from EventBase)
class EventCreate(EventBase):
    pass

# Model for stored Event (adds timestamp)
class Event(EventBase):
    timestamp: datetime
    class Config:
        from_attributes = True

