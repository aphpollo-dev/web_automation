from fastapi import APIRouter, HTTPException, Depends
from app.models.product import ProductSearchRequest, ProductRecommendation, Product
from app.services.serpapi_service import SerpApiService
from app.services.product_db_service import ProductDBService
from typing import Optional
from loguru import logger

router = APIRouter()

async def get_serpapi_service():
    return SerpApiService()

async def get_db_service():
    service = ProductDBService()
    await service.create_indexes()
    return service

@router.post("/api/product-recommendations", response_model=ProductRecommendation)
async def get_product_recommendations(
    request: ProductSearchRequest,
    serpapi_service: SerpApiService = Depends(get_serpapi_service),
    db_service: ProductDBService = Depends(get_db_service)
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
            request.product_name,
            request.price
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