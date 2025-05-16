from serpapi import GoogleSearch
import os
from typing import List, Optional
from app.models.product import Product
from loguru import logger

class SerpApiService:
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_API_KEY")
        if not self.api_key:
            raise ValueError("SERPAPI_API_KEY environment variable is not set")

    async def search_products(
        self, 
        product_name: str, 
        target_price: float, 
        num_results: int = 3, 
        state: Optional[str] = None,  # US state (e.g., "CA", "NY")
        city: Optional[str] = None    # US city (e.g., "Los Angeles", "New York")
    ) -> List[Product]:
        try:
            params = {
                "engine": "google_shopping",
                "q": product_name,
                "api_key": self.api_key,
                "num": num_results + 5,  # Fetch extra results to filter by price
                "gl": "us",              # Google location parameter for US
                "hl": "en"              # Language parameter
            }

            # Add location parameters if state is provided
            if state:
                location = state
                if city:
                    location = f"{city}, {state}, United States"
                else:
                    location = f"{state}, United States"
                params["location"] = location
  
            search = GoogleSearch(params)
            results = search.get_dict()
            
            if "shopping_results" not in results:
                logger.warning(f"No shopping results found for {product_name}")
                return []

            products = []
            for item in results["shopping_results"]:
                try:
                    # Convert price string to float
                    price_str = item.get("price", "").replace("$", "").replace(",", "")
                    price = float(price_str)
                    logger.info(f"info: {item}")
                    
                    # Filter products within 30% price range of target price
                    if 0.7 * target_price <= price <= 1.3 * target_price:
                        # Try multiple possible keys for the product link
                        product_link = item.get("link") or item.get("product_link") or item.get("product_url") or item.get("url")
                        
                        if not product_link:
                            logger.warning(f"No link found for product: {item.get('title')}")
                            continue

                        product = Product(
                            name=item.get("title", ""),
                            price=price,
                            source=item.get("source", ""),
                            url=product_link,
                            thumbnail=item.get("thumbnails", ""),
                            delivery=item.get("delivery", "")
                        )
                        products.append(product)
                except (ValueError, KeyError) as e:
                    logger.error(f"Error processing product: {e}")
                    continue

                if len(products) >= num_results:
                    break

            return products[:num_results]

        except Exception as e:
            logger.error(f"Error searching products: {e}")
            raise 