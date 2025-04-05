from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from typing import Optional
from app.services.purchase_service import PurchaseService
from app.db.mongodb import get_database

purchase_router = APIRouter(tags=["purchase"])

class PurchaseRequest(BaseModel):
    product_url: HttpUrl
    user_token: str

class PurchaseResponse(BaseModel):
    message: str
    task_id: str
    status: str

@purchase_router.post("/purchase", response_model=PurchaseResponse)
async def start_purchase(
    request: PurchaseRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_database)
):
    """
    Start an automated purchase process for a product URL.
    
    - **product_url**: URL of the product to purchase
    - **user_token**: Authentication token for the user
    """
    try:
        # Validate user token
        user = await db.users.find_one({"token": request.user_token})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid user token")
        
        # Create purchase service
        purchase_service = PurchaseService(db)
        
        # Start purchase process in background
        task_id = await purchase_service.start_purchase_process(
            product_url=str(request.product_url),
            user_id=str(user["_id"]),
            background_tasks=background_tasks
        )
        
        return {
            "message": "Purchase process started",
            "task_id": task_id,
            "status": "processing"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start purchase process: {str(e)}")

@purchase_router.get("/purchase/{task_id}", response_model=dict)
async def get_purchase_status(task_id: str, db = Depends(get_database)):
    """
    Get the status of a purchase process.
    
    - **task_id**: ID of the purchase task
    """
    try:
        purchase_service = PurchaseService(db)
        status = await purchase_service.get_purchase_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Purchase task not found")
            
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get purchase status: {str(e)}") 