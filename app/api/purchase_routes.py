from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, HttpUrl, EmailStr, Field
from typing import Optional, Dict, Any, List
from app.services.purchase_service import PurchaseService
from app.db.mongodb import get_database
from bson import ObjectId
from app.models.purchase import Purchase, PurchaseStatus, ProductInfo, PurchaseMethod
from app.models.pagination import PaginationParams, PaginatedResponse
from datetime import datetime
from app.models.user import User
from enum import Enum
from loguru import logger

purchase_router = APIRouter(tags=["purchase"])
order_router = APIRouter(tags=["order"])

class UserInfo(BaseModel):
    email: str
    name: str
    shipping_addresses: list[Dict[str, str]]

class PurchaseRequest(BaseModel):
    product_url: HttpUrl
    user_info: UserInfo
    product_info: ProductInfo
    config: Optional[Dict[str, Any]] = None

class OrderRequest(BaseModel):
    purchase_id: str
    method: PurchaseMethod

class PurchaseResponse(BaseModel):
    message: str
    purchase_id: str

class OrderResponse(BaseModel):
    message: str
    status: str

class LegacyProductInfo(BaseModel):
    order_id: str = ""
    product_name: str = ""
    business_name: str = ""
    price: float = 0.0

class PurchaseWithUser(BaseModel):
    id: Optional[str] = Field(alias="_id")
    user_id: str
    user: Optional[Dict[str, Any]]
    product_url: str
    product_info: LegacyProductInfo = Field(default_factory=lambda: LegacyProductInfo())
    config: Optional[Dict[str, Any]] = None
    status: str = PurchaseStatus.CREATED
    method: str = PurchaseMethod.NONE
    steps: Dict[str, Dict[str, str]] = {}
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class BatchPurchaseRequest(BaseModel):
    purchases: List[PurchaseRequest]

class BatchPurchaseResponse(BaseModel):
    message: str
    purchases: List[Dict[str, str]]

