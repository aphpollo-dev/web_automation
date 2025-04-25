from pydantic import BaseModel
from typing import TypeVar, Generic, List

T = TypeVar('T')

class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 10

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int
    total_pages: int 