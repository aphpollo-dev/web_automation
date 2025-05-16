from app.db.mongodb import get_database
from app.models.event import EventCreate
from datetime import datetime
from sentence_transformers import SentenceTransformer
import os, httpx
import faiss
from bson import ObjectId

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_API_KEY2 = os.getenv("TOGETHER_API_KEY2")
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

embedder = SentenceTransformer('paraphrase-MiniLM-L6-v2')

async def generate_answer(question: str, context: dict):
    prompt = f"""
    You are an AI assistant that analyzes user track data. Use the following JSON data to answer the question:
    
    {context}
    
    Question: {question}
    """

    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TOGETHER_API_URL, headers=headers, json=payload)
            response_json = response.json()

        # ✅ Handle missing keys safely
        together_answer = response_json.get("choices", [{}])[0].get("message", {}).get("content", "No response")

    except Exception as e:
        together_answer = f"Error with Together API: {str(e)}"

    return together_answer

async def fetch_documents():
    """Asynchronously fetch documents from MongoDB"""
    service = await EventService.get_instance()
    documents = []
    async for event in service.purchase_collection.find():
        user = await service.user_collection.find_one({"_id": event["user_id"]})
        if user:
            documents.append(f"{user['name']} {user['email']} {event['product_url']} {event['steps']} {event['error']} {event['created_at']}")
    return documents
  
async def create_faiss_index():
    """Fetch documents, generate embeddings, and create a FAISS index"""
    print("Fetching documents from MongoDB...")
    documents = await fetch_documents()
    
    if not documents:
        print("No documents found in MongoDB.")
        return None, None

    print(f"Generating embeddings for {len(documents)} documents...")
    embeddings = embedder.encode(documents, convert_to_numpy=True)

    print("Creating FAISS index...")
    dimension = embeddings.shape[1]  # Get embedding dimension (should be 384 for MiniLM)
    index = faiss.IndexFlatL2(dimension)  # L2 Distance Index
    index.add(embeddings)

    # Save FAISS index for later use
    faiss.write_index(index, "event_data_index.index")
    print("FAISS index saved successfully.")

    return index, documents
  
async def retrieve_relevant_documents(query, documents, top_k=5):
    """Retrieve top-k relevant documents for the given query using FAISS"""
    print("Loading FAISS index...")
    try:
        index = faiss.read_index("event_data_index.index")
    except:
        print("FAISS index not found. Creating a new one...")
        index, documents = await create_faiss_index()
        if index is None or documents is None:
            return []

    print(f"Encoding query: {query}")
    query_embedding = embedder.encode([query], convert_to_numpy=True)

    print("Performing FAISS search...")
    distances, indices = index.search(query_embedding, top_k)

    # Convert the relevant documents into readable strings
    relevant_docs = []
    for idx in indices[0]:
        if idx < len(documents):
            doc = documents[idx]
            relevant_docs.append(doc)
    
    return relevant_docs
    
