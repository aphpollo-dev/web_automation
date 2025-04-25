from fastapi import APIRouter, status, HTTPException, Body
from app.services.event_service import EventService
from app.models.event import EventCreate, Event

input_router = APIRouter(tags=["input"])


@input_router.post("/events", response_model=Event, status_code=status.HTTP_201_CREATED)
async def create_event(event: EventCreate):
    if event.event_type == "close":
        insert_event = await EventService.save_event(event)
        prompt = await EventService.get_prompt_event(event.hash)
        print("close event occur.", prompt)
        return insert_event
    else:
        return await EventService.save_event(event)

@input_router.post("/test")
async def test(data: dict = Body(...)):
    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    prompts = await EventService.get_test(url)
    if not prompts:
        raise HTTPException(status_code=404, detail="No events found")
    
    return prompts