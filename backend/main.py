import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .agent import process_chat_message, get_sanitized_config
from .database import ensure_db_initialized

app = FastAPI(title="Secure AI Insights API")

@app.on_event("startup")
def _startup() -> None:
    ensure_db_initialized()


# Allow the local frontend to communicate with backend (dev default)
CORS_ALLOW_ORIGIN_REGEX = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def read_root():
    return {"status": "Backend is running securely."}


@app.get("/api/debug-config")
def debug_config():
    return get_sanitized_config()

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for the frontend chat interface to talk to the AI.
    It returns the AI's answer along with any tool traces for explainability.
    """
    try:
        result = await process_chat_message(request.message)
        return {
            "answer": result["answer"],
            "traces": result["traces"]
        }
    except Exception as e:
        return {"answer": f"An error occurred: {str(e)}", "traces": []}