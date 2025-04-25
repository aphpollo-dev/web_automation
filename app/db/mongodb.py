import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# MongoDB connection string
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB")

# MongoDB client instance
client = None

async def connect_to_mongodb():
    """Connect to MongoDB."""
    global client
    try:
        client = AsyncIOMotorClient(MONGODB_URI)
        logger.info(f"Connected to MongoDB at {MONGODB_URI}")
        
        # Ping the database to verify connection
        await client.admin.command('ping')
        logger.info("MongoDB connection verified")
        
        # List all available databases
        database_names = await client.list_database_names()
        logger.info(f"Available databases: {', '.join(database_names)}")
        
        # Check if our target database exists
        if MONGODB_DB not in database_names:
            logger.warning(f"Target database '{MONGODB_DB}' not found in available databases")
            # Create the database by accessing it (MongoDB creates databases on first use)
            db = client[MONGODB_DB]
            # Create a temporary collection to ensure the database is created
            await db.create_collection("temp_collection")
            logger.info(f"Created database '{MONGODB_DB}' with temporary collection")
            # Drop the temporary collection
            await db.drop_collection("temp_collection")
            logger.info("Dropped temporary collection")
        else:
            logger.info(f"Target database '{MONGODB_DB}' found")
            db = client[MONGODB_DB]
        
        # Get collection info
        try:
            collections = await db.list_collection_names()
            logger.info(f"Collections in '{MONGODB_DB}': {', '.join(collections) if collections else 'No collections found'}")
            
            # If no collections found, create the required collections
            if not collections:
                logger.info("Creating required collections...")
                await db.create_collection("users")
                await db.create_collection("purchases")
                await db.create_collection("cards")
                await db.create_collection("events")
                await db.create_collection("prompts")
                await db.create_collection("user")
                logger.info("Created 'users', 'purchases', 'cards' and etc.. ")
                
                # Create indexes
                await db.users.create_index("email", unique=True)
                await db.purchases.create_index("user_id")
                await db.purchases.create_index("status")
                await db.purchases.create_index([("user_id", 1), ("status", 1)])
                await db.purchases.create_index([("created_at", -1)])
                
                # Create indexes for cards
                await db.cards.create_index([("created_at", -1)])
                await db.cards.create_index("is_default")
                
                logger.info("Created indexes on collections")
                
                # Verify collections again
                collections = await db.list_collection_names()
                logger.info(f"Collections after creation: {', '.join(collections)}")
        except Exception as collection_error:
            logger.error(f"Error accessing collections: {collection_error}")
        
        return client
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_mongodb_connection():
    """Close MongoDB connection."""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")

async def get_database():
    """Get database instance."""
    global client
    if not client:
        client = await connect_to_mongodb()
    return client[MONGODB_DB] 