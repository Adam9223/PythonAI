"""
FastAPI Server for PythonAI with Authentication
Provides API endpoints for chat, charts, and data retrieval
Supports both sample data and live website data
"""

from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
import secrets
from datetime import datetime, timedelta
import jwt

from main import respond, handle_balance_request, handle_inventory_request

# Security configuration
SECRET_KEY = os.getenv("API_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
API_KEYS_FILE = "api_keys.json"

# Initialize FastAPI app
app = FastAPI(
    title="PythonAI API",
    description="AI-powered chatbot API with authentication for financial data analysis",
    version="1.0.0"
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_token(authorization: str = Header(None)) -> str:
    """Verify JWT token from Authorization header and return API key"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Use: Bearer <token>"
        )
    
    token = parts[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        api_key = payload.get('api_key')
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Verify API key still exists and is valid
        api_keys = load_api_keys()
        if api_key not in api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key revoked"
            )
        
        return api_key
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    use_live_data: Optional[bool] = False


class ChatResponse(BaseModel):
    success: bool
    response: Any
    timestamp: str
    message_type: str  # "text", "chart", "error"


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class APIKeyResponse(BaseModel):
    api_key: str
    created_at: str
    expires_at: Optional[str] = None


class BalanceRequest(BaseModel):
    data_source: str = "general_ledger"  # "general_ledger" or "stock_card"
    use_live_data: Optional[bool] = False


class ChartTypeRequest(BaseModel):
    chart_type: str  # "line", "bar", "pie"
    message: str


# API Key Management
def load_api_keys() -> Dict[str, Dict]:
    """Load API keys from file"""
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_api_keys(keys: Dict[str, Dict]):
    """Save API keys to file"""
    with open(API_KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)


def create_jwt_token(api_key: str, expires_in_hours: int = 24) -> tuple:
    """Create JWT token from API key"""
    payload = {
        'api_key': api_key,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, payload['exp']


# API Endpoints

@app.post("/api/auth/generate-key", response_model=APIKeyResponse)
async def generate_api_key():
    """
    Generate a new API key for authentication
    Use this to get initial access, then exchange for JWT token
    """
    api_key = secrets.token_urlsafe(32)
    api_keys = load_api_keys()
    
    api_keys[api_key] = {
        'created_at': datetime.utcnow().isoformat(),
        'last_used': None,
        'requests_count': 0
    }
    
    save_api_keys(api_keys)
    
    return APIKeyResponse(
        api_key=api_key,
        created_at=datetime.utcnow().isoformat(),
        expires_at=None  # API keys don't expire unless explicitly revoked
    )


@app.post("/api/auth/token", response_model=AuthResponse)
async def get_token(api_key: str):
    """
    Exchange API key for JWT token
    Use the JWT token in Authorization header for subsequent requests
    
    Example:
    1. POST /api/auth/generate-key → get api_key
    2. POST /api/auth/token?api_key=YOUR_KEY → get access_token
    3. Use in header: Authorization: Bearer YOUR_TOKEN
    """
    api_keys = load_api_keys()
    
    if api_key not in api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    token, exp = create_jwt_token(api_key)
    
    # Update last used timestamp
    api_keys[api_key]['last_used'] = datetime.utcnow().isoformat()
    save_api_keys(api_keys)
    
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400  # 24 hours in seconds
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    api_key: str = Depends(verify_token)
):
    """
    Send a message to the AI chatbot
    
    Authentication: Include JWT token in Authorization header
    Example: Authorization: Bearer YOUR_TOKEN
    
    Parameters:
    - message: The user message
    - use_live_data: Whether to fetch live data from websites (default: False)
    """
    try:
        # Update API key usage stats
        api_keys = load_api_keys()
        api_keys[api_key]['requests_count'] = api_keys[api_key].get('requests_count', 0) + 1
        api_keys[api_key]['last_used'] = datetime.utcnow().isoformat()
        save_api_keys(api_keys)
        
        # Get AI response
        response = respond(request.message)
        
        # Handle case where AI cannot answer (returns None)
        if response is None:
            response = "I'm having trouble processing that request. Could you rephrase or ask something else?"
            message_type = "text"
        else:
            # Determine response type
            message_type = "text"
            if isinstance(response, str):
                try:
                    data = json.loads(response)
                    if data.get('type') == 'chart':
                        message_type = "chart"
                        response = data
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(response, dict) and response.get('type') == 'chart':
                message_type = "chart"
        
        return ChatResponse(
            success=True,
            response=response,
            timestamp=datetime.utcnow().isoformat(),
            message_type=message_type
        )
    
    except Exception as e:
        return ChatResponse(
            success=False,
            response=str(e),
            timestamp=datetime.utcnow().isoformat(),
            message_type="error"
        )


@app.get("/api/balance")
async def get_balance(
    data_source: str = "general_ledger",
    use_live_data: bool = False,
    api_key: str = Depends(verify_token)
):
    """
    Get current balance information
    
    Parameters:
    - data_source: 'general_ledger' or 'stock_card'
    - use_live_data: Fetch live data from websites
    
    Returns balance data and optionally a chart
    """
    try:
        prompt = f"What is the {data_source} balance?"
        if use_live_data:
            prompt += " Use live data from the website."
        
        response = handle_balance_request(prompt)
        
        is_chart = False
        if isinstance(response, str):
            try:
                data = json.loads(response)
                if data.get('type') == 'chart':
                    is_chart = True
                    response = data
            except (json.JSONDecodeError, TypeError):
                pass
        
        return {
            "success": True,
            "data_source": data_source,
            "response": response,
            "is_chart": is_chart,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/api/chart")
async def get_chart(
    request: ChartTypeRequest,
    api_key: str = Depends(verify_token)
):
    """
    Generate a chart with specific type
    
    Parameters:
    - chart_type: 'line', 'bar', or 'pie'
    - message: The context/request about the chart
    """
    try:
        full_message = f"Show me {request.message} as a {request.chart_type} chart"
        response = respond(full_message)
        
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                pass
        
        return {
            "success": True,
            "chart_type": request.chart_type,
            "data": response,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/inventory")
async def get_inventory(
    search_term: Optional[str] = None,
    api_key: str = Depends(verify_token)
):
    """
    Get inventory/stock card information
    
    Parameters:
    - search_term: Optional search term for specific items
    """
    try:
        if search_term:
            prompt = f"Tell me about the inventory for {search_term}"
        else:
            prompt = "Show me the current inventory status"
        
        response = handle_inventory_request(prompt)
        
        return {
            "success": True,
            "data": response,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint (no authentication required)"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/docs", include_in_schema=False)
async def docs_redirect():
    """Redirect to Swagger UI"""
    return {"docs_url": "/docs", "redoc_url": "/redoc"}


if __name__ == "__main__":
    import uvicorn
    
    # Print startup instructions
    print("""
    ╔════════════════════════════════════════╗
    ║   PythonAI FastAPI Server               ║
    ║   Version 1.0.0                         ║
    ╚════════════════════════════════════════╝
    
    Starting FastAPI server on http://localhost:8000
    
    📚 API Documentation:
    - Swagger UI: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
    
    🔐 Authentication Flow:
    1. GET http://localhost:8000/api/auth/generate-key
       → Returns: {"api_key": "YOUR_API_KEY", ...}
    
    2. POST http://localhost:8000/api/auth/token?api_key=YOUR_API_KEY
       → Returns: {"access_token": "YOUR_JWT_TOKEN", ...}
    
    3. Use token in requests:
       Authorization: Bearer YOUR_JWT_TOKEN
    
    💬 Example Chat Request:
    POST /api/chat
    Headers: Authorization: Bearer YOUR_JWT_TOKEN
    Body: {"message": "Give me the current balance"}
    
    """)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
