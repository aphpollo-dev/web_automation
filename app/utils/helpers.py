import uuid
import json
from datetime import datetime
from bson import ObjectId
from typing import Any, Dict

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for MongoDB objects."""
    
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

def generate_task_id() -> str:
    """Generate a unique task ID.
    
    Returns:
        Unique task ID
    """
    return str(uuid.uuid4())

def sanitize_html(html_content: str, max_length: int = 10000) -> str:
    """Sanitize and truncate HTML content.
    
    Args:
        html_content: HTML content to sanitize
        max_length: Maximum length of the sanitized content
        
    Returns:
        Sanitized HTML content
    """
    # Truncate if too long
    if len(html_content) > max_length:
        html_content = html_content[:max_length] + "..."
    
    return html_content

def format_mongodb_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format a MongoDB document for API response.
    
    Args:
        doc: MongoDB document
        
    Returns:
        Formatted document
    """
    # Convert to JSON and back to handle ObjectId and datetime
    return json.loads(json.dumps(doc, cls=JSONEncoder)) 