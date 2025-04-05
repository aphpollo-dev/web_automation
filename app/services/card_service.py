from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from loguru import logger

from app.models.card import Card, AddCardRequest

class CardService:
    def __init__(self, db):
        """Initialize the card service.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        logger.info("Card service initialized")
    
    async def add_card(self, card_data: AddCardRequest) -> str:
        """Add a new card.
        
        Args:
            card_data: Card data
            
        Returns:
            ID of the created card
        """
        try:
            # If this is set as default, unset any existing default
            if card_data.is_default:
                await self.db.cards.update_many(
                    {},
                    {"$set": {"is_default": False}}
                )
            
            # Create new card
            card = Card(
                card_number=card_data.card_number,
                card_holder=card_data.card_holder,
                expiry_month=card_data.expiry_month,
                expiry_year=card_data.expiry_year,
                cvv=card_data.cvv,
                billing_address=card_data.billing_address,
                is_default=card_data.is_default
            )
            
            # Insert into database
            result = await self.db.cards.insert_one(card.model_dump(by_alias=True))
            card_id = str(result.inserted_id)
            
            # Log success with masked card number
            masked_card = "****" + card_data.card_number[-4:]
            logger.info(f"Added card {masked_card}")
            
            return card_id
        
        except Exception as e:
            logger.error(f"Failed to add card: {e}")
            raise
    
    async def get_cards(self) -> List[Card]:
        """Get all cards.
        
        Returns:
            List of cards
        """
        try:
            cursor = self.db.cards.find({})
            cards = await cursor.to_list(length=None)
            
            # Convert to Card objects
            return [Card(**card) for card in cards]
        
        except Exception as e:
            logger.error(f"Failed to get cards: {e}")
            raise
    
    async def set_default_card(self, card_id: str) -> bool:
        """Set a card as default.
        
        Args:
            card_id: ID of the card to set as default
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First, unset any existing default
            await self.db.cards.update_many(
                {},
                {"$set": {"is_default": False}}
            )
            
            # Set the new default
            result = await self.db.cards.update_one(
                {"_id": ObjectId(card_id)},
                {"$set": {"is_default": True}}
            )
            
            return result.modified_count > 0
        
        except Exception as e:
            logger.error(f"Failed to set default card: {e}")
            raise
    
    async def delete_card(self, card_id: str) -> bool:
        """Delete a card.
        
        Args:
            card_id: ID of the card to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Remove the card
            result = await self.db.cards.delete_one({
                "_id": ObjectId(card_id)
            })
            
            if result.deleted_count > 0:
                logger.info(f"Deleted card {card_id}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Failed to delete card: {e}")
            raise 