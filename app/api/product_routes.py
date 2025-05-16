from fastapi import APIRouter, HTTPException, Depends
from app.models.product import ProductSearchRequest, ProductRecommendation, Product
from app.services.serpapi_service import SerpApiService
from app.services.product_db_service import ProductDBService
from app.db.mongodb import get_database
from typing import Optional
from loguru import logger

product_router = APIRouter(tags=["Recommendation"])

async def get_serpapi_service():
    return SerpApiService()

async def get_db_service():
    return await ProductDBService.get_instance()

@product_router.post("/product-recommendations", response_model=ProductRecommendation)
async def get_product_recommendations(
    request: ProductSearchRequest,
    serpapi_service: SerpApiService = Depends(get_serpapi_service),
    db_service: ProductDBService = Depends(get_db_service),
    db = Depends(get_database)
):
    try:
        # First, check if we have recommendations in the database
        existing_recommendation = await db_service.find_recommendations(
            request.product_name,
            request.price
        )
        
        if existing_recommendation:
            logger.info(f"Found existing recommendations for {request.product_name}")
            return existing_recommendation
            
        # If not found in DB, search using SerpApi
        recommendations = await serpapi_service.search_products(
            product_name=request.product_name,
            target_price=request.price,
            state=request.state,
            city=request.city
        )
        
        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail="No product recommendations found"
            )
            
        # Create query product
        query_product = Product(
            name=request.product_name,
            price=request.price,
            source="user_input"
        )
        
        # Save to database
        await db_service.save_recommendations(query_product, recommendations)
        
        return ProductRecommendation(
            query_product=query_product,
            recommendations=recommendations
        )
        
    except Exception as e:
        logger.error(f"Error getting product recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 