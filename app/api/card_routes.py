from fastapi import APIRouter, HTTPException, Depends
from typing import List

from app.models.card import AddCardRequest, Card
from app.services.card_service import CardService
from app.db.mongodb import get_database
from app.models.pagination import PaginationParams, PaginatedResponse

card_router = APIRouter(prefix="/cards", tags=["cards"])

@card_router.post("", response_model=str)
async def add_card(
    card_data: AddCardRequest,
    db = Depends(get_database)
):
    """Add a new card."""
    try:
        card_service = CardService(db)
        card_id = await card_service.add_card(card_data)
        return card_id
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@card_router.get("", response_model=PaginatedResponse[Card])
async def get_cards(
    pagination: PaginationParams = Depends(),
    db = Depends(get_database)
):
    """Get all cards with pagination."""
    try:
        card_service = CardService(db)
        cards, total = await card_service.get_cards(
            skip=(pagination.page - 1) * pagination.limit,
            limit=pagination.limit
        )
        total_pages = (total + pagination.limit - 1) // pagination.limit
        
        return PaginatedResponse(
            items=cards,
            total=total,
            page=pagination.page,
            limit=pagination.limit,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@card_router.post("/{card_id}/default")
async def set_default_card(
    card_id: str,
    db = Depends(get_database)
):
    """Set a card as default."""
    try:
        card_service = CardService(db)
        success = await card_service.set_default_card(card_id)
        if not success:
            raise HTTPException(status_code=404, detail="Card not found")
        return {"message": "Default card updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@card_router.delete("/{card_id}")
async def delete_card(
    card_id: str,
    db = Depends(get_database)
):
    """Delete a card."""
    try:
        card_service = CardService(db)
        success = await card_service.delete_card(card_id)
        if not success:
            raise HTTPException(status_code=404, detail="Card not found")
        return {"message": "Card deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 