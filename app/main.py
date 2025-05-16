from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx
import json
from app.db.mongodb import connect_to_mongodb, close_mongodb_connection
from app.services.event_service import EventService

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
# Auth router
from app.api.auth_routes import auth_router, get_current_user
# Agency router
from app.api.purchase_routes import purchase_router, order_router
from app.api.card_routes import card_router
# Dashboard router
from app.api.event_routes import event_router
# input router
from app.api.input_routes import input_router
from app.api.product_routes import product_router

app.include_router(auth_router)
app.include_router(purchase_router, prefix="/api")
# app.include_router(order_router, prefix="/api", dependencies=[Depends(get_current_user)])
# app.include_router(card_router, prefix="/api", dependencies=[Depends(get_current_user)])
# app.include_router(event_router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(order_router, prefix="/api")
app.include_router(card_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(input_router, prefix="/api")
# Include product routes
app.include_router(product_router, prefix="/api")

@app.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            request = json.loads(data)
            prompt = request.get("prompt", "")

            content_text = await EventService.get_chat(prompt)
            print("Answer:", content_text)

            await websocket.send_text(content_text)  # Send full response
            await websocket.send_text("<END>")  # Signal end of message
                    

    except WebSocketDisconnect:
        print("Client disconnected")
    except httpx.TimeoutException:
        await websocket.send_text("Error: Request to TogetherAI timed out.")
    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")


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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
