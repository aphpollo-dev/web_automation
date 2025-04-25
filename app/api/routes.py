from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any
from app.services.purchase_service import PurchaseService
from app.db.mongodb import get_database
from bson import ObjectId
from app.models.purchase import Purchase

purchase_router = APIRouter(tags=["purchase"])

class UserInfo(BaseModel):
    email: str
    name: str
    shipping_addresses: list[Dict[str, str]]

class PurchaseRequest(BaseModel):
    product_url: HttpUrl
    user_info: UserInfo
    config: Optional[Dict[str, Any]] = None

class OrderRequest(BaseModel):
    purchase_id: str

class PurchaseResponse(BaseModel):
    message: str
    purchase_id: str

class OrderResponse(BaseModel):
    message: str
    status: str

@purchase_router.post("/purchase", response_model=PurchaseResponse)
async def create_purchase(
    request: PurchaseRequest,
    db = Depends(get_database)
):
    """
    Create a purchase record with user and product information.
    
    - **product_url**: URL of the product to purchase
    - **user_info**: User information including email, name, and shipping address
    - **config**: Optional product details
    """
    try:
        # Save user information if not exists
        user = await db.users.find_one({"email": request.user_info.email})
        if not user:
            user_data = request.user_info.model_dump()
            result = await db.users.insert_one(user_data)
            user_id = result.inserted_id
        else:
            user_id = user["_id"]
        
        # Create purchase record using Purchase model
        purchase = Purchase(
            user_id=user_id,
            product_url=str(request.product_url),
            product_info={},  # This should be populated with actual product info
            config=request.config,
            status="created"
        )
        
        result = await db.purchases.insert_one(purchase.model_dump(by_alias=True))
        
        return {
            "message": "Purchase record created",
            "user_id": str(user_id),
            "purchase_id": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create purchase record: {str(e)}")

@purchase_router.post("/order", response_model=OrderResponse)
async def start_order(
    request: OrderRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_database)
):
    """
    Start the purchase workflow for a previously created purchase.
    
    - **purchase_id**: ID of the purchase record
    """
    try:
        # Get purchase record
        purchase = await db.purchases.find_one({"_id": ObjectId(request.purchase_id)})
        if not purchase:
            raise HTTPException(status_code=404, detail="Purchase record not found")
        
        # Create purchase service
        purchase_service = PurchaseService(db)
        
        # Start purchase process in background
        background_tasks.add_task(
            purchase_service.process_purchase,
            purchase_id=request.purchase_id
        )
        
        return {
            "message": "Purchase workflow started",
            "status": "processing"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start purchase workflow: {str(e)}")

@purchase_router.get("/purchase/{purchase_id}", response_model=dict)
async def get_purchase_status(purchase_id: str, db = Depends(get_database)):
    """
    Get the status of a purchase process.
    
    - **purchase_id**: ID of the purchase record
    """
    try:
        purchase_service = PurchaseService(db)
        status = await purchase_service.get_purchase_status(purchase_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Purchase record not found")
            
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get purchase status: {str(e)}")