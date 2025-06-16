from typing import Dict, Any
import aiohttp
from loguru import logger
import json

class LeionAPIService:
    BASE_URL = "https://api.leion.com/api/rest"
    
    def __init__(self):
        self.oauth_headers = {
            'oauth_consumer_key': 'tiz8huv66inettug5lxuqz228lstbgf2',
            'oauth_consumer_secret': '3l1slw2tw15rsl3d5a8bgx1hxcqifru2',
            'oauth_secret': '3w915iorgsg4pr65s91uyxclm5h7fd5f',
            'oauth_token': 'l9f690o2hkks8zgq0in10tc74b6r9kb2'
        }

    async def update_order_status(self, order_id: int, status: str) -> Dict[str, Any]:
        """
        Update the order status in the Leion API
        
        Args:
            order_id (int): The order ID from the purchase config
            status (str): The current status of the order
            
        Returns:
            Dict[str, Any]: The API response
        """
        url = f"{self.BASE_URL}/stores/orders/{order_id}/showcase-order-status"
        
        # Define boundary for multipart form data
        boundary = "----WebKitFormBoundaryxl1QqWipdixaWZxJ"
        
        # Prepare the raw form data string
        form_data = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="status"\r\n\r\n'
            f'{status}\r\n'
            f'--{boundary}--\r\n'
        )
        
        # Set up headers with content type including boundary
        headers = {
            **self.oauth_headers,
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=form_data.encode('utf-8'),
                    headers=headers
                ) as response:
                    response_text = await response.text()
                    
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response. Raw response: {response_text}")
                        return {
                            "error": True,
                            "status_code": response.status,
                            "message": f"Invalid JSON response: {response_text[:200]}"
                        }
                    
                    if response.status != 200:
                        logger.error(f"Failed to update order status: {response_data}")
                        return {
                            "error": True,
                            "status_code": response.status,
                            "message": response_data.get("message", "Unknown error occurred")
                        }
                    
                    logger.info(f"Successfully updated order status for order {order_id}")
                    return response_data
                    
        except Exception as e:
            logger.error(f"Error updating order status: {str(e)}")
            return {
                "error": True,
                "status_code": 500,
                "message": f"Failed to communicate with Leion API: {str(e)}"
            } 