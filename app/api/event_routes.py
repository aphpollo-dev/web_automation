from fastapi import APIRouter, HTTPException, status, Depends
from app.services.event_service import EventService
from app.models.prompt import Prompt
from app.models.event import Event
from app.models.pagination import PaginationParams, PaginatedResponse
import os

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

event_router = APIRouter(tags=["event"])

@event_router.get("/events", response_model=PaginatedResponse[Event])
async def list_events(pagination: PaginationParams = Depends()):
    events, total = await EventService.get_all_events(
        skip=(pagination.page - 1) * pagination.limit,
        limit=pagination.limit
    )
    if not events:
        raise HTTPException(status_code=404, detail="No events found")
    
    total_pages = (total + pagination.limit - 1) // pagination.limit
    return PaginatedResponse(
        items=events,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        total_pages=total_pages
    )

@event_router.get("/events/{ip_address}", response_model=PaginatedResponse[Event])
async def list_user_events(ip_address: str, pagination: PaginationParams = Depends()):
    events, total = await EventService.get_user_events(
        ip_address,
        skip=(pagination.page - 1) * pagination.limit,
        limit=pagination.limit
    )
    if not events:
        raise HTTPException(status_code=404, detail="No events found for this IP address")
    
    total_pages = (total + pagination.limit - 1) // pagination.limit
    return PaginatedResponse(
        items=events,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        total_pages=total_pages
    )

@event_router.delete("/events/{timestamp}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_event(timestamp: str):
    deleted = await EventService.delete_event(timestamp)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return

@event_router.get("/prompts", response_model=PaginatedResponse[Prompt])
async def list_prompts(pagination: PaginationParams = Depends()):
    prompts, total = await EventService.get_all_prompts(
        skip=(pagination.page - 1) * pagination.limit,
        limit=pagination.limit
    )
    if not prompts:
        raise HTTPException(status_code=404, detail="No events found")
    
    total_pages = (total + pagination.limit - 1) // pagination.limit
    return PaginatedResponse(
        items=prompts,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        total_pages=total_pages
    )
  
@event_router.get("/prompts/{ip_address}", response_model=PaginatedResponse[Prompt])
async def list_user_prompts(ip_address: str, pagination: PaginationParams = Depends()):
    prompts, total = await EventService.get_user_prompts(
        ip_address,
        skip=(pagination.page - 1) * pagination.limit,
        limit=pagination.limit
    )
    if not prompts:
        raise HTTPException(status_code=404, detail="No events found for this IP address")
    
    total_pages = (total + pagination.limit - 1) // pagination.limit
    return PaginatedResponse(
        items=prompts,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        total_pages=total_pages
    )

@event_router.delete("/prompts/{hash}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_event(hash: str):
    deleted = await EventService.delete_prompt(hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return

## test ollama embedding model

@event_router.get("/summary/{ip_address}")
async def get_summary(ip_address: str):
    prompts = await EventService.get_summary_event(ip_address)
    if not prompts:
            raise HTTPException(status_code=404, detail="No events found for this IP address")
    return prompts

@event_router.get("/reasoning/{id}")
async def get_reasoning(id: str):
    prompts = await EventService.get_reasoning_event(id)    
    if not prompts:
            raise HTTPException(status_code=404, detail="No events found for this IP address")
    return prompts
  

