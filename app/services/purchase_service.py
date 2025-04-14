import uuid
from datetime import datetime
from loguru import logger
from fastapi import BackgroundTasks
from typing import Dict, Any, Optional
from bson import ObjectId
import asyncio
from selenium.webdriver.common.by import By
from urllib.parse import urlparse, urljoin

from app.services.scraper import WebScraper
from app.models.purchase import Purchase, PurchaseStatus

class PurchaseService:
    def __init__(self, db):
        """Initialize the purchase service.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self.scraper = None
        logger.info("Purchase service initialized")
    
    async def _get_user_data(self, user_id: str) -> Dict[str, Any]:
        """Get user data for filling forms.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with user data structured for form filling
        """
        try:
            logger.info(f"Retrieving user data for user_id: {user_id}")
            
            # Get user data from database
            user_data = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user_data:
                raise ValueError(f"User data not found for user_id: {user_id}")
            
            # Get payment methods
            cards = await self.db.cards.find({}).to_list(length=None)
            if not cards:
                raise ValueError("No payment methods found")
            
            # Find default payment method
            default_payment = next((pm for pm in cards if pm.get('is_default')), cards[0])
            if not default_payment:
                raise ValueError("No default payment method found")
            
            # Get shipping address
            shipping_address = {}
            if user_data.get("shipping_addresses") and len(user_data.get("shipping_addresses")) > 0:
                shipping_address = user_data.get("shipping_addresses")[0]
            else:
                raise ValueError("No shipping address found for user")
            
            # Validate required fields
            required_shipping_fields = ["full_name", "address_line1", "city", "state", "postal_code", "country", "phone"]
            required_payment_fields = ["card_number", "expiry_month", "expiry_year", "cvv"]
            
            for field in required_shipping_fields:
                if field not in shipping_address or not shipping_address[field]:
                    raise ValueError(f"Missing required shipping address field: {field}")
            
            for field in required_payment_fields:
                if field not in default_payment or not default_payment[field]:
                    raise ValueError(f"Missing required payment method field: {field}")
            
            # Split name into first and last name
            name_parts = user_data.get("name", "").split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            
            # Create adapted user data for WebScraper
            adapted_user_data = {
                "email": user_data.get("email"),
                "first_name": first_name,
                "last_name": last_name,
                "phone": shipping_address.get("phone", ""),
                "address": {
                    "street": shipping_address.get("address_line1", ""),
                    "apt": shipping_address.get("address_line2", ""),
                    "city": shipping_address.get("city", ""),
                    "state": shipping_address.get("state", ""),
                    "zip": shipping_address.get("postal_code", ""),
                    "country": shipping_address.get("country", "")
                },
                "payment_method": {
                    "card_number": default_payment.get("card_number"),
                    "card_holder": default_payment.get("card_holder"),
                    "expiry_month": default_payment.get("expiry_month"),
                    "expiry_year": default_payment.get("expiry_year"),
                    "cvv": default_payment.get("cvv")
                }
            }
            
            # Log masked sensitive data
            masked_data = {
                "email": adapted_user_data["email"],
                "name": f"{adapted_user_data['first_name']} {adapted_user_data['last_name']}",
                "address": f"{adapted_user_data['address']['city']}, {adapted_user_data['address']['state']}",
                "payment": "****" + adapted_user_data["payment_method"]["card_number"][-4:] if adapted_user_data["payment_method"]["card_number"] else ""
            }
            logger.info(f"User data retrieved: {masked_data}")
            
            return adapted_user_data
        
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
            raise
    
    async def start_purchase_process(
        self, 
        product_url: str, 
        user_id: str,
        background_tasks: BackgroundTasks
    ) -> str:
        """Start the purchase process for a product.
        
        Args:
            product_url: URL of the product to purchase
            user_id: ID of the user making the purchase
            background_tasks: FastAPI background tasks
            
        Returns:
            ID of the created purchase task
        """
        try:
            # Create a new purchase record
            purchase = Purchase(
                user_id=ObjectId(user_id),
                product_url=product_url,
                current_url=product_url,
                status=PurchaseStatus.PENDING
            )
            
            # Insert into database
            result = await self.db.purchases.insert_one(purchase.model_dump(by_alias=True))
            purchase_id = str(result.inserted_id)
            
            # Start the purchase process in the background
            background_tasks.add_task(self.process_purchase, purchase_id=purchase_id)
            
            logger.info(f"Purchase process started for product URL: {product_url}, purchase ID: {purchase_id}")
            return purchase_id
        except Exception as e:
            logger.error(f"Failed to start purchase process: {e}")
            raise
    
    async def process_purchase(self, purchase_id: str) -> None:
        """Process a purchase task.
        
        Args:
            purchase_id: ID of the purchase task to process
        """
        try:
            # Get the purchase record
            purchase = await self.db.purchases.find_one({"_id": ObjectId(purchase_id)})
            if not purchase:
                logger.error(f"Purchase record not found: {purchase_id}")
                return
            
            # Extract user ID and product URL
            user_id = str(purchase["user_id"])
            product_url = purchase["product_url"]
            
            logger.info(f"Processing purchase {purchase_id} for user {user_id}")
            
            try:
                # Get user data
                user_data = await self._get_user_data(user_id)
                
                # Initialize scraper
                self.scraper = WebScraper(headless=False, user_data=user_data)
                await self.scraper.initialize_driver()
                
                # Update purchase status
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {"status": PurchaseStatus.PROCESSING.value}}
                )
                
                # Step 1: Navigate to product page
                logger.info(f"Navigating to product page: {product_url}")
                await self.scraper.scrape_page(product_url)
                
                # Log step 1 to database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps": {
                            "step1": {
                                "status": "info", 
                                "content": f"Navigating to product page: {product_url}"
                            }
                        }
                    }}
                )

                # Step 2: Fill the gaps
                logger.info("Filling the gaps and select the type")
                if not await self.scraper.fill_form_fields_and_select_type():
                    raise ValueError("Failed to fill form fields or select type")
                # Update step 2 in the database while preserving step 1
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step2": {
                            "status": "info", 
                            "content": "Filling the gaps and select the type"
                        }
                    }},
                    upsert=True
                )
                
                # Step 3: Click Add to Cart
                logger.info("Clicking 'Add to Cart' button")
                if not await self.scraper.find_and_click_button(['add_to_cart']):
                    raise ValueError("Failed to find 'Add to Cart' button")
                
                # Update step 3 in the database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step3": {
                            "status": "info", 
                            "content": "Clicking 'Add to Cart' button"
                        }
                    }},
                    upsert=True
                )
                
                # Wait for cart update
                await asyncio.sleep(2)
                
                # Step 4: Go to checkout
                parsed_url = urlparse(product_url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{'/'.join(parsed_url.path.split('/')[:-1])}"
                checkout_url = urljoin(base_url, "/checkout")
                logger.info(f"Navigating to checkout: {checkout_url}")
                current_url, _ = await self.scraper.scrape_page(checkout_url)
                
                # Update step 4 in the database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step4": {
                            "status": "info", 
                            "content": f"Navigating to checkout: {checkout_url}"
                        }
                    }}
                )
                
                # Step 5: Fill checkout form
                logger.info("Filling checkout form")
                field_types = await self.scraper.detect_form_fields()
                if field_types["shipping"] or field_types["billing"] or field_types["payment"]:
                    self.scraper.fill_form_fields(field_types)
                
                # Update step 5 in the database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step5": {
                            "status": "info", 
                            "content": "Filling checkout form with user information"
                        }
                    }}
                )
                
                # Step 6: Check and accept any agreement checkboxes
                await self._check_agreement_checkboxes()
                
                # Update step 6 in the database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step6": {
                            "status": "info", 
                            "content": "Checking and accepting agreement checkboxes"
                        }
                    }}
                )
                
                # Step 7: Click payment button
                logger.info("Clicking payment button")
                if not await self.scraper.find_and_click_button(['payment', 'complete_order', 'checkout']):
                    raise ValueError("Failed to find payment button")
                
                # Update step 7 in the database
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {
                        "steps.step7": {
                            "status": "info", 
                            "content": "Completing payment process"
                        }
                    }}
                )
                
                # Wait for payment processing
                await asyncio.sleep(3)
                
                # Check for payment errors
                current_url = self.scraper.driver.current_url
                
                # Check for error messages
                payment_error = await self._check_for_payment_errors()
                
                if payment_error:
                    logger.error(f"Payment error detected: {payment_error}")
                    await self.db.purchases.update_one(
                        {"_id": ObjectId(purchase_id)},
                        {"$set": {
                            "status": PurchaseStatus.FAILED.value,
                            "error": f"Payment error: {payment_error}",
                            "completed_at": datetime.utcnow()
                        }}
                    )
                    return
                
                # Success!
                result = await self.scraper.close_driver()
                if result == False:
                    logger.info("Purchase failed")
                    await self.db.purchases.update_one(
                        {"_id": ObjectId(purchase_id)},
                        {"$set": {
                            "status": PurchaseStatus.FAILED.value,
                            "error": "payment method declined",
                        }}
                    )
                else:
                    logger.info("Purchase completed successfully")
                    await self.db.purchases.update_one(
                        {"_id": ObjectId(purchase_id)},
                        {"$set": {
                            "status": PurchaseStatus.COMPLETED.value,
                            "completed_at": datetime.utcnow()
                        }}
                    )
                    
            except Exception as e:
                logger.error(f"Error during purchase process: {e}")
                await self.db.purchases.update_one(
                    {"_id": ObjectId(purchase_id)},
                    {"$set": {"status": PurchaseStatus.FAILED.value, "error": str(e)}}
                )
            
            finally:
                # Close the scraper
                if self.scraper:
                    await self.scraper.close_driver()
        
        except Exception as e:
            logger.error(f"Error in process_purchase: {e}")
    
    async def _check_for_payment_errors(self) -> Optional[str]:
        """Check for payment error alerts and messages."""
        try:
            # Common error selectors
            error_selectors = [
                "//div[contains(@class, 'error')]",
                "//div[contains(@class, 'alert')]",
                "//div[contains(@id, 'error')]",
                "//div[contains(@id, 'alert')]",
                "//p[contains(@class, 'error')]",
                "//span[contains(@class, 'error')]",
                "//*[contains(text(), 'payment declined')]",
                "//*[contains(text(), 'card declined')]",
                "//*[contains(text(), 'payment failed')]"
            ]
            
            # Check for visible error elements
            for selector in error_selectors:
                elements = self.scraper.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        error_text = element.text.strip()
                        if error_text:
                            return error_text
            
            # Check for JavaScript alerts
            try:
                alert = self.scraper.driver.switch_to.alert
                alert_text = alert.text
                logger.info(f"Alert detected: {alert_text}")
                
                # Check if it's an error alert
                error_keywords = [
                    "invalid payment", "payment failed", "payment error", 
                    "system error", "error", "failed", "declined"
                ]
                
                if any(keyword.lower() in alert_text.lower() for keyword in error_keywords):
                    # Accept the alert
                    alert.accept()
                    return alert_text
                
                # Accept the alert if it's not an error
                alert.accept()
            except:
                # No alert present
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for payment errors: {e}")
            return None
    
    async def _check_agreement_checkboxes(self) -> None:
        """Find and check any agreement or confirmation checkboxes on the page."""
        try:
            logger.info("Checking for agreement/confirmation checkboxes")
            
            # Common checkbox selectors related to agreements and confirmations
            checkbox_selectors = [
                # ID-based selectors
                "//input[@type='checkbox' and (contains(@id, 'agree') or contains(@id, 'consent') or contains(@id, 'confirm') or contains(@id, 'accept') or contains(@id, 'terms'))]",
                # Name-based selectors
                "//input[@type='checkbox' and (contains(@name, 'agree') or contains(@name, 'consent') or contains(@name, 'confirm') or contains(@name, 'accept') or contains(@name, 'terms'))]",
                # Class-based selectors
                "//input[@type='checkbox' and (contains(@class, 'agree') or contains(@class, 'consent') or contains(@class, 'confirm') or contains(@class, 'accept') or contains(@class, 'terms'))]",
                # Label-based selectors
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'terms')]/input[@type='checkbox']",
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'terms')]/preceding-sibling::input[@type='checkbox']",
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'terms')]/following-sibling::input[@type='checkbox']",
                # For checkboxes that are children of elements with privacy/terms related text
                "//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'terms')]//input[@type='checkbox']",
                # Cookie consent checkboxes
                "//input[@type='checkbox' and (contains(@id, 'cookie') or contains(@name, 'cookie') or contains(@class, 'cookie'))]",
                # General unchecked checkbox (less specific, try last)
                "//input[@type='checkbox' and not(@checked) and not(contains(@id, 'newsletter') or contains(@name, 'newsletter') or contains(@id, 'subscribe') or contains(@name, 'subscribe'))]"
            ]
            
            checkboxes_checked = 0
            for selector in checkbox_selectors:
                elements = self.scraper.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    try:
                        if element.is_displayed() and not element.is_selected():
                            # Get checkbox label for logging
                            try:
                                label_text = "Unknown"
                                label_id = element.get_attribute("id")
                                if label_id:
                                    label_elem = self.scraper.driver.find_element(By.XPATH, f"//label[@for='{label_id}']")
                                    if label_elem:
                                        label_text = label_elem.text.strip()
                                if not label_text or label_text == "Unknown":
                                    # Try parent or sibling text
                                    parent = self.scraper.driver.find_element(By.XPATH, f"//input[@id='{label_id}']/parent::*")
                                    if parent:
                                        label_text = parent.text.strip()
                            except:
                                pass
                            
                            # Scroll element into view
                            self.scraper.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            await asyncio.sleep(0.5)
                            
                            # Click the checkbox
                            logger.info(f"Checking agreement checkbox: {label_text}")
                            try:
                                self.scraper.driver.execute_script("arguments[0].click();", element)
                            except:
                                element.click()
                            
                            checkboxes_checked += 1
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Error checking checkbox: {e}")
            
            if checkboxes_checked > 0:
                logger.info(f"Checked {checkboxes_checked} agreement/confirmation checkboxes")
            else:
                logger.info("No agreement/confirmation checkboxes found or all were already checked")
                
        except Exception as e:
            logger.warning(f"Error checking agreement checkboxes: {e}")
            # Continue with the process even if there's an error checking checkboxes
    
    async def get_purchase_status(self, purchase_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a purchase task.
        
        Args:
            purchase_id: ID of the purchase task
            
        Returns:
            Purchase status information
        """
        try:
            purchase = await self.db.purchases.find_one({"_id": ObjectId(purchase_id)})
            if not purchase:
                return None
            
            # Convert ObjectId to string
            purchase["_id"] = str(purchase["_id"])
            purchase["user_id"] = str(purchase["user_id"])
            
            # Format dates
            for date_field in ["created_at", "updated_at", "completed_at"]:
                if purchase.get(date_field):
                    purchase[date_field] = purchase[date_field].isoformat()
            
            return purchase
        except Exception as e:
            logger.error(f"Failed to get purchase status: {e}")
            raise 