from fastapi import FastAPI, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["view_counter"]
urls_collection = db["urls"]
sessions_collection = db["sessions"]

SESSION_EXPIRY = timedelta(minutes=5)  # Prevents repeated hits within 10 mins

class URLRequest(BaseModel):
    url: str

class URLBody(BaseModel):
    url: str

def format_url(url: str) -> str:
    """Format URL by removing protocol, www, and trailing slashes."""
    # Remove protocol
    url = url.replace("http://", "").replace("https://", "")
    # Remove trailing slashes
    url = url.rstrip("/")
    return url

def create_url(url: str) -> str:
    """Create new URL entry and return its ID."""
    url_id = str(uuid4())
    urls_collection.insert_one({"_id": url_id, "url": url, "views": 0})
    return url_id

def get_url_id(url: str) -> str:
    """Helper function to get URL ID from URL. Creates URL if not found."""
    formatted_url = format_url(url)
    url_data = urls_collection.find_one({"url": formatted_url})
    if not url_data:
        return create_url(formatted_url)
    return url_data["_id"]

@app.post("/register")
def register_url(request: URLRequest):
    """Register a URL for tracking and return an ID."""
    formatted_url = format_url(request.url)
    url_id = create_url(formatted_url)
    return {"id": url_id, "message": "URL registered successfully."}

@app.get("/view/{url_id}")
def increment_view(url_id: str, request: Request, response: Response):
    """Increment the view count if session is valid."""
    url_data = urls_collection.find_one({"_id": url_id})
    if not url_data:
        raise HTTPException(status_code=404, detail="URL ID not found")
    
    # Session Management
    client_ip = request.client.host
    session_key = f"{client_ip}_{url_id}"
    current_time = datetime.utcnow()
    
    session = sessions_collection.find_one({"_id": session_key})
    if session and current_time - session["last_view_time"] < SESSION_EXPIRY:
        return {"message": "View count not incremented (Session active)", "views": url_data["views"]}
    
    # Update session time
    sessions_collection.update_one(
        {"_id": session_key},
        {"$set": {"last_view_time": current_time}},
        upsert=True
    )
    
    # Increment view count
    urls_collection.update_one({"_id": url_id}, {"$inc": {"views": 1}})
    
    return {"message": "View counted successfully.", "views": url_data["views"] + 1}

@app.post("/view")
def increment_view_by_url(url_body: URLBody, request: Request, response: Response):
    """Increment the view count using URL from body."""
    url_id = get_url_id(url_body.url)
    return increment_view(url_id, request, response)

@app.get("/stats/{url_id}")
def get_stats(url_id: str):
    """Retrieve the stats for a given URL ID."""
    url_data = urls_collection.find_one({"_id": url_id})
    if not url_data:
        raise HTTPException(status_code=404, detail="URL ID not found")
    return {"url": url_data["url"], "views": url_data["views"]}

@app.post("/stats")
def get_stats_by_url(url_body: URLBody):
    """Retrieve the stats using URL from body."""
    url_id = get_url_id(url_body.url)
    return get_stats(url_id)
