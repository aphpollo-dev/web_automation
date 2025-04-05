# Automated Purchase System

A Python FastAPI application that automates product purchases by analyzing unknown web page structures using web scraping and LLM analysis.

## Features

- Accepts product URLs and user tokens via API
- Scrapes product pages to identify purchase elements
- Uses LLM to analyze page structure and generate automation code
- Follows the purchase flow through multiple pages automatically
- Retrieves user payment information from MongoDB
- Completes purchases on behalf of users

## Project Structure

```
app/
├── api/            # API endpoints
├── core/           # Core application settings
├── db/             # Database connections and queries
├── models/         # Pydantic models and MongoDB schemas
├── services/       # Business logic services
│   ├── scraper.py  # Web scraping functionality
│   ├── llm.py      # LLM integration for page analysis
│   └── automation.py # Purchase automation logic
└── utils/          # Utility functions
```

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Unix/MacOS: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in your configuration
6. Run the application: `uvicorn app.main:app --reload`

## API Endpoints

- `POST /api/purchase`: Start an automated purchase process
  - Request body:
    ```json
    {
      "product_url": "https://example.com/product/123",
      "user_token": "user_auth_token"
    }
    ```

## How It Works

1. User submits a product URL and authentication token
2. System scrapes the product page
3. LLM analyzes the page structure to identify purchase elements
4. System clicks the appropriate buttons (e.g., "Add to Cart")
5. New page is scraped and analyzed
6. Process repeats until purchase is complete
7. User's payment information from MongoDB is used to complete the transaction

## Requirements

- Python 3.8+
- MongoDB
- OpenAI API key 