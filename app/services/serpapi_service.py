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
    ) -> tuple[List[Product], Optional[str]]:
        try:
            params = {
                "engine": "google_shopping",
                "q": product_name,
                "api_key": self.api_key,
                "num": num_results + 10,  # Increased to get more options for filtering
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
            
            if "shopping_results" not in results or not results["shopping_results"]:
                warning_msg = f"WARNING: No shopping results found for '{product_name}'. Please try a different search term."
                logger.warning(warning_msg)
                return [], warning_msg

            # Try different price ranges if no products found
            price_ranges = [
                (0.7, 1.3),  # Initial ±30% range
                (0.5, 1.5),  # Extended ±50% range
                (0, float('inf'))  # All prices if still no results
            ]

            all_products = []
            for item in results["shopping_results"]:
                try:
                    # Convert price string to float
                    price_str = item.get("price", "")
                    if not price_str:
                        continue
                    price_str = price_str.replace("$", "").replace(",", "")
                    price = float(price_str)
                    
                    # Try multiple possible keys for the product link
                    product_link = item.get("link") or item.get("product_link") or item.get("product_url") or item.get("url")
                    
                    if not product_link:
                        logger.warning(f"No link found for product: {item.get('title')}")
                        continue

                    # Handle thumbnails - if it's a list, take the first item
                    thumbnails = item.get("thumbnail", "")
                    if isinstance(thumbnails, list) and thumbnails:
                        thumbnail = thumbnails[0]
                    else:
                        thumbnail = thumbnails

                    product = Product(
                        name=item.get("title", ""),
                        price=price,
                        source=item.get("source", ""),
                        url=product_link,
                        thumbnail=thumbnail,
                        delivery=item.get("delivery", "")
                    )
                    all_products.append(product)
                except (ValueError, KeyError) as e:
                    logger.error(f"Error processing product: {e}")
                    continue

            if not all_products:
                warning_msg = f"WARNING: No valid products found for '{product_name}'. Please check the product details and try again."
                logger.warning(warning_msg)
                return [], warning_msg

            # Try each price range until we find enough products
            products = []
            for min_factor, max_factor in price_ranges:
                min_price = target_price * min_factor
                max_price = target_price * max_factor
                
                range_products = [
                    p for p in all_products 
                    if min_price <= p.price <= max_price
                ]
                
                if range_products:
                    logger.info(f"Found {len(range_products)} products in price range {min_price:.2f} - {max_price:.2f}")
                    products = range_products
                    break
            
            if not products:
                warning_msg = f"WARNING: No products found in the target price range for '{product_name}' (target: ${target_price:.2f}). Please try a different price range."
                logger.warning(warning_msg)
                # Return all products sorted by price proximity to target price
                products = sorted(all_products, key=lambda p: abs(p.price - target_price))
                return products[:num_results], warning_msg if not products else None

            return products[:num_results], None

        except Exception as e:
            error_msg = f"ERROR: Failed to search for products: {str(e)}"
            logger.error(error_msg)
            return [], error_msg 