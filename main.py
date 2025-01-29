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

SESSION_EXPIRY = timedelta(minutes=10)  # Prevents repeated hits within 10 mins

class URLRequest(BaseModel):
    url: str

@app.post("/register")
def register_url(request: URLRequest):
    """Register a URL for tracking and return an ID."""
    url_id = str(uuid4())
    urls_collection.insert_one({"_id": url_id, "url": request.url, "views": 0})
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

@app.get("/stats/{url_id}")
def get_stats(url_id: str):
    """Retrieve the stats for a given URL ID."""
    url_data = urls_collection.find_one({"_id": url_id})
    if not url_data:
        raise HTTPException(status_code=404, detail="URL ID not found")
    return {"url": url_data["url"], "views": url_data["views"]}
