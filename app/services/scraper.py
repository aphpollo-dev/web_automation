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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select  # Added this import
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException, ElementClickInterceptedException, JavascriptException
from selenium.webdriver.common.action_chains import ActionChains
import asyncio
import os

class WebScraper:
    def __init__(self, headless: bool = True, user_data: Optional[Dict[str, Any]] = None):
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
        """Initialize the Selenium WebDriver with proper Chrome version handling."""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless")
            
            # Add location of Chrome binary
            chrome_binary_path = "/usr/bin/google-chrome-stable"
            if os.path.exists(chrome_binary_path):
                chrome_options.binary_location = chrome_binary_path
                logger.info(f"Using Chrome binary at: {chrome_binary_path}")
                
                # Get Chrome version
                try:
                    import subprocess
                    chrome_version = subprocess.check_output([chrome_binary_path, '--version']).decode().strip().split()[-1]
                    logger.info(f"Detected Chrome version: {chrome_version}")
                except Exception as e:
                    logger.warning(f"Could not detect Chrome version: {e}")
                    chrome_version = None
            else:
                # Try to find Chrome binary
                possible_paths = [
                    "/usr/bin/google-chrome",
                    "/usr/bin/chrome",
                    "/snap/bin/chromium",
                    "/snap/bin/google-chrome"
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        chrome_options.binary_location = path
                        logger.info(f"Using Chrome binary at: {path}")
                        break
                else:
                    logger.warning("Could not find Chrome binary in common locations")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Add WebGL related options to prevent SwiftShader warning
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-webgl")
            chrome_options.add_argument("--disable-webgl2")
            
            # Add these options to prevent payment handler dialogs
            chrome_options.add_argument("--disable-features=PaymentHandlerMinimal")
            chrome_options.add_experimental_option("prefs", {
                "payment.method_promo_shown": True,
                "autofill.credit_card_enabled": False,
                "profile.default_content_setting_values.payment_handler": 2  # 2 = block
            })
            
            # Try multiple strategies to initialize the WebDriver
            try:
                # First, try to use the local chromedriver binary (most reliable in headless VPS)
                logger.info("Attempting to use local chromedriver binary")
                local_driver_path = "/home/ubuntu/Scrape_code/chromedriver-linux64/chromedriver"
                if os.path.exists(local_driver_path):
                    from selenium.webdriver.chrome.service import Service as ChromeService
                    service = ChromeService(executable_path=local_driver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("Successfully initialized with local ChromeDriver")
                else:
                    # If local driver not found, try with ChromeDriverManager
                    logger.info("Local chromedriver not found, trying with ChromeDriverManager")
                    from selenium.webdriver.chrome.service import Service as ChromeService
                    from webdriver_manager.chrome import ChromeDriverManager
                    from webdriver_manager.core.utils import get_browser_version_from_os
                    
                    # Use detected Chrome version or get it from OS
                    if not chrome_version:
                        try:
                            chrome_version = get_browser_version_from_os("google-chrome")
                            logger.info(f"Detected Chrome version from OS: {chrome_version}")
                        except Exception as e:
                            logger.warning(f"Could not detect Chrome version from OS: {e}")
                    
                    # Use cache_valid_range to avoid re-downloading drivers
                    if chrome_version:
                        service = ChromeService(ChromeDriverManager(driver_version=chrome_version, cache_valid_range=30).install())
                    else:
                        service = ChromeService(ChromeDriverManager(cache_valid_range=30).install())
                    
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("Successfully initialized ChromeDriver with WebDriver Manager")
                    
            except Exception as e1:
                logger.warning(f"Failed to initialize with ChromeDriverManager: {e1}")
                
                try:
                    # Fallback: try to find chromedriver in the extracted directory
                    logger.info("Trying to find chromedriver in extracted directory")
                    extracted_driver_path = None
                    
                    # Try multiple potential paths for chromedriver
                    potential_paths = [
                        "/home/ubuntu/Scrape_code/chromedriver-linux64/chromedriver",
                        "/home/ubuntu/Scrape_code/chromedriver",
                        "/usr/local/bin/chromedriver",
                        "/usr/bin/chromedriver"
                    ]
                    
                    for path in potential_paths:
                        if os.path.exists(path) and os.access(path, os.X_OK):
                            extracted_driver_path = path
                            break
                    
                    if extracted_driver_path:
                        from selenium.webdriver.chrome.service import Service as ChromeService
                        service = ChromeService(executable_path=extracted_driver_path)
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info(f"Successfully initialized with chromedriver at {extracted_driver_path}")
                    else:
                        raise FileNotFoundError("Could not find chromedriver executable in common locations")
                        
                except Exception as e2:
                    logger.warning(f"Failed to initialize with local chromedriver: {e2}")
                    
                    # Last resort, try a simplified approach
                    logger.info("Attempting simplified Chrome initialization")
                    try:
                        self.driver = webdriver.Chrome(options=chrome_options)
                    except Exception as e3:
                        error_msg = f"All Chrome initialization methods failed. Please ensure Chrome and ChromeDriver versions match.\nFinal error: {e3}"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
            
            logger.info("Selenium WebDriver initialized successfully")
            return self.driver
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    async def close_driver(self):
        """Close the Selenium WebDriver with proper error handling."""
        try:
            if not self.driver:
                logger.warning("No active WebDriver instance to close")
                return False

            initial_url = self.driver.current_url
            
            if await self.find_and_click_button(['payment', 'complete_order']):
                # Check if URL changed after clicking button
                logger.info(f"Initial URL: {initial_url}")
                time.sleep(20)
                if not self.driver:  # Check if driver is still available
                    logger.warning("WebDriver was closed during wait period")
                    return False
                    
                current_url = self.driver.current_url
                if current_url.split('?')[0].rstrip('/') != initial_url.split('?')[0].rstrip('/'):
                    logger.info(f"URL changed after clicking button: {current_url}")
                else:
                    logger.info("URL still unchanged after clicking button")
                    return False
            else:
                logger.info("No relevant buttons found or clickable")
                if self.driver:
                    logger.info("Waiting for 20s before closing the Selenium WebDriver")
                    await asyncio.sleep(20)  # 20-second delay
                    try:
                        self.driver.quit()
                    except Exception as e:
                        logger.error(f"Error while quitting WebDriver: {e}")
                    finally:
                        self.driver = None
                        logger.info("Selenium WebDriver closed")
                
                return False
                
        except Exception as e:
            logger.error(f"Error in close_driver: {e}")
            # Ensure driver is cleaned up even if there's an error
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as quit_error:
                    logger.error(f"Error while quitting WebDriver during error handling: {quit_error}")
                finally:
                    self.driver = None
            return False
    
    async def handle_react_select_fields(self) -> None:
        """Handle React Select dropdown components which require special handling."""
        try:
            if not self.driver:
                raise ValueError("WebDriver not initialized")
            
            logger.info("Looking for React Select fields")
            
            # Find React Select input fields
            react_select_inputs = self.driver.find_elements(By.CSS_SELECTOR, "[id^='react-select'][id$='-input']")
            
            for input_field in react_select_inputs:
                if input_field.is_displayed() and input_field.is_enabled():
                    try:
                        # Get the field ID to determine what type of field it is
                        field_id = input_field.get_attribute("id")
                        parent_container = input_field.find_element(By.XPATH, "./ancestor::div[contains(@class, 'react-select')]")
                        
                        # Try to get label or context
                        context_text = ""
                        try:
                            # Look for label in parent containers
                            for i in range(1, 5):  # Check up to 5 levels up
                                parent = input_field.find_element(By.XPATH, f"./{'ancestor::div[1]' * i}")
                                parent_text = parent.text.lower()
                                if parent_text and len(parent_text) < 100:  # Avoid getting too much text
                                    context_text = parent_text
                                    break
                        except:
                            pass
                        
                        logger.info(f"Found React Select field: {field_id} with context: {context_text}")
                        
                        # Determine what data to fill based on context
                        value_to_fill = None
                        
                        if "country" in field_id.lower() or "country" in context_text:
                            value_to_fill = self.user_data['address']['country']
                            logger.info(f"Filling country select with: {value_to_fill}")
                        elif any(word in context_text for word in ["state", "province", "region"]):
                            value_to_fill = self.user_data['address']['state']
                            logger.info(f"Filling state select with: {value_to_fill}")
                        
                        if value_to_fill:
                            # Click to open the dropdown
                            parent_container.click()
                            time.sleep(0.5)
                            
                            # Enter the value in the input field
                            input_field.send_keys(value_to_fill)
                            time.sleep(0.5)
                            
                            # Try to find and click the matching option
                            try:
                                # Look for options that appear after clicking
                                options = self.driver.find_elements(By.CSS_SELECTOR, "[id^='react-select'][role='option']")
                                
                                if options:
                                    for option in options:
                                        if value_to_fill.lower() in option.text.lower():
                                            option.click()
                                            logger.info(f"Selected option: {option.text}")
                                            break
                                else:
                                    # If no options found, try pressing Enter
                                    input_field.send_keys(Keys.ENTER)
                                    logger.info("No options found, pressed Enter")
                            except Exception as e:
                                logger.warning(f"Error selecting option: {e}")
                                # Try pressing Enter as a fallback
                                input_field.send_keys(Keys.ENTER)
                    
                    except Exception as e:
                        logger.warning(f"Error handling React Select field: {e}")
            
            logger.info("React Select field handling complete")
        except Exception as e:
            logger.error(f"Error handling React Select fields: {e}")
    
    async def handle_modern_styled_inputs(self) -> None:
        """Handle modern styled inputs with floating labels, peer classes, and other modern UI patterns."""
        try:
            if not self.driver:
                raise ValueError("WebDriver not initialized")
            
            logger.info("Looking for modern styled inputs")
            
            # Execute JavaScript to find and fill modern styled inputs based on context
            self.driver.execute_script("""
                // Helper function to determine field type from context
                function determineFieldType(context) {
                    context = context.toLowerCase();
                    if (context.includes('name') || context.includes('full name') || context.includes('fullname')) {
                        return 'name';
                    } else if (context.includes('email')) {
                        return 'email';
                    } else if (context.includes('phone') || context.includes('telephone') || context.includes('mobile')) {
                        return 'phone';
                    } else if (context.includes('address') && !context.includes('address 2') && !context.includes('line 2')) {
                        return 'address';
                    } else if (context.includes('address 2') || context.includes('line 2') || context.includes('apt') || context.includes('suite')) {
                        return 'address2';
                    } else if (context.includes('city')) {
                        return 'city';
                    } else if (context.includes('state') || context.includes('province') || context.includes('region')) {
                        return 'state';
                    } else if (context.includes('zip') || context.includes('postal')) {
                        return 'zip';
                    } else if (context.includes('country')) {
                        return 'country';
                    } else if (context.includes('card') && context.includes('number')) {
                        return 'cardnumber';
                    } else if (context.includes('cvv') || context.includes('cvc') || context.includes('security code')) {
                        return 'cvv';
                    } else if (context.includes('expiry') || context.includes('expiration')) {
                        return 'expiry';
                    }
                    return 'unknown';
                }
                
                // Find all inputs with modern styling patterns
                const modernInputSelectors = [
                    'input.peer', 
                    'input.text-blue-gray-700',
                    'input.bg-transparent',
                    'input.border-blue-gray-200',
                    'input[name="fullName"]',  // Add specific selector for fullName
                    'input.placeholder-shown\\:border',
                    'input.focus\\:outline',
                    'input.transition-all',
                    'input.rounded-\\[7px\\]',
                    'input.w-full.h-full',
                    'input.code',
                    '.form-control',
                    '.form-input',
                    '.input-field',
                    '.chakra-input',
                    '.mui-input',
                    '.ant-input'
                ];
                
                // Try each selector
                for (const selector of modernInputSelectors) {
                    try {
                        const inputs = document.querySelectorAll(selector);
                        console.log(`Found ${inputs.length} inputs with selector: ${selector}`);
                        
                        for (const input of inputs) {
                            if (input.type === 'hidden' || !input.offsetParent) continue; // Skip hidden inputs
                            
                            // Get context from parent elements
                            let context = '';
                            let parent = input.parentElement;
                            for (let i = 0; i < 3 && parent; i++) { // Check up to 3 levels up
                                context += ' ' + (parent.textContent || '');
                                
                                // Also check for labels
                                const labels = parent.querySelectorAll('label');
                                for (const label of labels) {
                                    context += ' ' + (label.textContent || '');
                                }
                                
                                parent = parent.parentElement;
                            }
                            
                            // Also check for aria-label and placeholder
                            context += ' ' + (input.getAttribute('aria-label') || '');
                            context += ' ' + (input.getAttribute('placeholder') || '');
                            context += ' ' + (input.name || '');
                            context += ' ' + (input.id || '');
                            
                            // Determine field type from context
                            const fieldType = determineFieldType(context);
                            console.log(`Field type determined as: ${fieldType} for context: ${context.substring(0, 50)}...`);
                            
                            // Fill the field based on type
                            if (fieldType === 'name') {
                                input.value = arguments[0] + ' ' + arguments[1];
                                console.log('Filled name field');
                            } else if (fieldType === 'email') {
                                input.value = arguments[2];
                                console.log('Filled email field');
                            } else if (fieldType === 'phone') {
                                input.value = arguments[3];
                                console.log('Filled phone field');
                            } else if (fieldType === 'address') {
                                input.value = arguments[4];
                                console.log('Filled address field');
                            } else if (fieldType === 'address2') {
                                input.value = arguments[5];
                                console.log('Filled address2 field');
                            } else if (fieldType === 'city') {
                                input.value = arguments[6];
                                console.log('Filled city field');
                            } else if (fieldType === 'state') {
                                input.value = arguments[7];
                                console.log('Filled state field');
                            } else if (fieldType === 'zip') {
                                input.value = arguments[8];
                                console.log('Filled zip field');
                            } else if (fieldType === 'country') {
                                input.value = arguments[9];
                                console.log('Filled country field');
                            } else if (fieldType === 'cardnumber') {
                                input.value = arguments[10];
                                console.log('Filled card number field');
                            } else if (fieldType === 'cvv') {
                                input.value = arguments[11];
                                console.log('Filled CVV field');
                            } else if (fieldType === 'expiry') {
                                input.value = arguments[12] + '/' + arguments[13].slice(-2);
                                console.log('Filled expiry field');
                            }
                            
                            // Trigger events to ensure the value is registered
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            
                            // For modern frameworks, we need to trigger a focus event first, then blur
                            input.dispatchEvent(new Event('focus', { bubbles: true }));
                            setTimeout(() => {
                                input.dispatchEvent(new Event('blur', { bubbles: true }));
                            }, 100);
                        }
                    } catch (e) {
                        console.error(`Error with selector ${selector}:`, e);
                    }
                }
                
                // Specifically handle the example class pattern
                try {
                    const specificInputs = document.querySelectorAll('input.code.peer.w-full.h-full.bg-transparent.text-blue-gray-700, input.peer.w-full.h-full.bg-transparent.text-blue-gray-700');
                    console.log(`Found ${specificInputs.length} inputs with specific class pattern`);
                    
                    for (const input of specificInputs) {
                        if (input.type === 'hidden' || !input.offsetParent) continue; // Skip hidden inputs
                        
                        // Get context from parent elements
                        let context = '';
                        let parent = input.parentElement;
                        for (let i = 0; i < 3 && parent; i++) { // Check up to 3 levels up
                            context += ' ' + (parent.textContent || '');
                            parent = parent.parentElement;
                        }
                        
                        // Determine field type from context
                        const fieldType = determineFieldType(context);
                        console.log(`Specific pattern field type: ${fieldType}`);
                        
                        // Fill the field based on type (same logic as above)
                        if (fieldType === 'name') {
                            input.value = arguments[0] + ' ' + arguments[1];
                        } else if (fieldType === 'email') {
                            input.value = arguments[2];
                        } else if (fieldType === 'phone') {
                            input.value = arguments[3];
                        } else if (fieldType === 'address') {
                            input.value = arguments[4];
                        } else if (fieldType === 'address2') {
                            input.value = arguments[5];
                        } else if (fieldType === 'city') {
                            input.value = arguments[6];
                        } else if (fieldType === 'state') {
                            input.value = arguments[7];
                        } else if (fieldType === 'zip') {
                            input.value = arguments[8];
                        } else if (fieldType === 'country') {
                            input.value = arguments[9];
                        }
                        
                        // Trigger events
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new Event('focus', { bubbles: true }));
                        setTimeout(() => {
                            input.dispatchEvent(new Event('blur', { bubbles: true }));
                        }, 100);
                    }
                } catch (e) {
                    console.error('Error handling specific class pattern:', e);
                }
            """,
            self.user_data['first_name'],
            self.user_data['last_name'],
            self.user_data['email'],
            self.user_data['phone'],
            self.user_data['address']['street'],
            self.user_data['address']['apt'],
            self.user_data['address']['city'],
            self.user_data['address']['state'],
            self.user_data['address']['zip'],
            self.user_data['address']['country'],
            self.user_data['payment_method']['card_number'],
            self.user_data['payment_method']['cvv'],
            self.user_data['payment_method']['expiry_month'],
            self.user_data['payment_method']['expiry_year']
            )
            
            logger.info("Modern styled inputs handling complete")
        except Exception as e:
            logger.error(f"Error handling modern styled inputs: {e}")
    
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
            time.sleep(3)
            
            # Get the current URL (might have changed due to redirects)
            current_url = self.driver.current_url
            
            # Check for agreement/consent checkboxes and click them
            await self.check_agreement_checkboxes()
            
            # Handle modern styled inputs with floating labels and peer classes
            await self.handle_modern_styled_inputs()
            
            # Handle React Select dropdown components
            await self.handle_react_select_fields()
            
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
    
    async def fill_quantity_fields(self, quantity: int) -> bool:
        """Find and fill quantity input fields on the page.
        
        Args:
            quantity: The quantity value to set
            
        Returns:
            True if quantity field was found and filled, False otherwise
        """
        try:
            if not self.driver:
                logger.error("WebDriver not initialized")
                return False
            
            logger.info(f"Looking for quantity input field to set value: {quantity}")
            
            # Common selectors for quantity input fields
            quantity_selectors = [
                "//input[(contains(@id, 'quantity') or contains(@name, 'quantity') or contains(@class, 'quantity'))]",
                "//input[(contains(@id, 'quantity') or contains(@name, 'quantity') or contains(@class, 'quantity'))]",
                "//input[(contains(@id, 'qty') or contains(@name, 'qty') or contains(@class, 'qty'))]",
                "//input[(contains(@id, 'qty') or contains(@name, 'qty') or contains(@class, 'qty'))]",
                "//input[(contains(@aria-label, 'quantity') or contains(@placeholder, 'quantity'))]",
                "//input[(contains(@aria-label, 'quantity') or contains(@placeholder, 'quantity'))]",
                "//input[@type='number'][@min]",  # Often quantity fields have a min attribute
                "//select[contains(@id, 'qty') or contains(@name, 'qty') or contains(@class, 'qty')]",
                # Added label-based selectors
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quantity')]/following-sibling::input",
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'qty')]/following-sibling::input",
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quantity')]/preceding-sibling::input",
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'qty')]/preceding-sibling::input",
                # Added span-based selectors
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quantity')]/following-sibling::input",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'qty')]/following-sibling::input",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quantity')]/preceding-sibling::input",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'qty')]/preceding-sibling::input",
                # Added parent-based selectors
                "//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'quantity')]//input",
                "//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'qty')]//input"
            ]
            
            for selector in quantity_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            # Scroll element into view
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)
                            
                            tag_name = element.tag_name.lower()
                            if tag_name == 'select':
                                # Handle select dropdown
                                options = element.find_elements(By.TAG_NAME, "option")
                                # Find the option closest to our desired quantity
                                closest_option = None
                                closest_diff = float('inf')
                                
                                for option in options:
                                    try:
                                        option_value = int(option.get_attribute("value"))
                                        diff = abs(option_value - quantity)
                                        if diff < closest_diff:
                                            closest_diff = diff
                                            closest_option = option
                                    except (ValueError, TypeError):
                                        continue
                                
                                if closest_option:
                                    logger.info(f"Setting quantity dropdown to value: {closest_option.get_attribute('value')}")
                                    closest_option.click()
                                    return True
                                
                            else:
                                # Handle input field
                                try:
                                    # First try to clear any existing value trackers
                                    self.driver.execute_script("""
                                        if (arguments[0]._valueTracker) {
                                            arguments[0]._valueTracker.setValue('');
                                        }
                                    """, element)
                                    
                                    # Try to trigger React-style onChange handler if it exists
                                    self.driver.execute_script("""
                                        if (arguments[0].__reactEventHandlers) {
                                            arguments[0].__reactEventHandlers.onChange({target: {value: arguments[1]}});
                                        }
                                    """, element, str(quantity))
                                    
                                    # Use native input value setter for framework compatibility
                                    self.driver.execute_script("""
                                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                        nativeInputValueSetter.call(arguments[0], arguments[1]);
                                        
                                        // Dispatch events in the correct order
                                        arguments[0].dispatchEvent(new Event('focus', { bubbles: true }));
                                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                        
                                        // Move focus to body element after setting value
                                        document.body.focus();
                                        arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                                        
                                        // For React-style frameworks
                                        if (window.React && window.React.events) {
                                            window.React.events.emit('change', arguments[1]);
                                        }
                                    """, element, str(quantity))
                                    
                                    # Verify the value was set
                                    actual_value = element.get_attribute('value')
                                    if actual_value != str(quantity):
                                        # If value didn't stick, try direct property setting
                                        element.clear()
                                        element.send_keys(str(quantity))
                                        
                                    # Add a small delay to let framework updates process
                                    time.sleep(0.5)
                                    
                                    logger.info(f"Set quantity input field to value: {quantity}")
                                    return True
                                    
                                except Exception as e:
                                    logger.debug(f"Error setting quantity value: {e}")
                                    try:
                                        # Fallback to basic Selenium actions
                                        element.clear()
                                        element.send_keys(str(quantity))
                                        time.sleep(0.5)
                                        return True
                                    except:
                                        return False
                except Exception as e:
                    logger.debug(f"Error with quantity selector {selector}: {e}")
            
            # If no direct quantity field found, look for quantity buttons (+ and -)
            logger.info("No direct quantity input found, looking for quantity adjustment buttons")
            
            # Find elements that might be quantity adjustment buttons
            plus_button_selectors = [
                "//button[contains(@class, 'plus') or contains(@class, 'increment') or contains(@class, 'increase')]",
                "//button[contains(text(), '+')]",
                "//a[contains(@class, 'plus') or contains(@class, 'increment') or contains(@class, 'increase')]",
                "//a[contains(text(), '+')]",
                "//span[contains(@class, 'plus') or contains(@class, 'increment') or contains(@class, 'increase')]",
                "//span[contains(text(), '+')]",
                "//div[contains(@class, 'plus') or contains(@class, 'increment') or contains(@class, 'increase')]",
                "//div[contains(text(), '+')]"
            ]
            
            for selector in plus_button_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            # Try to find the quantity display (often between +/- buttons)
                            logger.info("find quantity display")
                            quantity_display = None
                            
                            # Check for a display element nearby
                            try:
                                # Look for siblings or nearby elements that might show the quantity
                                display_elements = self.driver.find_elements(
                                    By.XPATH, 
                                    f"//input[ancestor::div[contains(., '+')]] | //span[ancestor::div[contains(., '+')]]"
                                )
                                
                                for display in display_elements:
                                    if display.is_displayed():
                                        quantity_display = display
                                        break
                            except:
                                pass
                            
                            # Scroll to the button
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)
                            
                            # Click the + button until we reach the desired quantity
                            current_qty = 1  # Default starting quantity
                            
                            # Try to get current quantity if display element was found
                            if quantity_display:
                                try:
                                    if quantity_display.tag_name.lower() == 'input':
                                        current_qty = int(quantity_display.get_attribute('value') or '1')
                                    else:
                                        current_qty = int(quantity_display.text.strip() or '1')
                                except (ValueError, TypeError):
                                    current_qty = 1
                            
                            # Click + button until we reach desired quantity
                            clicks_needed = max(0, quantity - current_qty)
                            logger.info(f"Current quantity: {current_qty}, clicking + button {clicks_needed} times")
                            
                            for _ in range(clicks_needed):
                                try:
                                    self.driver.execute_script("arguments[0].click();", element)
                                    time.sleep(0.2)  # Small delay between clicks
                                except:
                                    try:
                                        element.click()
                                        time.sleep(0.2)
                                    except:
                                        logger.warning("Failed to click + button")
                                        break
                            
                            logger.info(f"Adjusted quantity using + button approximately to: {quantity}")
                            return True
                except Exception as e:
                    logger.debug(f"Error with plus button selector {selector}: {e}")
            
            logger.warning("No quantity input field or adjustment buttons found")
            return False
            
        except Exception as e:
            logger.error(f"Error filling quantity field: {e}")
            return False

    async def select_product_option(self, option_name: str, option_value: str) -> bool:
        """Select a product option like size, color, etc.
        
        Args:
            option_name: Name of the option (e.g., 'size', 'color')
            option_value: Value to select (e.g., 'M', 'Blue')
            
        Returns:
            True if option was successfully selected, False otherwise
        """
        try:
            # Debug logging
            logger.info(f"Attempting to select option '{option_name}' with value '{option_value}'")
            
            # Common selectors for product options
            selectors = [
                # Modern UI selectors
                f"//button[@role='option']//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]/ancestor::button",
                f"//*[@role='option' and descendant::*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]]",
                f"//button[descendant::*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]]",
                
                # Direct element selectors
                f"//select[contains(@id, '{option_name}') or contains(@name, '{option_name}') or contains(@class, '{option_name}')]",
                f"//div[contains(@class, 'product-options')]//select[contains(@id, '{option_name}')]",
                f"//div[contains(@class, 'variant')]//select[contains(@id, '{option_name}')]",
                f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_name}')]",
                f"//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value}')]",
                
                # Button and div selectors with expanded attributes
                f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]",
                f"//button[@role='option']//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]/ancestor::button",
                f"//button[.//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]]",
                f"//div[contains(@class, 'variant')]//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]",
                
                # Role-based selectors
                f"//*[@role='option' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower()}')]",
                f"//*[@role='option']//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value.lower}')]/ancestor::*[@role='option']",
                
                # Radio button selectors
                f"//input[@type='radio' and (contains(@name, '{option_name}') or contains(@class, '{option_name}') or contains(@value, '{option_value}'))]",
                f"//input[@type='radio' and contains(text(), '{option_value}')]",
                
                
                # Custom attribute selectors
                f"//*[@data-{option_name}='{option_value}']",
                f"//*[@data-variant='{option_value}']",
                f"//*[@data-option='{option_value}']",
                f"//*[@data-selection='{option_value}']",
                
                # Nested selectors for complex structures
                f"//div[contains(@class, 'variant-wrapper')]//div[contains(., '{option_value}')]",
                f"//div[contains(@class, 'swatch')]//div[contains(., '{option_value}')]",
                f"//div[contains(@class, 'option')]//div[contains(., '{option_value}')]",
                
                # Fallback selectors
                f"//*[contains(@option-value, '{option_value}') or contains(@data-option-value, '{option_value}') or contains(@value, '{option_value}')]",
                f"//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{option_value}')]",
            ]
            
            for selector in selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                logger.info(f" selector: {selector}")
                for element in elements:
                    
                    try:
                        # Try to scroll element into view first
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.5)
                        
                        # Check if element is displayed or can be interacted with
                        is_displayed = element.is_displayed()
                        is_enabled = element.is_enabled()
                        is_clickable = False
                        
                        try:
                            # Try to check if element is clickable
                            WebDriverWait(self.driver, 2).until(
                                EC.element_to_be_clickable((By.XPATH, f"//*[@id='{element.get_attribute('id')}']"))
                            )
                            is_clickable = True
                        except:
                            pass
                        
                        if is_displayed or is_enabled or is_clickable:
                            try:
                                # If it's a select element
                                if element.tag_name == 'select':
                                    select = Select(element)
                                    # Try exact match first
                                    try:
                                        select.select_by_value(option_value)
                                    except:
                                        # Try case-insensitive text match
                                        for option in select.options:
                                            if option_value.lower() in option.text.lower():
                                                select.select_by_visible_text(option.text)
                                                break
                                # If it's a button or div (likely a swatch or option tile)
                                elif element.tag_name in ['button', 'div', 'span', 'label']:
                                    logger.info(f"Selecting option {option_name} with value {option_value} using element {element.get_attribute('outerHTML')}")
                                    # Try multiple click methods
                                    try:
                                        # Try JavaScript click first
                                        self.driver.execute_script("arguments[0].click();", element)
                                    except:
                                        try:
                                            # Try ActionChains click
                                            ActionChains(self.driver).move_to_element(element).click().perform()
                                        except:
                                            # Try regular click
                                            element.click()
                                # If it's a radio button
                                elif element.tag_name == 'input' and element.get_attribute('type') == 'radio':
                                    if not element.is_selected():
                                        try:
                                            self.driver.execute_script("arguments[0].click();", element)
                                        except:
                                            element.click()
                                
                                # Wait for any dynamic updates
                                await asyncio.sleep(1)
                                
                                # Verify the selection was successful
                                if element.tag_name == 'select':
                                    selected_option = Select(element).first_selected_option
                                    if option_value.lower() in selected_option.text.lower():
                                        return True
                                elif element.tag_name == 'input' and element.get_attribute('type') == 'radio':
                                    if element.is_selected():
                                        return True
                                else:
                                    # For other elements, assume success if we got here
                                    return True
                                    
                            except Exception as e:
                                logger.debug(f"Error selecting option {option_name}: {e}")
                                continue
                    except Exception as e:
                        logger.debug(f"Error with element for selector {selector}: {e}")
                        continue
            
            logger.warning(f"Could not find or select option {option_name} with value {option_value}")
            return False
            
        except Exception as e:
            logger.error(f"Error in select_product_option: {e}")
            return False

    
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
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pay')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pay')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
                    "//*[contains(@id, 'pay') or contains(@class, 'pay')]",
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
                                    
                                    # Find and uncheck any "Remember me" or "Save information" checkboxes BEFORE clicking payment button
                                    remember_selectors = [
                                        "//input[@type='checkbox' and (contains(@id, 'remember') or contains(@name, 'remember') or contains(@class, 'remember'))]",
                                        "//input[@type='checkbox' and (contains(@id, 'save') or contains(@name, 'save') or contains(@class, 'save'))]",
                                        "//input[@type='checkbox' and (contains(@id, 'store') or contains(@name, 'store') or contains(@class, 'store'))]",
                                        "//input[@type='checkbox' and (contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember'))]",
                                        "//input[@type='checkbox' and (contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember'))]",
                                        "//input[@type='checkbox' and (contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save'))]",
                                        "//input[@type='checkbox' and (contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save'))]",
                                        "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember')]//input[@type='checkbox']",
                                        "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]//input[@type='checkbox']"
                                    ]
                                    
                                    checkboxes_unchecked = 0
                                    for selector in remember_selectors:
                                        try:
                                            elements = self.driver.find_elements(By.XPATH, selector)
                                            for element in elements:
                                                if element.is_displayed() and element.is_selected():
                                                    # Get checkbox label for logging
                                                    try:
                                                        label_text = "Unknown"
                                                        label_id = element.get_attribute("id")
                                                        if label_id:
                                                            label_elem = self.driver.find_element(By.XPATH, f"//label[@for='{label_id}']")
                                                            if label_elem:
                                                                label_text = label_elem.text.strip()
                                                        if not label_text or label_text == "Unknown":
                                                            parent = self.driver.find_element(By.XPATH, f"//input[@id='{label_id}']/parent::*")
                                                            if parent:
                                                                label_text = parent.text.strip()
                                                    except:
                                                        pass
                                                    
                                                    logger.info(f"Unchecking save/remember checkbox: {label_text}")
                                                    try:
                                                        self.driver.execute_script("arguments[0].click();", element)
                                                    except:
                                                        element.click()
                                                    checkboxes_unchecked += 1
                                                    time.sleep(0.5)
                                        except Exception as e:
                                            logger.debug(f"Error handling remember/save checkbox with selector {selector}: {e}")    
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
                "contact": [],
                "unknown": [],  # Added unknown type for unrecognized fields
                "styled": []    # Added specifically for modern styled inputs
            }
            logger.info(f"Field types: {field_types}")
            
            # Common field identifiers with expanded patterns
            field_identifiers = {
                "billing": ["billing", "bill to", "bill address", "billing address", "bill information"],
                "shipping": ["shipping", "ship to", "delivery", "shipping address", "ship address", "delivery address", "recipient"],
                "payment": ["payment", "card", "credit", "cvv", "cvc", "expir", "expiry", "expiration", "card number", "cardholder", "security code", "payment method"],
                "contact": ["email", "phone", "contact", "mobile", "telephone", "e-mail", "customer", "account"]
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
                    
                    # Flag to track if field type was identified
                    field_type_found = False
                    
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
            return {"billing": [], "shipping": [], "payment": [], "contact": [], "unknown": []}
    
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
            
            # Create JavaScript to fill the fields with improved automation
            fill_script = f"""
            const userData = {user_data_js};
            let filledFields = 0;
            
            console.log('Starting enhanced form automation...');
            
            // Helper function to fill an input field with enhanced framework support
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
                        // Enhanced input field handling
                        try {{
                            // Try to clear any existing value trackers (React)
                            if (field._valueTracker) {{
                                field._valueTracker.setValue('');
                            }}
                            
                            // Try React event handlers
                            if (field.__reactEventHandlers) {{
                                field.__reactEventHandlers.onChange({{target: {{value: value}}}});
                            }}
                            
                            // Use native input value setter for framework compatibility
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeInputValueSetter.call(field, value);
                            
                            // Dispatch multiple events for framework detection
                            field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            field.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            
                            filledFields++;
                            return true;
                        }} catch (e) {{
                            console.error('Error filling field:', e);
                            // Fallback to basic value setting
                            field.value = value;
                            field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            filledFields++;
                            return true;
                        }}
                    }}
                }}
                return false;
            }}
            
            // Enhanced email field detection
            const emailSelectors = [
                'input[name="email"]',
                'input[type="email"]',
                'input[autocomplete="email"]',
                'input.email',
                'input#email'
            ];
            
            let emailField = null;
            for (const selector of emailSelectors) {{
                emailField = document.querySelector(selector);
                if (emailField) {{
                    console.log(`Found email input using selector: ${{selector}}`);
                    fillField(`document.querySelector('${{selector}}')`, userData.email);
                    break;
                }}
            }}
            
            // Enhanced name field handling
            const nameSelectors = [
                'input[name="fullName"]',
                'input[name="full_name"]',
                'input[name="name"]',
                'input[autocomplete="name"]',
                'input.full-name',
                'input#fullName',
                'input#full_name',
                'input#name'
            ];
            
            let nameField = null;
            for (const selector of nameSelectors) {{
                nameField = document.querySelector(selector);
                if (nameField) {{
                    console.log(`Found name input using selector: ${{selector}}`);
                    fillField(`document.querySelector('${{selector}}')`, userData.first_name + ' ' + userData.last_name);
                    break;
                }}
            }}
            
            // Fill billing fields
            for (const selector of {json.dumps(field_types['billing'])}) {{
                // Try full name field first
                if (selector.toLowerCase().includes('full_name') || 
                    (selector.toLowerCase().includes('name') && 
                    !selector.toLowerCase().includes('first') && 
                    !selector.toLowerCase().includes('last') && 
                    !selector.toLowerCase().includes('user'))) {{
                    fillField(selector, userData.first_name + ' ' + userData.last_name); 
                    setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('first') || selector.toLowerCase().includes('name') && !selector.toLowerCase().includes('last')) {{
                    fillField(selector, userData.first_name); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('last')) {{
                    fillField(selector, userData.last_name); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('address') || selector.toLowerCase().includes('street')) {{
                    fillField(selector, userData.address.street); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('address2') || selector.toLowerCase().includes('apt')) {{
                    fillField(selector, userData.address.apt); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('city')) {{
                    fillField(selector, userData.address.city); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('state') || selector.toLowerCase().includes('province')) {{
                    fillField(selector, userData.address.state); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('zip') || selector.toLowerCase().includes('postal')) {{
                    fillField(selector, userData.address.zip); setTimeout(() => {{}}, 1000);
                }} else if (selector.toLowerCase().includes('country')) {{
                    fillField(selector, userData.address.country); setTimeout(() => {{}}, 1000);
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
            
            // Try to inject a script into the page context for enhanced framework support
            try {{
                const scriptElement = document.createElement('script');
                scriptElement.textContent = `
                    (function() {{
                        // This runs in the page context, not in the console sandbox
                        const nameField = document.querySelector('input[name="fullName"]');
                        const emailField = document.querySelector('input[name="email"]') || 
                                        document.querySelector('input[type="email"]');
                        
                        if (nameField) {{
                            // Try to set value through any custom property or method
                            if (nameField._valueTracker) nameField._valueTracker.setValue('');
                            if (nameField.__reactEventHandlers) nameField.__reactEventHandlers.onChange({{target: {{value: '${{userData.first_name}} ${{userData.last_name}}'}}}});
                            
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeInputValueSetter.call(nameField, '${{userData.first_name}} ${{userData.last_name}}');
                            nameField.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                        
                        if (emailField) {{
                            if (emailField._valueTracker) emailField._valueTracker.setValue('');
                            if (emailField.__reactEventHandlers) emailField.__reactEventHandlers.onChange({{target: {{value: '${{userData.email}}'}}}});
                            
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeInputValueSetter.call(emailField, '${{userData.email}}');
                            emailField.dispatchEvent(new Event('input', {{bubbles: true}}));
                        }}
                    }})();
                `;
                document.body.appendChild(scriptElement);
                document.body.removeChild(scriptElement);
            }} catch (e) {{
                console.log('Enhanced framework support injection failed:', e);
            }}
            
            return filledFields;
            """

            filled_fields = self.driver.execute_script(fill_script)

            try:
                # First look for all possible Stripe iframes
                stripe_iframes = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    "iframe[name^='__privateStripeFrame'], iframe.stripe-element, iframe.card-fields-iframe"
                )
                
                iframe_found = False
                if stripe_iframes:
                    logger.info(f"Found {len(stripe_iframes)} potential payment iframes")
                    
                    # Define field types and their selectors
                    field_selectors = {
                        'card': {
                            'selectors': "input[name='number'], input[name='cardnumber'], input[autocomplete='cc-number'],input[data-elements-stable-field-name='cardNumber']",
                            'value': self.user_data['payment_method']['card_number']
                        },
                        'expiry': {
                            'selectors': "input[name='exp-date'], input[name='expiry'], input[data-elements-stable-field-name='cardExpiry'], input[autocomplete='cc-exp']",
                            'value': f"{self.user_data['payment_method']['expiry_month']}/{self.user_data['payment_method']['expiry_year'][-2:]}"
                        },
                        'cvv': {
                            'selectors': "input[name='verification_value'], input[name='cvc'], input[autocomplete='cc-csc'], input[data-elements-stable-field-name='cardCvc']",
                            'value': self.user_data['payment_method']['cvv']
                        },
                        'name': {
                            'selectors': "input[name='name'], input[name='cardholder-name'], input[name='cardholder'], input[name='nameOnAccount'], input[data-elements-stable-field-name='cardHolder'], input[autocomplete='cc-name']",
                            'value': self.user_data['payment_method']['card_holder']
                        }
                    }

                    # Try single iframe approach first
                    for iframe in stripe_iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            card_input = self.driver.find_element(By.CSS_SELECTOR, field_selectors['card']['selectors'])
                            cvv_input = self.driver.find_element(By.CSS_SELECTOR, field_selectors['cvv']['selectors'])
                            if card_input and cvv_input:
                                iframe_found = True
                                logger.info("Found single iframe with all fields")
                                break
                        except Exception as e:
                            logger.debug(f"Single iframe approach failed: {e}")
                            self.driver.switch_to.default_content()
                            iframe_found = False
                            continue
                    if iframe_found:
                        for field_type, field_info in field_selectors.items():
                            try:
                                field = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, field_info['selectors']))
                                )
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                                time.sleep(0.3)
                                self.driver.execute_script("arguments[0].focus(); arguments[0].click();", field)
                                time.sleep(0.3)
                                self.driver.execute_script("arguments[0].value = '';", field)
                                time.sleep(0.3)
                                self.driver.execute_script("""
                                    arguments[0].value = arguments[1];
                                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                """, field, field_info['value'])
                                time.sleep(0.3)
                            except Exception as e:
                                logger.debug(f"Error filling {field_type} field: {e}")
                                iframe_found = False
                                self.driver.switch_to.default_content()
                                break
                    # If single iframe approach failed, try multiple iframes approach
                    if not iframe_found:
                        logger.info("Single iframe approach failed, trying multiple iframes")
                        card_field_found = False  # Track if we've already found a card field
                        
                        for iframe in stripe_iframes:
                            try:
                                self.driver.switch_to.frame(iframe)
                                for field_type, field_info in field_selectors.items():
                                    try:
                                        # Special handling for card fields
                                        if field_type == 'card':
                                            if card_field_found:
                                                field = self.driver.find_element(By.CSS_SELECTOR, field_selectors['expiry']['selectors'])
                                                # If we already found a card field, this is likely an expiry field
                                                logger.info("Found second card field, treating as expiry field")
                                                raw_value = f"{self.user_data['payment_method']['expiry_month']}/{self.user_data['payment_method']['expiry_year'][-2:]}"
                                            else:
                                                field = self.driver.find_element(By.CSS_SELECTOR, field_info['selectors'])
                                                raw_value = field_info['value']
                                                card_field_found = True
                                        else:
                                            field = self.driver.find_element(By.CSS_SELECTOR, field_info['selectors'])
                                            raw_value = field_info['value']
                                            
                                        logger.info(f"Found {field_type} field in separate iframe")
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                                        time.sleep(0.3)
                                        self.driver.execute_script("arguments[0].focus(); arguments[0].click();", field)
                                        time.sleep(0.3)
                                        self.driver.execute_script("arguments[0].value = '';", field)
                                        time.sleep(0.3)
                                        self.driver.execute_script("""
                                            arguments[0].value = arguments[1];
                                            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                            // Move focus to body element after setting value
                                            document.body.focus();
                                            // Dispatch blur event on the field
                                            arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                                        """, field, raw_value)
                                        time.sleep(0.3)  # Give time for events to process
                                        iframe_found = True
                                        break
                                    except:
                                        pass
                                self.driver.switch_to.default_content()
                            except Exception as e:
                                logger.debug(f"Error in multiple iframe approach: {e}")
                                self.driver.switch_to.default_content()

                    if iframe_found:
                        logger.info("Successfully filled Stripe payment fields")
                    else:
                        logger.warning("Could not find payment iframe with card field, continuing with regular form")

                    

            except Exception as e:
                logger.error(f"Error filling payment form: {e}")
                self.driver.switch_to.default_content()
                return None

            logger.info(f"Filled {filled_fields} form fields with user data from MongoDB")
            
            return iframe_found
        
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
                    
                    # Find and uncheck any "Remember me" or "Save information" checkboxes BEFORE clicking payment button
                    remember_selectors = [
                        "//input[@type='checkbox' and (contains(@id, 'remember') or contains(@name, 'remember') or contains(@class, 'remember'))]",
                        "//input[@type='checkbox' and (contains(@id, 'save') or contains(@name, 'save') or contains(@class, 'save'))]",
                        "//input[@type='checkbox' and (contains(@id, 'store') or contains(@name, 'store') or contains(@class, 'store'))]",
                        "//input[@type='checkbox' and (contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember'))]",
                        "//input[@type='checkbox' and (contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember'))]",
                        "//input[@type='checkbox' and (contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save'))]",
                        "//input[@type='checkbox' and (contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save'))]",
                        "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'remember')]//input[@type='checkbox']",
                        "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]//input[@type='checkbox']"
                    ]
                    
                    checkboxes_unchecked = 0
                    for selector in remember_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            for element in elements:
                                if element.is_displayed() and element.is_selected():
                                    # Get checkbox label for logging
                                    try:
                                        label_text = "Unknown"
                                        label_id = element.get_attribute("id")
                                        if label_id:
                                            label_elem = self.driver.find_element(By.XPATH, f"//label[@for='{label_id}']")
                                            if label_elem:
                                                label_text = label_elem.text.strip()
                                        if not label_text or label_text == "Unknown":
                                            parent = self.driver.find_element(By.XPATH, f"//input[@id='{label_id}']/parent::*")
                                            if parent:
                                                label_text = parent.text.strip()
                                    except:
                                        pass
                                    
                                    logger.info(f"Unchecking save/remember checkbox: {label_text}")
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                    except:
                                        element.click()
                                    checkboxes_unchecked += 1
                                    time.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Error handling remember/save checkbox with selector {selector}: {e}")
                    
                    if checkboxes_unchecked > 0:
                        logger.info(f"Unchecked {checkboxes_unchecked} save/remember checkboxes")
                        # Add a small delay after unchecking boxes
                        time.sleep(1)

                    # Now try to find and click payment or complete order buttons
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