import os
import openai
import asyncio
from dotenv import load_dotenv
from loguru import logger
from typing import Dict, Any, Optional
import json
import re
import time
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

class LLMService:
    def __init__(self):
        """Initialize the LLM service."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        
        # Set the API key for the openai module
        openai.api_key = self.api_key
        
        # Rate limiting settings
        self.last_api_call = 0
        self.min_time_between_calls = 1  # seconds
        
        logger.info("LLM service initialized")
    
    def _optimize_html(self, html_content: str) -> str:
        """Optimize HTML content to reduce token usage.
        
        Args:
            html_content: HTML content to optimize
            
        Returns:
            Optimized HTML content
        """
        try:
            # Parse HTML with BeautifulSoup using html.parser instead of lxml
            logger.info("Parsing HTML with BeautifulSoup using html.parser")
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "noscript", "svg", "path"]):
                script.decompose()
            
            # Remove comments
            for comment in soup.find_all(text=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
                comment.extract()
            
            # Remove hidden elements
            for hidden in soup.find_all(style=re.compile(r'display:\s*none|visibility:\s*hidden')):
                hidden.decompose()
            
            # Focus on main content areas
            main_content = None
            for selector in ['main', 'article', '#content', '.content', '#main', '.main', '.product', '.cart', '.checkout']:
                content = soup.select_one(selector)
                if content:
                    main_content = content
                    break
            
            # If main content area found, use it; otherwise use body
            if main_content:
                logger.info(f"Using main content area with selector: {main_content.name}{'.'+main_content.get('class', [''])[0] if main_content.get('class') else ''}")
                optimized_html = str(main_content)
            else:
                logger.info("No main content area found, using optimized body")
                optimized_html = str(soup.body) if soup.body else html_content
            
            # Remove excessive whitespace
            optimized_html = re.sub(r'\s+', ' ', optimized_html)
            
            token_reduction = (len(html_content) - len(optimized_html)) / len(html_content) * 100 if html_content else 0
            logger.info(f"HTML optimization complete: reduced by approximately {token_reduction:.1f}% (from {len(html_content)} to {len(optimized_html)} chars)")
            
            return optimized_html
        except Exception as e:
            logger.error(f"Error optimizing HTML: {e}")
            logger.warning("Falling back to original HTML content due to optimization error")
            return html_content  # Return original content if optimization fails
    
    async def _call_openai_with_retry(self, messages, model, max_tokens, temperature, retries=3):
        """Call OpenAI API with retry logic for rate limits.
        
        Args:
            messages: Messages to send to the API
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            retries: Number of retries for rate limit errors
            
        Returns:
            API response
        """
        # Enforce rate limiting
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        if time_since_last_call < self.min_time_between_calls:
            wait_time = self.min_time_between_calls - time_since_last_call
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s before API call")
            await asyncio.sleep(wait_time)
        
        # Update last call time
        self.last_api_call = time.time()
        
        # Try API call with retries
        for attempt in range(retries + 1):
            try:
                response = await openai.ChatCompletion.acreate(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response
            except openai.error.RateLimitError as e:
                if attempt < retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Rate limit error, retrying in {wait_time}s (attempt {attempt+1}/{retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Rate limit error after {retries} retries: {e}")
                    raise
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
                raise
    
    async def analyze_page_structure(self, html_content: str, url: str) -> Dict[str, Any]:
        """Analyze the structure of a web page using LLM.
        
        Args:
            html_content: HTML content of the page (body only)
            url: URL of the page
            
        Returns:
            Analysis of the page structure
        """
        try:
            logger.info(f"Analyzing page structure for URL: {url}")
            
            # Optimize HTML to reduce token usage
            max_length = 50000  # Reduced from 100,000 to save tokens
            truncated_html = self._optimize_html(html_content)
            
            # Create prompt for page analysis
            prompt = f"""
            You are an expert web page analyzer for e-commerce automation. Analyze the following HTML content from URL: {url}
            
            Your task is to identify the key elements needed for an automated purchase flow:
            
            1. FIRST AND MOST IMPORTANT, CHECK FOR ANY PAYMENT ERROR ALERTS:
               - Look specifically for error alerts that appear after submitting payment
               - These are often modal dialogs, alert boxes, or error messages that appear after clicking "Pay" or "Complete Order"
               - Common payment error alerts include: "Payment declined", "Invalid card", "Transaction failed", "Payment error"
               - Check for elements with classes like 'error', 'alert', 'warning', 'notification', 'modal', 'dialog'
               - Look for text containing words like 'error', 'invalid', 'failed', 'declined', 'unsuccessful'
               - If you find ANY payment error alerts, this is CRITICAL information that should be reported immediately
               - Payment error alerts are different from validation errors - they appear AFTER submitting payment
            
            2. DETERMINE THE PAGE TYPE:
               - Is this a product page? (where you can add items to cart)
               - Is this a checkout page? (where you enter shipping/payment details)
               - Is this a payment page? (where you enter credit card information)
               - Is this a confirmation page? (showing order success)
            
            3. BASED ON THE PAGE TYPE, IDENTIFY THE CRITICAL ELEMENTS:
               - For product pages: Find the "Add to Cart" button AND any "View Cart" button that appears after adding to cart
               - For cart pages: Find the "Checkout" or "Proceed to Checkout" button
               - For checkout pages: Find shipping form fields and "Continue to Payment" button
               - For payment pages: Find ALL payment form fields (card number, expiry, CVV, etc.) and "Complete Order" or "Pay Now" or "Place Order" button
               - For error pages: Find the specific error message and any retry or back buttons
               - For confirmation pages: Find order confirmation details
            
            4. FOR EACH ELEMENT, PROVIDE:
               - Selector (ID, class, or XPath)
               - Element type (button, input, etc.)
               - Text content (if applicable)
               - Any relevant attributes (name, value, etc.)
               - For form fields, identify what information they require (e.g., "first_name", "card_number", etc.)
            
            5. DETERMINE THE NEXT ACTION:
               - What JavaScript code should be executed to proceed to the next step?
               - For forms, what data needs to be filled in?
               - If this is a product page, provide code to click the "Add to Cart" button
               - If a "View Cart" button appears after adding to cart, provide code to click it
               - If this is a checkout or payment page, identify ALL form fields that need to be filled
               - If this is an error page, determine if the purchase should be aborted
            
            6. FOR CHECKOUT AND PAYMENT PAGES, IDENTIFY THESE SPECIFIC FIELD TYPES:
               - Billing address fields (street, city, state, zip, country)
               - Contact information (email, phone)
               - Payment method selection elements
               - Credit card fields (number, name, expiry, CVV)
               - Any checkboxes that need to be checked (terms, etc.)
            
            7. WHEN IDENTIFYING FORM FIELDS, MAP THEM TO THESE DATA FIELDS:
               - Email: safeUserData.email
               - Phone: safeUserData.phone
               - First name: safeUserData.first_name
               - Last name: safeUserData.last_name
               - Address line 1: safeUserData.address.street
               - Address line 2: safeUserData.address.apt
               - City: safeUserData.address.city
               - State/Province: safeUserData.address.state
               - ZIP/Postal code: safeUserData.address.zip
               - Country: safeUserData.address.country
               - Card number: safeUserData.payment_method.card_number
               - Card name: safeUserData.first_name + " " + safeUserData.last_name
               - Expiry month: safeUserData.payment_method.expiry_month
               - Expiry year: safeUserData.payment_method.expiry_year
               - CVV: safeUserData.payment_method.cvv
            
            8. IMPORTANT: IF YOU FIND ANY PAYMENT ERROR ALERTS, include them in a dedicated "payment_error_alerts" section in your response. These might include:
               - Invalid payment method
               - Payment declined
               - Card declined
               - Transaction failed
               - System error
               - Any other error messages related to payment processing
            
            Respond with a JSON object containing this information. Be precise with selectors.
            """
            
            # Call OpenAI API
            messages = [
                {"role": "system", "content": "You are an expert e-commerce automation assistant."},
                {"role": "user", "content": prompt + "\n\nHTML Content:\n" + truncated_html}
            ]
            
            response = await self._call_openai_with_retry(
                messages=messages,
                model="gpt-4-1106-preview",  # Using the correct model name for older API
                max_tokens=1500,  # Reduced from 2000 to save tokens
                temperature=0.2
            )
            
            # Extract and parse response
            response_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```|^\s*(\{[\s\S]*\})\s*$', response_text)
                if json_match:
                    json_str = json_match.group(1) or json_match.group(2)
                    analysis_result = json.loads(json_str)
                else:
                    # If no JSON format found, try to parse the entire response
                    analysis_result = json.loads(response_text)
                
                logger.info("Successfully parsed page analysis result")
                return analysis_result
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from response, returning raw text")
                return {"raw_response": response_text}
        
        except Exception as e:
            logger.error(f"Failed to analyze page structure: {e}")
            raise
    
    async def generate_automation_code(self, page_analysis: Dict[str, Any], url: str, user_data: Dict[str, Any]) -> str:
        """Generate JavaScript automation code based on page analysis.
        
        Args:
            page_analysis: Analysis of the page structure
            url: URL of the page
            user_data: Actual user data for form filling
            
        Returns:
            JavaScript code for automating actions on the page
        """
        try:
            logger.info(f"Generating automation code for URL: {url} with actual user data")
            
            # Check if the page analysis identified any payment error alerts
            if "payment_error_alerts" in page_analysis and page_analysis["payment_error_alerts"]:
                error_messages = page_analysis["payment_error_alerts"]
                if isinstance(error_messages, list):
                    error_message = "; ".join(error_messages)
                else:
                    error_message = str(error_messages)
                    
                logger.warning(f"Generating code for page with payment error alerts: {error_message}")
                
                # Generate code that will report the payment error
                return f"""
                // Payment error alert detected on page
                console.error("Payment error alert detected: {error_message}");
                
                // Return information about the payment error
                return "error://payment_failed?message={error_message}";
                """
            
            # Check if the page analysis identified any errors (backward compatibility)
            if "errors" in page_analysis and page_analysis["errors"]:
                error_messages = page_analysis["errors"]
                if isinstance(error_messages, list):
                    error_message = "; ".join(error_messages)
                else:
                    error_message = str(error_messages)
                    
                logger.warning(f"Generating code for page with errors: {error_message}")
                
                # Generate code that will report the error
                return f"""
                // Error detected on page
                console.error("Payment or system error detected: {error_message}");
                
                // Return information about the error
                return "error://payment_failed?message={error_message}";
                """
            
            # Check if the page type is identified as an error page
            if "page_type" in page_analysis and page_analysis.get("page_type", "").lower() == "error":
                error_message = "Page identified as an error page"
                if "error_message" in page_analysis:
                    error_message = page_analysis["error_message"]
                    
                logger.warning(f"Generating code for error page: {error_message}")
                
                # Generate code that will report the error
                return f"""
                // Error page detected
                console.error("Error page detected: {error_message}");
                
                // Return information about the error
                return "error://payment_failed?message={error_message}";
                """
            
            # Create a sanitized version of user data for logging (mask sensitive info)
            masked_user_data = {
                "email": user_data.get("email", ""),
                "phone": "****" + user_data.get("phone", "")[-4:] if user_data.get("phone") else "",
                "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                "address": f"{user_data.get('address', {}).get('city', '')}, {user_data.get('address', {}).get('state', '')}" if user_data.get('address') else "",
                "payment": "****" + user_data.get("payment_method", {}).get("card_number", "")[-4:] if user_data.get("payment_method", {}).get("card_number") else ""
            }
            logger.info(f"Using user data: {masked_user_data}")
            
            # Create prompt for code generation that includes the actual user data
            prompt = f"""
            You are an expert web automation engineer. Generate JavaScript code to automate actions on a web page based on the following analysis:
            
            URL: {url}
            Page Analysis: {json.dumps(page_analysis, indent=2)}
            
            The code should:
            1. Find the elements using the provided selectors
            2. Perform the necessary actions (click buttons, fill forms, etc.)
            3. Handle potential errors gracefully
            4. Return a success status
            
            IMPORTANT: The code will be executed with user data provided below.
            
            IMPORTANT INSTRUCTIONS BASED ON PAGE TYPE:
            
            FOR CART PAGES:
            - Make sure to correctly click the checkout button to proceed to the next step
            - Handle any popups or overlays that might appear
            - If there are multiple checkout buttons, prioritize the main one
            
            FOR CHECKOUT PAGES:
            - Fill in required form fields with the user data provided below
            - Handle any validation that might occur
            - Make sure to click the button that advances to payment
            
            FOR PAYMENT PAGES:
            - Fill in ALL payment form fields using the user data provided below
            - For credit card fields, use the appropriate values from safeUserData.payment_method
            - Handle any validation that might occur
            - Make sure to click the button that completes the order
            - If you detect payment error alerts, return "error://payment_failed?message=YOUR_ERROR_MESSAGE"
            
            FOR ERROR PAGES:
            - If you detect this is an error page, return "error://payment_failed?message=YOUR_ERROR_MESSAGE"
            - Do not attempt to proceed with the purchase if errors are detected
            
            The code will be executed in a browser context using Selenium's execute_script method.
            
            CRITICAL: Use safeUserData instead of userData in your code. The safeUserData object will be available with this structure:
            
            ```javascript
            const safeUserData = {{
                email: '...',
                first_name: '...',
                last_name: '...',
                phone: '...',
                address: {{
                    street: '...',
                    apt: '...',
                    city: '...',
                    state: '...',
                    zip: '...',
                    country: '...'
                }},
                payment_method: {{
                    card_number: '...',
                    expiry_month: '...',
                    expiry_year: '...',
                    cvv: '...'
                }}
            }};
            ```
            
            IMPORTANT: ALWAYS use safeUserData instead of userData in your code to avoid null reference errors.
            
            CRITICAL: After clicking payment buttons, ALWAYS check for error alerts or messages. If found, return the error URL.
            
            Return ONLY the JavaScript code without any explanation or markdown formatting.
            """
            
            # Call OpenAI API using our retry method
            messages = [
                {"role": "system", "content": "You are an expert JavaScript automation engineer who uses real user data."},
                {"role": "user", "content": prompt}
            ]
            
            logger.info("Requesting automation code with actual user data")
            response = await self._call_openai_with_retry(
                messages=messages,
                model="gpt-4-1106-preview",
                max_tokens=1500,
                temperature=0.2
            )
            
            # Extract the code from the response
            automation_code = response.choices[0].message.content.strip()
            
            # Clean up the code (remove markdown code blocks if present)
            if automation_code.startswith("```javascript"):
                automation_code = automation_code.replace("```javascript", "").replace("```", "").strip()
            elif automation_code.startswith("```js"):
                automation_code = automation_code.replace("```js", "").replace("```", "").strip()
            elif automation_code.startswith("```"):
                automation_code = automation_code.replace("```", "").strip()
            
            logger.info(f"Generated automation code with actual user data for URL: {url}")
            return automation_code
        except Exception as e:
            logger.error(f"Failed to generate automation code: {e}")
            raise 