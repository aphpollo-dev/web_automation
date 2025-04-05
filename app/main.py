from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

from app.db.mongodb import connect_to_mongodb, close_mongodb_connection

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Automated Purchase System",
    description="API for automating product purchases using web scraping and LLM analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.api.routes import purchase_router
from app.api.card_routes import card_router
app.include_router(purchase_router, prefix="/api")
app.include_router(card_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Automated Purchase System API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    await connect_to_mongodb()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongodb_connection()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True) 