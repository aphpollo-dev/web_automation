import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from loguru import logger
import time
import json
from typing import Dict, Any, Optional, Tuple, List, Union
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException, ElementClickInterceptedException, JavascriptException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import asyncio

class WebScraper:
    def __init__(self, headless: bool = False, user_data: Optional[Dict[str, Any]] = None):
        """Initialize the web scraper.
        
        Args:
            headless: Whether to run the browser in headless mode
            user_data: User data for filling forms (billing, shipping, payment info)
        """
        self.headless = headless
        self.driver = None
        self.user_data = user_data or self._get_default_user_data()
    
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
    
    async def initialize_driver(self):
        """Initialize the Selenium WebDriver."""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # service = Service(ChromeDriverManager().install())
            service = Service("C:/chromedriver-win64/chromedriver.exe")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Selenium WebDriver initialized")
            return self.driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    async def close_driver(self):
        """Close the Selenium WebDriver with a 1-minute delay."""
        if self.driver:
            logger.info("Waiting for 1 minute before closing the Selenium WebDriver")
            await asyncio.sleep(60)  # 1-minute delay
            self.driver.quit()
            self.driver = None
            logger.info("Selenium WebDriver closed")
    
    async def scrape_page(self, url: str) -> Tuple[str, str]:
        """Scrape a web page and return only the body content to reduce token usage.
        
        Args:
            url: URL of the page to scrape
            
        Returns:
            Tuple of (current_url, body_content)
        """
        try:
            if not self.driver:
                await self.initialize_driver()
            
            logger.info(f"Scraping page: {url}")
            self.driver.get(url)
            
            # Wait for page to load
            time.sleep(5)
            
            # Get the current URL (might have changed due to redirects)
            current_url = self.driver.current_url
            
            # Check for agreement/consent checkboxes and click them
            await self.check_agreement_checkboxes()
            
            # Extract only the body element to reduce token usage
            try:
                body_element = self.driver.find_element(By.TAG_NAME, "body")
                body_html = body_element.get_attribute("outerHTML")
                logger.info("Successfully extracted body element")
            except NoSuchElementException:
                logger.warning("Body element not found, falling back to full page source")
                body_html = self.driver.page_source
            
            logger.info(f"Successfully scraped page: {current_url}")
            return current_url, body_html
        except Exception as e:
            logger.error(f"Failed to scrape page {url}: {e}")
            raise
    
    async def scroll_page(self, scroll_amount: int = 300, max_scrolls: int = 10, wait_time: float = 0.5) -> None:
        """Scroll the page to load dynamic content when no new URL is found.
        
        Args:
            scroll_amount: Amount to scroll in pixels
            max_scrolls: Maximum number of scroll operations
            wait_time: Time to wait between scrolls in seconds
        """
        try:
            if not self.driver:
                raise ValueError("WebDriver not initialized")
            
            logger.info(f"Scrolling page to load dynamic content (max {max_scrolls} scrolls)")
            
            # Get initial page height
            initial_height = self.driver.execute_script("return document.body.scrollHeight")
            
            for i in range(max_scrolls):
                # Scroll down
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                
                # Wait for content to load
                time.sleep(wait_time)
                
                # Check if new content has loaded by comparing page height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height > initial_height:
                    logger.info(f"New content loaded after scroll {i+1} (height increased from {initial_height} to {new_height})")
                    initial_height = new_height
                
                logger.debug(f"Completed scroll {i+1}/{max_scrolls}")
            
            # Scroll to specific positions where buttons are commonly found
            positions = [0.25, 0.5, 0.75, 1.0]  # Scroll to 25%, 50%, 75%, and 100% of page
            for position in positions:
                self.driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {position});")
                time.sleep(wait_time)
                logger.debug(f"Scrolled to {int(position*100)}% of page height")
            
            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            logger.info("Scrolling complete, returned to top of page")
            
        except Exception as e:
            logger.error(f"Error during page scrolling: {e}")
    
    async def find_and_click_button(self, button_types: List[str]) -> bool:
        """Find and click a button when URL doesn't change.
        
        Args:
            button_types: List of button types to look for (e.g., ['add_to_cart', 'checkout'])
            
        Returns:
            True if a button was found and clicked, False otherwise
        """
        try:
            if not self.driver:
                raise ValueError("WebDriver not initialized")
            
            logger.info(f"Looking for buttons of types: {button_types}")
            
            # Common button selectors based on type
            button_selectors = {
                'add_to_cart': [
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add to cart')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add to cart')]",
                    "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add to cart')]",
                    "//*[contains(@id, 'add-to-cart') or contains(@class, 'add-to-cart')]",
                    "//*[contains(@id, 'addtocart') or contains(@class, 'addtocart')]"
                ],
                'checkout': [
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'checkout')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'checkout')]",
                    "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'checkout')]",
                    "//*[contains(@id, 'checkout') or contains(@class, 'checkout')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'proceed to')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'proceed to')]"
                ],
                'view_cart': [
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view cart')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view cart')]",
                    "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view cart')]",
                    "//*[contains(@id, 'view-cart') or contains(@class, 'view-cart')]",
                    "//*[contains(@id, 'viewcart') or contains(@class, 'viewcart')]",
                    "//a[contains(@href, 'cart')]"
                ],
                'payment': [
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'payment')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'payment')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
                    "//*[contains(@id, 'payment') or contains(@class, 'payment')]"
                ],
                'complete_order': [
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'place order')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'complete order')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit order')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'place order')]",
                    "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'place order')]",
                    "//*[contains(@id, 'place-order') or contains(@class, 'place-order')]",
                    "//*[contains(@id, 'placeorder') or contains(@class, 'placeorder')]"
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
                        
                        # Find all matching elements
                        elements = self.driver.find_elements(By.XPATH, selector)
                        
                        # Filter for visible elements
                        visible_elements = []
                        for element in elements:
                            try:
                                if element.is_displayed():
                                    visible_elements.append(element)
                            except StaleElementReferenceException:
                                continue
                        
                        if visible_elements:
                            logger.info(f"Found {len(visible_elements)} visible {button_type} buttons")
                            
                            # Try to click each visible element
                            for element in visible_elements:
                                try:
                                    # Scroll element into view
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                    time.sleep(0.5)
                                    
                                    # Try to get element text for logging
                                    try:
                                        element_text = element.text.strip() or element.get_attribute("value") or "[No text]"
                                        logger.info(f"Clicking {button_type} button: '{element_text}'")
                                    except:
                                        logger.info(f"Clicking {button_type} button (text unavailable)")
                                    
                                    # Try JavaScript click first
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                    except JavascriptException:
                                        # Fall back to regular click
                                        element.click()
                                    
                                    # Wait for potential page load or error alerts
                                    time.sleep(3)
                                    
                                    # If this is a payment-related button, check for error alerts
                                    if is_payment_button:
                                        logger.info("Checking for payment error alerts after clicking payment button")
                                        
                                        # Check for error alerts
                                        error_selectors = [
                                            "//div[contains(@class, 'error') and contains(text(), 'payment')]",
                                            "//div[contains(@class, 'alert') and contains(text(), 'payment')]",
                                            "//div[contains(@class, 'error') and contains(text(), 'card')]",
                                            "//div[contains(@class, 'alert') and contains(text(), 'card')]",
                                            "//div[contains(@class, 'error') and contains(text(), 'declined')]",
                                            "//div[contains(@class, 'alert') and contains(text(), 'declined')]",
                                            "//div[contains(@class, 'error') and contains(text(), 'failed')]",
                                            "//div[contains(@class, 'alert') and contains(text(), 'failed')]",
                                            "//div[contains(@class, 'error')]",
                                            "//div[contains(@class, 'alert')]",
                                            "//p[contains(@class, 'error')]",
                                            "//span[contains(@class, 'error')]",
                                            "//*[contains(text(), 'payment declined')]",
                                            "//*[contains(text(), 'card declined')]",
                                            "//*[contains(text(), 'payment failed')]",
                                            "//*[contains(text(), 'transaction failed')]",
                                            "//*[contains(text(), 'invalid card')]"
                                        ]
                                        
                                        for error_selector in error_selectors:
                                            try:
                                                error_elements = self.driver.find_elements(By.XPATH, error_selector)
                                                for error_element in error_elements:
                                                    if error_element.is_displayed():
                                                        error_text = error_element.text.strip()
                                                        if error_text:
                                                            logger.error(f"Payment error alert detected: {error_text}")
                                                            # Return special value to indicate payment error
                                                            self.driver.execute_script(f"""
                                                            console.error("Payment error alert detected: {error_text}");
                                                            window.paymentErrorDetected = "{error_text}";
                                                            """)
                                                            return True
                                            except Exception as e:
                                                logger.debug(f"Error checking for error alerts with selector {error_selector}: {e}")
                                        
                                        # Check for JavaScript alerts
                                        try:
                                            alert = self.driver.switch_to.alert
                                            alert_text = alert.text
                                            logger.info(f"Alert detected after payment: {alert_text}")
                                            
                                            # Check if it's an error alert
                                            error_keywords = [
                                                "invalid payment", "payment failed", "payment error", 
                                                "system error", "error", "failed", "declined", 
                                                "invalid card", "card declined", "transaction failed"
                                            ]
                                            
                                            is_error_alert = any(keyword.lower() in alert_text.lower() for keyword in error_keywords)
                                            
                                            if is_error_alert:
                                                logger.error(f"Payment error alert detected: {alert_text}")
                                                # Accept the alert
                                                alert.accept()
                                                # Return special value to indicate payment error
                                                self.driver.execute_script(f"""
                                                console.error("Payment error alert detected: {alert_text}");
                                                window.paymentErrorDetected = "{alert_text}";
                                                """)
                                                return True
                                            
                                            # Accept the alert if it's not an error
                                            alert.accept()
                                        except:
                                            # No alert present
                                            pass
                                    
                                    logger.info(f"Successfully clicked {button_type} button")
                                    return True
                                except (ElementClickInterceptedException, StaleElementReferenceException) as e:
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
    
    async def detect_form_fields(self) -> Dict[str, List[str]]:
        """Detect form fields on the page to determine if it's a checkout or payment page.
        
        Returns:
            Dictionary with field types and their selectors
        """
        try:
            if not self.driver:
                raise ValueError("WebDriver not initialized")
            
            logger.info("Detecting form fields on the page")
            
            field_types = {
                "billing": [],
                "shipping": [],
                "payment": [],
                "contact": []
            }
            
            # Common field identifiers
            field_identifiers = {
                "billing": ["billing", "bill to"],
                "shipping": ["shipping", "ship to", "delivery"],
                "payment": ["payment", "card", "credit", "cvv", "cvc", "expir"],
                "contact": ["email", "phone", "contact"]
            }
            
            # Find all input fields
            input_elements = self.driver.find_elements(By.XPATH, "//input | //select | //textarea")
            
            for element in input_elements:
                try:
                    # Get element attributes
                    element_id = element.get_attribute("id") or ""
                    element_name = element.get_attribute("name") or ""
                    element_class = element.get_attribute("class") or ""
                    element_placeholder = element.get_attribute("placeholder") or ""
                    element_label = ""
                    
                    # Try to find associated label
                    try:
                        label_for = self.driver.find_element(By.XPATH, f"//label[@for='{element_id}']")
                        element_label = label_for.text.strip()
                    except:
                        pass
                    
                    # Combine all text for matching
                    all_text = (element_id + " " + element_name + " " + element_class + " " + 
                               element_placeholder + " " + element_label).lower()
                    
                    # Check which type of field it is
                    for field_type, identifiers in field_identifiers.items():
                        for identifier in identifiers:
                            if identifier.lower() in all_text:
                                field_selector = f"document.querySelector('[id=\"{element_id}\"]') || document.querySelector('[name=\"{element_name}\"]')"
                                if field_selector not in field_types[field_type]:
                                    field_types[field_type].append(field_selector)
                                break
                except:
                    continue
            
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
    
    def fill_form_fields(self, field_types: Dict[str, List[str]]) -> bool:
        """Fill form fields with user data.
        
        Args:
            field_types: Dictionary with field types and selectors
            
        Returns:
            True if fields were filled, False otherwise
        """
        try:
            if not self.driver:
                logger.error("WebDriver not initialized")
                return False
            
            logger.info(f"Filling form fields with user data from MongoDB")
            
            # Convert user data to JavaScript
            user_data_js = json.dumps(self.user_data)
            
            # Create JavaScript to fill the fields
            fill_script = f"""
            const userData = {user_data_js};
            let filledFields = 0;
            
            // Helper function to fill an input field
            function fillField(selector, value) {{
                const field = eval(selector);
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
                    fillField(selector, userData.first_name);
                }} else if (selector.toLowerCase().includes('last')) {{
                    fillField(selector, userData.last_name);
                }} else if (selector.toLowerCase().includes('address') || selector.toLowerCase().includes('street')) {{
                    fillField(selector, userData.address.street);
                }} else if (selector.toLowerCase().includes('address2') || selector.toLowerCase().includes('apt')) {{
                    fillField(selector, userData.address.apt);
                }} else if (selector.toLowerCase().includes('city')) {{
                    fillField(selector, userData.address.city);
                }} else if (selector.toLowerCase().includes('state') || selector.toLowerCase().includes('province')) {{
                    fillField(selector, userData.address.state);
                }} else if (selector.toLowerCase().includes('zip') || selector.toLowerCase().includes('postal')) {{
                    fillField(selector, userData.address.zip);
                }} else if (selector.toLowerCase().includes('country')) {{
                    fillField(selector, userData.address.country);
                }}
            }}
            
            // Find shipping form container
            const shippingContainers = document.querySelectorAll('form, div, section, fieldset');
            let shippingForm = null;
            
            for (const container of shippingContainers) {{
                const containerText = container.textContent.toLowerCase();
                if (containerText.includes('shipping') || containerText.includes('ship to') || 
                    containerText.includes('delivery')) {{
                    shippingForm = container;
                    break;
                }}
            }}
            
            if (shippingForm) {{
                // Find all input elements within shipping form
                const inputs = shippingForm.querySelectorAll('input, select, textarea');
                
                for (const input of inputs) {{
                    const inputName = (input.name || input.id || '').toLowerCase();
                    const inputType = input.type.toLowerCase();
                    
                    if (inputName.includes('first') || (inputName.includes('name') && !inputName.includes('last'))) {{
                        fillField(input, userData.first_name);
                    }} else if (inputName.includes('last')) {{
                        fillField(input, userData.last_name);
                    }} else if (inputName.includes('address') || inputName.includes('street')) {{
                        fillField(input, userData.address.street);
                    }} else if (inputName.includes('address2') || inputName.includes('apt')) {{
                        fillField(input, userData.address.apt);
                    }} else if (inputName.includes('city')) {{
                        fillField(input, userData.address.city);
                    }} else if (inputName.includes('state') || inputName.includes('province')) {{
                        fillField(input, userData.address.state);
                    }} else if (inputName.includes('zip') || inputName.includes('postal')) {{
                        fillField(input, userData.address.zip);
                    }} else if (inputName.includes('country')) {{
                        fillField(input, userData.address.country);
                    }}
                }}
            }}
            
            // Fill contact fields
            for (const selector of {json.dumps(field_types['contact'])}) {{
                if (selector.toLowerCase().includes('email')) {{
                    fillField(selector, userData.email);
                }} else if (selector.toLowerCase().includes('phone')) {{
                    fillField(selector, userData.phone);
                }}
            }}
            // Check "same as shipping" checkbox if billing is same as shipping
            for (const selector of {json.dumps(field_types.get('same_as_shipping', []))}) {{
                const checkbox = eval(selector);
                if (checkbox) {{
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filledFields++;
                }}
            }}
            
            return filledFields;
            """
            try:
                # First look for all possible Stripe iframes
                stripe_iframes = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    "iframe[name^='__privateStripeFrame'], iframe.stripe-element, iframe.card-fields-iframe"
                )
                
                iframe_found = False
                if stripe_iframes:
                    logger.info(f"Found {len(stripe_iframes)} potential payment iframes")
                    for iframe in stripe_iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            # Verify if this is the right frame by checking for card input
                            card_inputs = self.driver.find_elements(
                                By.CSS_SELECTOR, 
                                "input[name='number'], input[name='cardnumber'], input[data-elements-stable-field-name='cardNumber']"
                            )
                            if card_inputs:
                                logger.info("Found correct payment iframe with card field")
                                iframe_found = True
                                break
                            else:
                                # Not the right frame, switch back
                                self.driver.switch_to.default_content()
                        except Exception as e:
                            logger.warning(f"Error checking iframe: {e}")
                            self.driver.switch_to.default_content()
                
                if not iframe_found:
                    logger.warning("Could not find payment iframe with card field, continuing with regular form")
                
                # Wait for payment fields with more robust selectors
                card_selectors = "input[name='number'], input[name='cardnumber'], input[data-elements-stable-field-name='cardNumber']"
                expiry_selectors = "input[name='expiry']"
                cvv_selectors = "input[name='verification_value'], input[name='cvc'], input[data-elements-stable-field-name='cardCvc']"
                name_selectors = "input[name='name'], input[name='cardholder-name']"
                
                # Fill card number with better error handling
                try:
                    # Wait longer and ensure element is fully ready
                    card_number_input = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, card_selectors))
                    )
                    # Scroll to element to ensure it's in view
                    # self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_number_input)
                    # time.sleep(1)  # Additional wait for element to stabilize
                    
                    # Try direct input first
                    ActionChains(self.driver).move_to_element(card_number_input).click().perform()
                    card_number_input.clear()
                    ActionChains(self.driver).send_keys_to_element(
                        card_number_input, 
                        self.user_data['payment_method']['card_number']
                    ).perform()
                except Exception as e:
                    logger.warning(f"Direct card number input failed: {e}, trying JavaScript")
                    # Fallback to JavaScript
                    self.driver.execute_script(
                        "arguments[0].value = arguments[1];", 
                        card_number_input, 
                        self.user_data['payment_method']['card_number']
                    )
                
                time.sleep(1)  # Wait between fields
                
                # Similar pattern for expiry
                try:
                    expiry_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, expiry_selectors)))
                
                    # Scroll element into view with margin to avoid overlapping elements
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); window.scrollBy(0, -100);", expiry_input)
                    time.sleep(1)
                    
                    # Try JavaScript click instead of direct click
                    self.driver.execute_script("arguments[0].focus(); arguments[0].click();", expiry_input)
                    time.sleep(1)
                    
                    # Use JavaScript to clear the field
                    self.driver.execute_script("arguments[0].value = '';", expiry_input)
                    time.sleep(0.5)
                    
                    # Format expiry data
                    expiry_value = f"{self.user_data['payment_method']['expiry_month']}/{self.user_data['payment_method']['expiry_year'][-2:]}"
                    
                    # Use JavaScript to set value directly
                    self.driver.execute_script("arguments[0].value = arguments[1];", expiry_input, expiry_value)
                    # Trigger input event to ensure the value is registered
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", expiry_input)
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", expiry_input)
                    time.sleep(0.5)
                    # This line is redundant now since we've already input the expiry data above
                    # ActionChains(self.driver).send_keys_to_element(expiry_input, expiry_value).perform()
                except Exception as e:
                    logger.warning(f"Direct expiry input failed: {e}, trying JavaScript")
                    try:
                        # Format the expiry value in the exception handler too
                        expiry_value = f"{self.user_data['payment_method']['expiry_month']}/{self.user_data['payment_method']['expiry_year'][-2:]}"
                        self.driver.execute_script(
                            "arguments[0].value = arguments[1];", 
                            expiry_input, 
                            expiry_value
                        )
                    except Exception as inner_e:
                        logger.error(f"JavaScript expiry input also failed: {inner_e}")
                    
                time.sleep(1)
                
                # Similar pattern for CVV
                try:
                    cvv_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, cvv_selectors)))
                
                    # Scroll element into view with margin to avoid overlapping elements
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); window.scrollBy(0, -100);", cvv_input)
                    time.sleep(1)
                    
                    # Try JavaScript click instead of direct click
                    self.driver.execute_script("arguments[0].focus(); arguments[0].click();", cvv_input)
                    time.sleep(1)
                    
                    # Use JavaScript to clear the field
                    self.driver.execute_script("arguments[0].value = '';", cvv_input)
                    time.sleep(0.5)
                    
                    # Use JavaScript to set value directly
                    self.driver.execute_script("arguments[0].value = arguments[1];", cvv_input, self.user_data['payment_method']['cvv'])
                    # Trigger input event to ensure the value is registered
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", cvv_input)
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", cvv_input)
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Direct CVV input failed: {e}, trying JavaScript")
                    try:
                        self.driver.execute_script(
                            "arguments[0].value = arguments[1];", 
                            cvv_input, 
                            self.user_data['payment_method']['cvv']
                        )
                    except Exception as inner_e:
                        logger.error(f"JavaScript CVV input also failed: {inner_e}")
                    
                time.sleep(1)
                
                # Similar pattern for name
                try:
                    name_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, name_selectors)))
                
                    # Scroll element into view with margin to avoid overlapping elements
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); window.scrollBy(0, -100);", name_input)
                    time.sleep(1)
                    
                    # Try JavaScript click instead of direct click
                    self.driver.execute_script("arguments[0].focus(); arguments[0].click();", name_input)
                    time.sleep(1)
                    
                    # Use JavaScript to clear the field
                    self.driver.execute_script("arguments[0].value = '';", name_input)
                    time.sleep(0.5)
                    
                    # Use JavaScript to set value directly
                    name_value = self.user_data['payment_method']['card_holder']
                    self.driver.execute_script("arguments[0].value = arguments[1];", name_input, name_value)
                    # Trigger input event to ensure the value is registered
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", name_input)
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", name_input)
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Direct name input failed: {e}, trying JavaScript")
                    try:
                        name_value = self.user_data['payment_method']['card_holder']
                        self.driver.execute_script(
                            "arguments[0].value = arguments[1];", 
                            name_input, 
                            name_value
                        )
                    except Exception as inner_e:
                        logger.error(f"JavaScript name input also failed: {inner_e}")
                    
                time.sleep(1)
                    
                # Always ensure we switch back to default content
                if iframe_found:
                    logger.info("Switching back to main content after filling payment fields")
                    self.driver.switch_to.default_content()
                    
            except Exception as e:
                logger.error(f"Error filling payment form: {e}")
                # Make sure we're back in the main document
                self.driver.switch_to.default_content()
                # Additional error handling as needed
            filled_fields = self.driver.execute_script(fill_script)
            logger.info(f"Filled {filled_fields} form fields with user data from MongoDB")
            
            return filled_fields > 0
        
        except Exception as e:
            logger.error(f"Error filling form fields: {e}")
            return False
    
    async def execute_action(self, action_code: str) -> str:
        """Execute JavaScript action code in the browser.
        
        Args:
            action_code: JavaScript code to execute
            
        Returns:
            Current URL after action execution
        """
        try:
            if not self.driver:
                logger.error("WebDriver not initialized")
                raise ValueError("WebDriver not initialized")
            
            logger.info("Executing action in browser with user data")
            initial_url = self.driver.current_url
            
            # Inject user data into the action code
            user_data_js = json.dumps(self.user_data)
            logger.info("Injecting user data into automation code")
            
            # Create JavaScript with user data and null checks
            action_with_data = f"""
            // User data
            const userData = {user_data_js};
            
            // Add null checks for all user data properties
            const safeUserData = {{
                email: userData.email || '',
                first_name: userData.first_name || '',
                last_name: userData.last_name || '',
                phone: userData.phone || '',
                address: {{
                    street: (userData.address && userData.address.street) || '',
                    apt: (userData.address && userData.address.apt) || '',
                    city: (userData.address && userData.address.city) || '',
                    state: (userData.address && userData.address.state) || '',
                    zip: (userData.address && userData.address.zip) || '',
                    country: (userData.address && userData.address.country) || ''
                }},
                payment_method: {{
                    card_number: (userData.payment_method && userData.payment_method.card_number) || '',
                    expiry_month: (userData.payment_method && userData.payment_method.expiry_month) || '',
                    expiry_year: (userData.payment_method && userData.payment_method.expiry_year) || '',
                    cvv: (userData.payment_method && userData.payment_method.cvv) || ''
                }}
            }};
            
            // Log that we're using the data (will appear in browser console)
            console.log('Using user data:', {{
                email: safeUserData.email,
                name: safeUserData.first_name + ' ' + safeUserData.last_name,
                address: safeUserData.address.city + ', ' + safeUserData.address.state,
                payment: safeUserData.payment_method.card_number ? ('****' + safeUserData.payment_method.card_number.slice(-4)) : ''
            }});
            
            // Execute the automation code with both userData and safeUserData available
            try {{
                {action_code}
            }} catch (error) {{
                console.error('Error executing automation code:', error);
                // Try to continue despite errors
            }}
            """
            
            # Execute the action with safe user data
            logger.info("Executing JavaScript with safe user data")
            self.driver.execute_script(action_with_data)
            
            # Wait for page to load after action
            time.sleep(5)
            
            # Check if a payment error was detected in the JavaScript code
            try:
                payment_error = self.driver.execute_script("return window.paymentErrorDetected;")
                if payment_error:
                    logger.error(f"Payment error alert detected by JavaScript: {payment_error}")
                    return f"error://payment_failed?message={payment_error}"
            except:
                pass
            
            # Check for payment error alerts
            error_selectors = [
                "//div[contains(@class, 'error') and contains(text(), 'payment')]",
                "//div[contains(@class, 'alert') and contains(text(), 'payment')]",
                "//div[contains(@class, 'error') and contains(text(), 'card')]",
                "//div[contains(@class, 'alert') and contains(text(), 'card')]",
                "//div[contains(@class, 'error') and contains(text(), 'declined')]",
                "//div[contains(@class, 'alert') and contains(text(), 'declined')]",
                "//div[contains(@class, 'error') and contains(text(), 'failed')]",
                "//div[contains(@class, 'alert') and contains(text(), 'failed')]",
                "//div[contains(@class, 'error')]",
                "//div[contains(@class, 'alert')]",
                "//p[contains(@class, 'error')]",
                "//span[contains(@class, 'error')]",
                "//*[contains(text(), 'payment declined')]",
                "//*[contains(text(), 'card declined')]",
                "//*[contains(text(), 'payment failed')]",
                "//*[contains(text(), 'transaction failed')]",
                "//*[contains(text(), 'invalid card')]"
            ]
            
            for error_selector in error_selectors:
                try:
                    error_elements = self.driver.find_elements(By.XPATH, error_selector)
                    for error_element in error_elements:
                        if error_element.is_displayed():
                            error_text = error_element.text.strip()
                            if error_text:
                                logger.error(f"Payment error alert detected: {error_text}")
                                return f"error://payment_failed?message={error_text}"
                except Exception as e:
                    logger.debug(f"Error checking for error alerts with selector {error_selector}: {e}")
            
            # Check for JavaScript alerts
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                logger.info(f"Alert detected: {alert_text}")
                
                # Check if it's an error alert
                error_keywords = [
                    "invalid payment", "payment failed", "payment error", 
                    "system error", "error", "failed", "declined", 
                    "invalid card", "card declined", "transaction failed"
                ]
                
                is_error_alert = any(keyword.lower() in alert_text.lower() for keyword in error_keywords)
                
                if is_error_alert:
                    logger.error(f"Payment error alert detected: {alert_text}")
                    # Accept the alert
                    alert.accept()
                    return f"error://payment_failed?message={alert_text}"
                
                # Accept the alert if it's not an error
                alert.accept()
            except:
                # No alert present
                pass
            
            # Get the current URL (might have changed due to action)
            current_url = self.driver.current_url
            
            # If URL hasn't changed, try additional strategies
            if current_url == initial_url:
                logger.info("URL didn't change after action, trying additional strategies with MongoDB user data")
                
                # First, detect and fill form fields
                field_types = await self.detect_form_fields()
                
                # If payment or billing fields found, fill them with MongoDB user data
                if field_types["payment"] or field_types["billing"]:
                    logger.info("Detected payment or billing fields, filling with user data from MongoDB")
                    self.fill_form_fields(field_types)
                    
                    # Try to find and click payment or complete order buttons
                    if await self.find_and_click_button(['payment', 'complete_order']):
                        # Check if URL changed after clicking button
                        current_url = self.driver.current_url
                        if current_url != initial_url:
                            logger.info(f"URL changed after clicking payment/order button: {current_url}")
                        else:
                            logger.info("URL still unchanged after clicking payment/order button")
                
                # If URL still hasn't changed, try scrolling and finding other buttons
                if current_url == initial_url:
                    # Scroll the page to load any dynamic content
                    await self.scroll_page(max_scrolls=15, wait_time=1.0)
                    
                    # Check if URL changed after scrolling
                    current_url = self.driver.current_url
                    if current_url == initial_url:
                        logger.info("URL still unchanged after scrolling, looking for buttons to click")
                        
                        # Try to find and click relevant buttons
                        if await self.find_and_click_button(['view_cart', 'checkout']):
                            # Check if URL changed after clicking button
                            current_url = self.driver.current_url
                            if current_url != initial_url:
                                logger.info(f"URL changed after clicking button: {current_url}")
                            else:
                                logger.info("URL still unchanged after clicking button")
                        else:
                            logger.info("No relevant buttons found or clickable")
                    else:
                        logger.info(f"URL changed after scrolling: {current_url}")
            
            logger.info(f"Action executed, new URL: {current_url}")
            return current_url
        except Exception as e:
            logger.error(f"Failed to execute action: {e}")
            raise
    
    async def check_agreement_checkboxes(self) -> None:
        """Find and check any agreement or confirmation checkboxes on the page."""
        try:
            logger.info("Checking for agreement/confirmation checkboxes during page scrape")
            
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
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    try:
                        if element.is_displayed() and not element.is_selected():
                            # Get checkbox label for logging
                            try:
                                label_text = "Unknown"
                                label_id = element.get_attribute("id")
                                if label_id:
                                    label_elem = self.driver.find_element(By.XPATH, f"//label[@for='{label_id}']")
                                    if label_elem:
                                        label_text = label_elem.text.strip()
                                if not label_text or label_text == "Unknown":
                                    # Try parent or sibling text
                                    parent = self.driver.find_element(By.XPATH, f"//input[@id='{label_id}']/parent::*")
                                    if parent:
                                        label_text = parent.text.strip()
                            except:
                                pass
                            
                            # Scroll element into view
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            await asyncio.sleep(0.5)
                            
                            # Click the checkbox
                            logger.info(f"Checking agreement checkbox during page scrape: {label_text}")
                            try:
                                self.driver.execute_script("arguments[0].click();", element)
                            except:
                                element.click()
                            
                            checkboxes_checked += 1
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Error checking checkbox during page scrape: {e}")
            
            if checkboxes_checked > 0:
                logger.info(f"Checked {checkboxes_checked} agreement/confirmation checkboxes during page scrape")
            
        except Exception as e:
            logger.warning(f"Error checking agreement checkboxes during page scrape: {e}")
            # Continue with the process even if there's an error checking checkboxes 