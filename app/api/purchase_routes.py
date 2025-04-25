from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl, EmailStr, Field
from typing import Optional, Dict, Any, List
from app.services.purchase_service import PurchaseService
from app.db.mongodb import get_database
from bson import ObjectId
from app.models.purchase import Purchase, PurchaseStatus
from app.models.pagination import PaginationParams, PaginatedResponse
from datetime import datetime
from loguru import logger
from app.models.user import User

purchase_router = APIRouter(tags=["purchase"])
order_router = APIRouter(tags=["order"])

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

class PurchaseWithUser(BaseModel):
    id: Optional[str] = Field(alias="_id")
    user_id: str
    user: Optional[Dict[str, Any]]
    product_url: str
    product_info: Dict[str, Any] = {}
    config: Optional[Dict[str, Any]] = None
    status: str = PurchaseStatus.CREATED
    steps: Dict[str, Dict[str, str]] = {}
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

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

@order_router.post("/order", response_model=OrderResponse)
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
    
@purchase_router.get("/purchase", response_model=PaginatedResponse[PurchaseWithUser])
async def get_all_purchases(
    pagination: PaginationParams = Depends(),
    db = Depends(get_database)
):
    total = await db.purchases.count_documents({})
    
    # Use aggregation pipeline to include user information
    pipeline = [
        {
            "$skip": (pagination.page - 1) * pagination.limit
        },
        {
            "$limit": pagination.limit
        },
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "_id",
                "as": "user"
            }
        },
        {
            "$addFields": {
                "user": {
                    "$map": {
                        "input": "$user",
                        "as": "u",
                        "in": {
                            "$mergeObjects": [
                                "$$u",
                                {"_id": {"$toString": "$$u._id"}}
                            ]
                        }
                    }
                }
            }
        },
        {
            "$addFields": {
                "user": {"$arrayElemAt": ["$user", 0]},  # Get first (and only) user from array
                "product_info": {"$ifNull": ["$product_info", {}]},
                "_id": {"$toString": "$_id"},
                "user_id": {"$toString": "$user_id"}
            }
        }
    ]
    
    purchases = await db.purchases.aggregate(pipeline).to_list(length=None)
    
    # Convert any remaining ObjectId instances to strings
    def convert_objectid(obj):
        if isinstance(obj, dict):
            return {k: convert_objectid(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_objectid(item) for item in obj]
        elif isinstance(obj, ObjectId):
            return str(obj)
        return obj
    
    purchases = [convert_objectid(purchase) for purchase in purchases]
    
    logger.info(f"Purchases: {purchases}")
    
    total_pages = (total + pagination.limit - 1) // pagination.limit
    return PaginatedResponse(
        items=purchases,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        total_pages=total_pages
    )

@purchase_router.get("/purchase/email/{email}", response_model=PaginatedResponse[PurchaseWithUser])
async def get_purchases_by_email(
    email: str,
    pagination: PaginationParams = Depends(),
    db = Depends(get_database)
):
    """
    Get all purchases for a specific email.
    
    - **email**: Username/email of the user
    """
    try:
        # First find the user
        user = await db.users.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user_id = user["_id"]
        
        # Count total documents for this user
        total = await db.purchases.count_documents({"user_id": user_id})
        
        # Use aggregation pipeline to include user information
        pipeline = [
            {
                "$match": {"user_id": user_id}
            },
            {
                "$skip": (pagination.page - 1) * pagination.limit
            },
            {
                "$limit": pagination.limit
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user"
                }
            },
            {
                "$addFields": {
                    "user": {"$arrayElemAt": ["$user", 0]},
                    "product_info": {"$ifNull": ["$product_info", {}]},
                    "_id": {"$toString": "$_id"},
                    "user_id": {"$toString": "$user_id"}
                }
            }
        ]
        
        purchases = await db.purchases.aggregate(pipeline).to_list(length=None)
        
        # Convert any remaining ObjectId instances to strings
        def convert_objectid(obj):
            if isinstance(obj, dict):
                return {k: convert_objectid(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_objectid(item) for item in obj]
            elif isinstance(obj, ObjectId):
                return str(obj)
            return obj
        
        purchases = [convert_objectid(purchase) for purchase in purchases]
        
        total_pages = (total + pagination.limit - 1) // pagination.limit
        return PaginatedResponse(
            items=purchases,
            total=total,
            page=pagination.page,
            limit=pagination.limit,
            total_pages=total_pages
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get purchases: {str(e)}")

@purchase_router.delete("/purchase/{purchase_id}", status_code=204)
async def delete_purchase(
    purchase_id: str,
    db = Depends(get_database)
):
    """
    Delete a purchase record.
    
    - **purchase_id**: ID of the purchase to delete
    """
    try:
        result = await db.purchases.delete_one({"_id": ObjectId(purchase_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Purchase not found")
            
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete purchase: {str(e)}")



