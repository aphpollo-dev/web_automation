from loguru import logger
import asyncio
import json
from typing import Dict, Any, Optional, Tuple, List, Union
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from urllib.parse import urlparse, urljoin

class PlaywrightScraper:
    def __init__(self, headless: bool = True, user_data: Optional[Dict[str, Any]] = None):
        """Initialize the Playwright scraper.
        
        Args:
            headless: Whether to run the browser in headless mode
            user_data: User data for filling forms (billing, shipping, payment info)
        """
        self.headless = headless
        self.user_data = user_data or self._get_default_user_data()
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
    
    def _get_default_user_data(self) -> Dict[str, Any]:
        """Get default user data for filling forms.
        
        Returns:
            Dictionary with default user data
        """
        return {
            "email": "user@example.com",
            "phone": "1234567890",
            "first_name": "John",
            "last_name": "Doe",
            "address": {
                "street": "123 Main St",
                "apt": "Apt 4B",
                "city": "New York",
                "state": "NY",
                "zip": "10001",
                "country": "United States"
            },
            "payment_method": {
                "card_number": "4111111111111111",
                "expiry_month": "12",
                "expiry_year": "2025",
                "cvv": "123"
            }
        }
    
    def set_user_data(self, user_data: Dict[str, Any]) -> None:
        """Set user data for filling forms.
        
        Args:
            user_data: User data dictionary
        """
        self.user_data = user_data
        logger.info("User data updated for form filling")
    
    async def initialize_browser(self):
        """Initialize the Playwright browser."""
        try:
            self.playwright = await async_playwright().start()
            
            # Use Chromium for better compatibility
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ]
            )
            
            # Create a new context with viewport size
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            
            # Create a new page
            self.page = await self.context.new_page()
            
            # Set default timeout for all operations
            self.page.set_default_timeout(30000)  # 30 seconds
            
            logger.info("Playwright browser initialized")
            return self.page
        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser: {e}")
            raise
    
    async def close_browser(self):
        """Close the Playwright browser."""
        try:
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            logger.info("Playwright browser closed")
        except Exception as e:
            logger.error(f"Error closing Playwright browser: {e}")
    
    async def scrape_page(self, url: str) -> Tuple[str, str]:
        """Scrape a web page and return content.
        
        Args:
            url: URL of the page to scrape
            
        Returns:
            Tuple of (current_url, body_content)
        """
        try:
            if not self.page:
                await self.initialize_browser()
            
            logger.info(f"Scraping page: {url}")
            
            # Navigate to the URL
            response = await self.page.goto(url, wait_until="networkidle")
            
            # Wait for page to be fully loaded
            await self.page.wait_for_load_state("networkidle")
            
            # Get the current URL (might have changed due to redirects)
            current_url = self.page.url
            
            # Check for agreement/consent checkboxes and click them
            await self.check_agreement_checkboxes()
            
            # Extract the body element to reduce token usage
            body_html = await self.page.evaluate("document.body.outerHTML")
            
            logger.info(f"Successfully scraped page: {current_url}")
            return current_url, body_html
        except Exception as e:
            logger.error(f"Failed to scrape page {url}: {e}")
            raise
    
    async def check_agreement_checkboxes(self) -> None:
        """Find and check any agreement or confirmation checkboxes on the page."""
        try:
            logger.info("Checking for agreement/confirmation checkboxes")
            
            # Common checkbox selectors related to agreements and confirmations
            checkbox_selectors = [
                # ID-based selectors
                "input[type='checkbox'][id*='agree'], input[type='checkbox'][id*='consent'], input[type='checkbox'][id*='confirm'], input[type='checkbox'][id*='accept'], input[type='checkbox'][id*='terms']",
                # Name-based selectors
                "input[type='checkbox'][name*='agree'], input[type='checkbox'][name*='consent'], input[type='checkbox'][name*='confirm'], input[type='checkbox'][name*='accept'], input[type='checkbox'][name*='terms']",
                # Class-based selectors
                "input[type='checkbox'][class*='agree'], input[type='checkbox'][class*='consent'], input[type='checkbox'][class*='confirm'], input[type='checkbox'][class*='accept'], input[type='checkbox'][class*='terms']",
                # Cookie consent checkboxes
                "input[type='checkbox'][id*='cookie'], input[type='checkbox'][name*='cookie'], input[type='checkbox'][class*='cookie']",
                # General unchecked checkbox (less specific, try last)
                "input[type='checkbox']:not(:checked):not([id*='newsletter']):not([name*='newsletter']):not([id*='subscribe']):not([name*='subscribe'])"
            ]
            
            checkboxes_checked = 0
            
            for selector in checkbox_selectors:
                # Find all checkboxes matching the selector
                checkboxes = await self.page.query_selector_all(selector)
                
                for checkbox in checkboxes:
                    # Check if checkbox is visible and not checked
                    is_visible = await checkbox.is_visible()
                    is_checked = await checkbox.is_checked()
                    
                    if is_visible and not is_checked:
                        # Try to get checkbox label text for logging
                        label_text = "Unknown"
                        try:
                            # Get the ID of the checkbox
                            checkbox_id = await checkbox.get_attribute("id")
                            if checkbox_id:
                                # Try to find associated label
                                label = await self.page.query_selector(f"label[for='{checkbox_id}']")
                                if label:
                                    label_text = await label.inner_text()
                        except:
                            pass
                        
                        # Scroll checkbox into view
                        await checkbox.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        
                        # Click the checkbox
                        logger.info(f"Checking agreement checkbox: {label_text}")
                        await checkbox.click()
                        
                        checkboxes_checked += 1
                        await asyncio.sleep(0.5)
            
            if checkboxes_checked > 0:
                logger.info(f"Checked {checkboxes_checked} agreement/confirmation checkboxes")
            else:
                logger.info("No agreement/confirmation checkboxes found or all were already checked")
                
        except Exception as e:
            logger.warning(f"Error checking agreement checkboxes: {e}")
            # Continue with the process even if there's an error checking checkboxes
    
    async def find_and_click_button(self, button_types: List[str]) -> bool:
        """Find and click a button based on type.
        
        Args:
            button_types: List of button types to look for (e.g., ['add_to_cart', 'checkout'])
            
        Returns:
            True if a button was found and clicked, False otherwise
        """
        try:
            if not self.page:
                raise ValueError("Playwright page not initialized")
            
            logger.info(f"Looking for buttons of types: {button_types}")
            
            # Common button selectors based on type
            button_selectors = {
                'add_to_cart': [
                    "button:has-text(/add to cart/i)",
                    "a:has-text(/add to cart/i)",
                    "input[value*='add to cart' i]",
                    "[id*='add-to-cart'], [class*='add-to-cart']",
                    "[id*='addtocart'], [class*='addtocart']"
                ],
                'checkout': [
                    "button:has-text(/checkout/i)",
                    "a:has-text(/checkout/i)",
                    "input[value*='checkout' i]",
                    "[id*='checkout'], [class*='checkout']",
                    "button:has-text(/proceed to/i)",
                    "a:has-text(/proceed to/i)"
                ],
                'view_cart': [
                    "button:has-text(/view cart/i)",
                    "a:has-text(/view cart/i)",
                    "input[value*='view cart' i]",
                    "[id*='view-cart'], [class*='view-cart']",
                    "[id*='viewcart'], [class*='viewcart']",
                    "a[href*='cart']"
                ],
                'payment': [
                    "button:has-text(/payment/i)",
                    "a:has-text(/payment/i)",
                    "button:has-text(/continue/i)",
                    "a:has-text(/continue/i)",
                    "[id*='payment'], [class*='payment']"
                ],
                'complete_order': [
                    "button:has-text(/place order/i)",
                    "button:has-text(/complete order/i)",
                    "button:has-text(/submit order/i)",
                    "a:has-text(/place order/i)",
                    "input[value*='place order' i]",
                    "[id*='place-order'], [class*='place-order']",
                    "[id*='placeorder'], [class*='placeorder']"
                ]
            }
            
            # Check if we're looking for payment-related buttons
            is_payment_button = any(btn_type in ['payment', 'complete_order'] for btn_type in button_types)
            
            # Try each button type
            for button_type in button_types:
                if button_type not in button_selectors:
                    logger.warning(f"Unknown button type: {button_type}")
                    continue
                
                # Try each selector for this button type
                for selector in button_selectors[button_type]:
                    try:
                        logger.info(f"Trying to find {button_type} button with selector: {selector}")
                        
                        # Find all elements matching the selector
                        elements = await self.page.query_selector_all(selector)
                        
                        # Filter for visible elements
                        visible_elements = []
                        for element in elements:
                            if await element.is_visible():
                                visible_elements.append(element)
                        
                        if visible_elements:
                            logger.info(f"Found {len(visible_elements)} visible {button_type} buttons")
                            
                            # Try to click each visible element
                            for element in visible_elements:
                                try:
                                    # Scroll element into view
                                    await element.scroll_into_view_if_needed()
                                    await asyncio.sleep(0.5)
                                    
                                    # Try to get element text for logging
                                    try:
                                        element_text = await element.inner_text() or await element.get_attribute("value") or "[No text]"
                                        logger.info(f"Clicking {button_type} button: '{element_text}'")
                                    except:
                                        logger.info(f"Clicking {button_type} button (text unavailable)")
                                    
                                    # Click the element
                                    await element.click()
                                    
                                    # Wait for potential page load
                                    await asyncio.sleep(3)
                                    await self.page.wait_for_load_state("networkidle")
                                    
                                    # If this is a payment-related button, check for error alerts
                                    if is_payment_button:
                                        payment_error = await self._check_for_payment_errors()
                                        if payment_error:
                                            logger.error(f"Payment error detected: {payment_error}")
                                            return True
                                    
                                    logger.info(f"Successfully clicked {button_type} button")
                                    return True
                                except Exception as e:
                                    logger.warning(f"Could not click element: {e}")
                                    continue
                    except Exception as e:
                        logger.warning(f"Error finding {button_type} button with selector {selector}: {e}")
                        continue
            
            logger.warning(f"No {' or '.join(button_types)} buttons found or clickable")
            return False
        
        except Exception as e:
            logger.error(f"Error in find_and_click_button: {e}")
            return False
    
    async def _check_for_payment_errors(self) -> Optional[str]:
        """Check for payment error alerts and messages."""
        try:
            # Common error selectors
            error_selectors = [
                "div.error, div.alert",
                "p.error, span.error",
                "text=/payment declined/i",
                "text=/card declined/i",
                "text=/payment failed/i",
                "text=/transaction failed/i",
                "text=/invalid card/i"
            ]
            
            # Check for visible error elements
            for selector in error_selectors:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        error_text = await element.inner_text()
                        if error_text:
                            return error_text
            
            # Check for dialog alerts
            try:
                dialog_message = await self.page.evaluate("window.paymentErrorDetected") 
                if dialog_message:
                    return dialog_message
            except:
                pass
            
            # Set up dialog handler for future alerts
            async def handle_dialog(dialog):
                message = dialog.message
                logger.info(f"Dialog detected: {message}")
                
                # Check if it's an error dialog
                error_keywords = [
                    "invalid payment", "payment failed", "payment error", 
                    "system error", "error", "failed", "declined"
                ]
                
                if any(keyword.lower() in message.lower() for keyword in error_keywords):
                    logger.error(f"Payment error dialog detected: {message}")
                    await self.page.evaluate(f"window.paymentErrorDetected = '{message}'")
                
                await dialog.accept()
            
            self.page.on("dialog", handle_dialog)
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for payment errors: {e}")
            return None
    
    async def detect_form_fields(self) -> Dict[str, List[str]]:
        """Detect form fields on the page to determine if it's a checkout or payment page.
        
        Returns:
            Dictionary with field types and their selectors
        """
        try:
            if not self.page:
                raise ValueError("Playwright page not initialized")
            
            logger.info("Detecting form fields on the page")
            
            field_types = {
                "billing": [],
                "shipping": [],
                "payment": [],
                "contact": []
            }
            
            # This requires JavaScript execution in the browser
            field_detection_script = """
            () => {
                const fieldTypes = {
                    billing: [],
                    shipping: [],
                    payment: [],
                    contact: []
                };
                
                // Common field identifiers
                const fieldIdentifiers = {
                    billing: ["billing", "bill to"],
                    shipping: ["shipping", "ship to", "delivery"],
                    payment: ["payment", "card", "credit", "cvv", "cvc", "expir"],
                    contact: ["email", "phone", "contact"]
                };
                
                // Find all input fields
                const inputElements = document.querySelectorAll("input, select, textarea");
                
                for (const element of inputElements) {
                    // Get element attributes
                    const elementId = element.id || "";
                    const elementName = element.name || "";
                    const elementClass = element.className || "";
                    const elementPlaceholder = element.placeholder || "";
                    
                    // Try to find associated label
                    let elementLabel = "";
                    if (elementId) {
                        const labelFor = document.querySelector(`label[for="${elementId}"]`);
                        if (labelFor) {
                            elementLabel = labelFor.textContent.trim();
                        }
                    }
                    
                    // Combine all text for matching
                    const allText = (elementId + " " + elementName + " " + elementClass + " " + 
                                   elementPlaceholder + " " + elementLabel).toLowerCase();
                    
                    // Find parent elements for context
                    let parentElement = element.parentElement;
                    let parentText = "";
                    
                    for (let i = 0; i < 3 && parentElement; i++) {
                        parentText += " " + (parentElement.textContent || "");
                        parentElement = parentElement.parentElement;
                    }
                    
                    parentText = parentText.toLowerCase();
                    
                    // Check which type of field it is
                    for (const [fieldType, identifiers] of Object.entries(fieldIdentifiers)) {
                        for (const identifier of identifiers) {
                            if (allText.includes(identifier.toLowerCase()) || parentText.includes(identifier.toLowerCase())) {
                                const fieldSelector = `#${elementId}, [name="${elementName}"]`;
                                if (!fieldTypes[fieldType].includes(fieldSelector)) {
                                    fieldTypes[fieldType].push(fieldSelector);
                                }
                                break;
                            }
                        }
                    }
                }
                
                return fieldTypes;
            }
            """
            
            # Execute the script
            detected_fields = await self.page.evaluate(field_detection_script)
            
            # Copy the results
            for field_type, selectors in detected_fields.items():
                field_types[field_type] = selectors
            
            # Log results
            for field_type, selectors in field_types.items():
                if selectors:
                    logger.info(f"Found {len(selectors)} {field_type} fields")
                else:
                    logger.info(f"No {field_type} fields found")
            
            return field_types
        
        except Exception as e:
            logger.error(f"Error detecting form fields: {e}")
            return {"billing": [], "shipping": [], "payment": [], "contact": []}
    
    async def fill_form_fields(self, field_types: Dict[str, List[str]]) -> bool:
        """Fill form fields with user data.
        
        Args:
            field_types: Dictionary with field types and selectors
            
        Returns:
            True if fields were filled, False otherwise
        """
        try:
            if not self.page:
                logger.error("Playwright page not initialized")
                return False
            
            logger.info("Filling form fields with user data")
            
            # Prepare user data for JavaScript
            user_data_json = json.dumps(self.user_data)
            
            # Define script to fill form fields
            fill_script = f"""
            async (userData) => {{
                let filledFields = 0;
                
                // Helper function to fill an input field
                async function fillField(selector, value) {{
                    const field = document.querySelector(selector);
                    if (field) {{
                        if (field.tagName === 'SELECT') {{
                            // Handle select fields
                            const options = field.options;
                            for (let i = 0; i < options.length; i++) {{
                                const optionText = options[i].text.toLowerCase();
                                const optionValue = options[i].value.toLowerCase();
                                const valueToMatch = value.toLowerCase();
                                
                                if (optionText.includes(valueToMatch) || optionValue.includes(valueToMatch)) {{
                                    field.selectedIndex = i;
                                    field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    filledFields++;
                                    return true;
                                }}
                            }}
                            return false;
                        }} else {{
                            // Handle regular input fields
                            field.value = value;
                            field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            filledFields++;
                            return true;
                        }}
                    }}
                    return false;
                }}
                
                // Fill billing fields
                for (const selector of {json.dumps(field_types['billing'])}) {{
                    // Try common billing field names
                    if (selector.toLowerCase().includes('first') || selector.toLowerCase().includes('name') && !selector.toLowerCase().includes('last')) {{
                        await fillField(selector, userData.first_name);
                    }} else if (selector.toLowerCase().includes('last')) {{
                        await fillField(selector, userData.last_name);
                    }} else if (selector.toLowerCase().includes('address') || selector.toLowerCase().includes('street')) {{
                        await fillField(selector, userData.address.street);
                    }} else if (selector.toLowerCase().includes('address2') || selector.toLowerCase().includes('apt')) {{
                        await fillField(selector, userData.address.apt);
                    }} else if (selector.toLowerCase().includes('city')) {{
                        await fillField(selector, userData.address.city);
                    }} else if (selector.toLowerCase().includes('state') || selector.toLowerCase().includes('province')) {{
                        await fillField(selector, userData.address.state);
                    }} else if (selector.toLowerCase().includes('zip') || selector.toLowerCase().includes('postal')) {{
                        await fillField(selector, userData.address.zip);
                    }} else if (selector.toLowerCase().includes('country')) {{
                        await fillField(selector, userData.address.country);
                    }}
                }}
                
                // Fill shipping fields
                for (const selector of {json.dumps(field_types['shipping'])}) {{
                    // Try common shipping field names
                    if (selector.toLowerCase().includes('first') || selector.toLowerCase().includes('name') && !selector.toLowerCase().includes('last')) {{
                        await fillField(selector, userData.first_name);
                    }} else if (selector.toLowerCase().includes('last')) {{
                        await fillField(selector, userData.last_name);
                    }} else if (selector.toLowerCase().includes('address') || selector.toLowerCase().includes('street')) {{
                        await fillField(selector, userData.address.street);
                    }} else if (selector.toLowerCase().includes('address2') || selector.toLowerCase().includes('apt')) {{
                        await fillField(selector, userData.address.apt);
                    }} else if (selector.toLowerCase().includes('city')) {{
                        await fillField(selector, userData.address.city);
                    }} else if (selector.toLowerCase().includes('state') || selector.toLowerCase().includes('province')) {{
                        await fillField(selector, userData.address.state);
                    }} else if (selector.toLowerCase().includes('zip') || selector.toLowerCase().includes('postal')) {{
                        await fillField(selector, userData.address.zip);
                    }} else if (selector.toLowerCase().includes('country')) {{
                        await fillField(selector, userData.address.country);
                    }}
                }}
                
                // Fill contact fields
                for (const selector of {json.dumps(field_types['contact'])}) {{
                    if (selector.toLowerCase().includes('email')) {{
                        await fillField(selector, userData.email);
                    }} else if (selector.toLowerCase().includes('phone')) {{
                        await fillField(selector, userData.phone);
                    }}
                }}
                
                // Fill payment fields
                for (const selector of {json.dumps(field_types['payment'])}) {{
                    if (selector.toLowerCase().includes('card') && selector.toLowerCase().includes('number')) {{
                        await fillField(selector, userData.payment_method.card_number);
                    }} else if (selector.toLowerCase().includes('name') && selector.toLowerCase().includes('card')) {{
                        await fillField(selector, userData.first_name + " " + userData.last_name);
                    }} else if (selector.toLowerCase().includes('exp') && selector.toLowerCase().includes('month')) {{
                        await fillField(selector, userData.payment_method.expiry_month);
                    }} else if (selector.toLowerCase().includes('exp') && selector.toLowerCase().includes('year')) {{
                        await fillField(selector, userData.payment_method.expiry_year);
                    }} else if (selector.toLowerCase().includes('exp') && !selector.toLowerCase().includes('month') && !selector.toLowerCase().includes('year')) {{
                        // Combined expiry date (MM/YY)
                        const expiry = userData.payment_method.expiry_month + "/" + userData.payment_method.expiry_year.slice(-2);
                        await fillField(selector, expiry);
                    }} else if (selector.toLowerCase().includes('cvv') || selector.toLowerCase().includes('cvc') || selector.toLowerCase().includes('security')) {{
                        await fillField(selector, userData.payment_method.cvv);
                    }}
                }}
                
                return filledFields;
            }}
            """
            
            # Execute the script
            filled_fields = await self.page.evaluate(fill_script, self.user_data)
            
            logger.info(f"Filled {filled_fields} form fields with user data")
            
            return filled_fields > 0
        
        except Exception as e:
            logger.error(f"Error filling form fields: {e}")
            return False
    
    async def take_screenshot(self, filename: str) -> str:
        """Take a screenshot of the current page.
        
        Args:
            filename: Filename to save the screenshot
            
        Returns:
            Path to the saved screenshot
        """
        try:
            if not self.page:
                raise ValueError("Playwright page not initialized")
            
            logger.info(f"Taking screenshot: {filename}")
            
            # Take screenshot
            await self.page.screenshot(path=filename)
            
            logger.info(f"Screenshot saved: {filename}")
            return filename
        
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            raise 