class EventService:
    def __init__(self):
        self.db = None
        self.event_collection = None
        self.prompt_collection = None
        self.purchase_collection = None

    async def initialize(self):
        if not self.db:
            self.db = await get_database()
            self.event_collection = self.db.events
            self.prompt_collection = self.db.prompts
            self.purchase_collection = self.db.purchases
            self.user_collection = self.db.users

    @staticmethod
    async def get_instance():
        service = EventService()
        await service.initialize()
        return service

    @classmethod
    async def save_event(cls, event: EventCreate):
        service = await cls.get_instance()
        event_dict = event.dict()
        event_dict["timestamp"] = datetime.now()
        result = await service.event_collection.insert_one(event_dict)
        return await service.event_collection.find_one({"_id": result.inserted_id})

    @classmethod
    async def get_all_events(cls, skip: int = 0, limit: int = 10):
        service = await cls.get_instance()
        total = await service.event_collection.count_documents({})
        events = await service.event_collection.find().sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
        return events, total

    @classmethod
    async def get_user_events(cls, ip_address: str, skip: int = 0, limit: int = 10):
        service = await cls.get_instance()
        total = await service.event_collection.count_documents({"ip_address": ip_address})
        events = await service.event_collection.find(
            {"ip_address": ip_address}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
        return events, total

    @classmethod
    async def delete_event(cls, hash: str):
        service = await cls.get_instance()
        result = await service.event_collection.delete_many({"hash": hash})
        return result.deleted_count > 0

    @classmethod
    async def get_all_prompts(cls, skip: int = 0, limit: int = 10):
        service = await cls.get_instance()
        total = await service.prompt_collection.count_documents({})
        prompts = await service.prompt_collection.find().sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
        return prompts, total

    @classmethod
    async def get_all_purchases(cls, skip: int = 0, limit: int = 10):
        service = await cls.get_instance()
        total = await service.purchase_collection.count_documents({})
        purchases = await service.purchase_collection.find().sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
        return purchases, total

    @classmethod
    async def get_user_prompts(cls, ip_address: str, skip: int = 0, limit: int = 10):
        service = await cls.get_instance()
        total = await service.prompt_collection.count_documents({"ip_address": ip_address})
        events = await service.prompt_collection.find(
            {"ip_address": ip_address}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
        return events, total

    @classmethod
    async def delete_prompt(cls, hash: str):
        service = await cls.get_instance()
        result = await service.prompt_collection.delete_one({"hash": hash})
        return result.deleted_count > 0

    @classmethod
    async def get_prompt_event(cls, hash: str):
        service = await cls.get_instance()
        events = await service.event_collection.find({"hash": hash}).sort("timestamp").to_list(100)
        prompt = []
        for event in events:
            if event["event_type"] == "visit":
                url = event['details']['url']
            col = {"event_type": event["event_type"], "details": event["details"]}
            prompt.append(col)
            ip_address = event["ip_address"]

        try:
            question = "Did the user's checkout process succeed or fail? \
                Answer: (Respond only with 'success' or 'fail'. No extra text.)"
            reason_question = "Why are users leaving before completing checkout? \
                (Privide a concise summary under 100 word.) \
                Answer:"
            response = await generate_answer(question, prompt)
            reason = await generate_answer(reason_question, prompt)
            print(reason)
            await service.prompt_collection.insert_one({
                "hash": hash,
                "ip_address": ip_address,
                "url": url,
                "response": response,
                "prompt": prompt,
                "reason": reason,
                "timestamp": datetime.now()
            })

            return prompt
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    async def get_summary_event(cls, ip_address: str):
        service = await cls.get_instance()
        events = await service.event_collection.find({"ip_address": ip_address}).sort("timestamp").to_list(30)
        prompt = []
        for event in events:
            col = {"event_type": event["event_type"], "details": event["details"]}
            prompt.append(col)
        
        try: 
            input = f"""
                {prompt}
                Summarize the user event concisely.
            """
            headers = {
                "Authorization": f"Bearer {TOGETHER_API_KEY2}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
                "messages": [{"role": "user", "content": input}],
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(TOGETHER_API_URL, headers=headers, json=payload)

            response_json = response.json()
            print(response_json)
            content_text = response_json["choices"][0]["message"]["content"]
            
            return content_text
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    async def get_reasoning_event(cls, id: str):
        service = await cls.get_instance()
        event = await service.purchase_collection.find_one({"_id": ObjectId(id)})
        if not event:
            return {"error": "Purchase record not found"}
        prompt = {"steps": event["steps"], "status": event["status"], "error:": event["error"], "created_at": event["created_at"]}
        try: 
            input = f"""
                {prompt}
                Analyze the purchase processing.
                If the purchase failed, provide a reason.
            """
            headers = {
                "Authorization": f"Bearer {TOGETHER_API_KEY2}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
                "messages": [{"role": "user", "content": input}],
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(TOGETHER_API_URL, headers=headers, json=payload)

            response_json = response.json()
            print(response_json)
            content_text = response_json["choices"][0]["message"]["content"]
            
            return content_text
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    async def get_test(cls, url: str):
        try:
            input = f"""
                {url}
                analyze this url and give me concisely answer.
            """
            headers = {
                "Authorization": f"Bearer {TOGETHER_API_KEY2}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
                "messages": [{"role": "user", "content": input}],
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(TOGETHER_API_URL, headers=headers, json=payload)

            response_json = response.json()
            print(response_json)
            content_text = response_json["choices"][0]["message"]["content"]

            return content_text
        except Exception as e:
            return {"error": str(e)}
    
    @classmethod
    async def get_chat(cls, query: str):
        """Generate a response using RAG (retrieval-augmented generation) with Llama"""
        print("Retrieving relevant documents...")

        # Ensure we retrieve both FAISS index and documents
        index, documents = await create_faiss_index()

        if index is None or documents is None:
            return "No data available to generate a response."

        relevant_docs = await retrieve_relevant_documents(query, documents)

        if not relevant_docs:
            return "No relevant documents found."

        # Combine retrieved documents into context
        context = " ".join(relevant_docs)[:2000]  # Truncate to avoid exceeding model limits
        input_prompt = f"User query: {query} give me concisely answer.\nContext: {context}\nAnswer:"
        print("test prompt:", input_prompt)
        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY2}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            "messages": [{"role": "user", "content": input_prompt}],
        }

        print("Sending request to Together API...")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(TOGETHER_API_URL, headers=headers, json=payload)
            response_json = response.json()
            together_answer = response_json["choices"][0]["message"]["content"]
        except Exception as e:
            together_answer = f"Error with Together API: {str(e)}"

        return together_answer