@purchase_router.post("/purchases", response_model=BatchPurchaseResponse)
async def create_batch_purchases(
    request: BatchPurchaseRequest,
    db = Depends(get_database)
):
    """
    Create multiple purchase records at once.
    
    - **purchases**: List of purchase requests containing product_url, user_info, product_info, and optional config
    """
    try:
        purchase_results = []
        
        for purchase_request in request.purchases:
            # Save user information if not exists
            user = await db.users.find_one({"email": purchase_request.user_info.email})
            if not user:
                user_data = purchase_request.user_info.model_dump()
                result = await db.users.insert_one(user_data)
                user_id = result.inserted_id
            else:
                user_id = user["_id"]
            
            # Create purchase record using Purchase model
            purchase = Purchase(
                user_id=user_id,
                product_url=str(purchase_request.product_url),
                product_info=purchase_request.product_info,
                config=purchase_request.config,
                status="created",
                method=PurchaseMethod.NONE
            )
            
            result = await db.purchases.insert_one(purchase.model_dump(by_alias=True))
            purchase_results.append({
                "purchase_id": str(result.inserted_id),
                "product_url": str(purchase_request.product_url)
            })
        
        return {
            "message": f"Successfully created {len(purchase_results)} purchases",
            "purchases": purchase_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create batch purchases: {str(e)}")

@order_router.post("/order", response_model=OrderResponse)
async def start_order(
    request: OrderRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_database)
):
    """
    Start the purchase workflow for a previously created purchase.
    
    - **purchase_id**: ID of the purchase record
    - **method**: Method of the purchase (auto, manual, none)
    """
    # Get purchase record
    logger.info(f"Starting order for purchase_id: {request.purchase_id}")
    purchase = await db.purchases.find_one({"_id": ObjectId(request.purchase_id)})


    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase record not found")
    
    # Check if purchase is already completed or processing
    if purchase.get("status") in [PurchaseStatus.COMPLETED, PurchaseStatus.PROCESSING]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot start order: purchase is already in {purchase.get('status')} status"
        )
    
    # Update the method in the purchase record
    await db.purchases.update_one(
        {"_id": ObjectId(request.purchase_id)},
        {"$set": {"method": request.method}}
    )
    
    if request.method == PurchaseMethod.AUTO:
        # Create purchase service and start process in background for auto method
        purchase_service = PurchaseService(db)
        background_tasks.add_task(
            purchase_service.process_purchase,
            purchase_id=request.purchase_id
        )
        return {
            "message": "Purchase workflow started",
            "status": "processing"
        }
    elif request.method == PurchaseMethod.MANUAL:
        # For manual method, update status directly
        current_time = datetime.utcnow()
        await db.purchases.update_one(
            {"_id": ObjectId(request.purchase_id)},
            {
                "$set": {
                    "status": PurchaseStatus.COMPLETED,
                    "completed_at": current_time,
                    "steps": {
                        "manual": {
                            "status": "info",
                            "content": "This is manual purchase."
                        }
                    }
                }
            }
        )
        return {
            "message": "Manual purchase completed",
            "status": "completed"
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid purchase method")
        

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
    status: Optional[PurchaseStatus] = Query(None, description="Filter by purchase status"),
    method: Optional[PurchaseMethod] = Query(None, description="Filter by purchase method"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (e.g., created_at, updated_at)"),
    sort_order: Optional[SortOrder] = Query(SortOrder.DESC, description="Sort order (asc or desc)"),
    db = Depends(get_database)
):
    # Build the match condition
    match_condition = {}
    if status:
        match_condition["status"] = status
    if method:
        match_condition["method"] = method
    # Count total documents with the filter
    total = await db.purchases.count_documents(match_condition)
    
    # Build the sort condition - always default to DESC (-1)
    sort_condition = {"created_at": -1}  # Default sort
    if sort_by:
        sort_condition = {sort_by: -1}  # Default to DESC
        if sort_order == SortOrder.ASC:
            sort_condition[sort_by] = 1

    # Use aggregation pipeline to include user information
    pipeline = [
        {"$match": match_condition},
        {"$sort": sort_condition},
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
                "user": {"$arrayElemAt": ["$user", 0]},
                "product_info": {
                    "$mergeObjects": [
                        {
                            "order_id": "",
                            "product_name": "",
                            "business_name": "",
                            "price": 0.0
                        },
                        {"$ifNull": ["$product_info", {}]}
                    ]
                },
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

@purchase_router.get("/purchase/user/{email}", response_model=PaginatedResponse[PurchaseWithUser])
async def get_purchases_by_email(
    email: str,
    pagination: PaginationParams = Depends(),
    status: Optional[PurchaseStatus] = Query(None, description="Filter by purchase status"),
    method: Optional[PurchaseMethod] = Query(None, description="Filter by purchase method"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (e.g., created_at, updated_at)"),
    sort_order: Optional[SortOrder] = Query(SortOrder.ASC, description="Sort order (asc or desc)"),
    db = Depends(get_database)
):
    # Find user by email
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build the match condition
    match_condition = {"user_id": user["_id"]}
    if status:
        match_condition["status"] = status
    if method:
        match_condition["method"] = method

    # Count total documents with the filter
    total = await db.purchases.count_documents(match_condition)
    
    # Build the sort condition
    sort_condition = {"created_at": 1}  # Default sort
    if sort_by:
        sort_condition = {sort_by: 1}  # Default to ASC
        if sort_order == SortOrder.DESC:
            sort_condition[sort_by] = -1

    # Use aggregation pipeline to include user information
    pipeline = [
        {"$match": match_condition},
        {"$sort": sort_condition},
        {"$skip": (pagination.page - 1) * pagination.limit},
        {"$limit": pagination.limit},
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
                "user": {"$arrayElemAt": ["$user", 0]},
                "product_info": {
                    "$mergeObjects": [
                        {
                            "order_id": "",
                            "product_name": "",
                            "business_name": "",
                            "price": 0.0
                        },
                        {"$ifNull": ["$product_info", {}]}
                    ]
                },
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



