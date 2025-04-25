from pydantic import BaseModel
from datetime import datetime
from typing import Dict

class Prompt(BaseModel):
  hash: str
  ip_address: str
  url: str
  response: str
  reason: str
  timestamp: datetime
