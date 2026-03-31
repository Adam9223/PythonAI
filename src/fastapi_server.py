"""
FastAPI Server for PythonAI with Authentication
Provides API endpoints for chat, charts, and data retrieval
Supports both sample data and live website data
"""

from fastapi import FastAPI, HTTPException, Depends, status, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
import secrets
import base64
import requests as http_requests
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from .main import respond, handle_balance_request, handle_inventory_request, handle_chart_request
from .web_scraper import WebScraper

# Security configuration
SECRET_KEY = os.getenv("API_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
API_KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "api_keys.json")

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
    user_auth_token: Optional[str] = None  # Frontend's auth token for target website


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
    user_auth_token: Optional[str] = None  # Frontend's auth token for target website


class InventoryRequest(BaseModel):
    category: Optional[str] = "all"
    user_auth_token: Optional[str] = None  # Frontend's auth token for target website
    user_cookie: Optional[str] = None  # Raw Cookie header from frontend session
    csrf_token: Optional[str] = None
    auth_header_name: Optional[str] = "Authorization"
    csrf_header_name: Optional[str] = "X-CSRF-Token"
    extra_headers: Optional[Dict[str, str]] = None


class GLAccountsRequest(BaseModel):
    user_auth_token: Optional[str] = None  # Frontend auth token for target website
    user_cookie: Optional[str] = None  # Raw Cookie header from frontend session
    auth_header_name: Optional[str] = "x-access-tokens"
    extra_headers: Optional[Dict[str, str]] = None


class GLReportRequest(BaseModel):
    user_auth_token: Optional[str] = None
    user_cookie: Optional[str] = None
    auth_header_name: Optional[str] = "x-access-tokens"
    extra_headers: Optional[Dict[str, str]] = None


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


# Stored site token (updated daily via PUT /api/config/site-token or POST /api/config/auto-login)
_site_token: Optional[str] = None

SCRAPER_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")


def resolve_site_token(request_token: Optional[str]) -> Optional[str]:
    """Return the request-level token if provided, otherwise fall back to the stored one."""
    return request_token if request_token else _site_token


def parse_cookie_header(cookie_header: Optional[str]) -> Dict[str, str]:
    """Parse raw Cookie header format into requests-compatible cookie dict."""
    if not cookie_header or not isinstance(cookie_header, str):
        return {}

    cookies: Dict[str, str] = {}
    for part in cookie_header.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _to_bool(value: Any) -> bool:
    """Convert mixed request flag types to bool safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _grouped_mode(payload: Dict[str, Any]) -> bool:
    """Treat any supported grouping flag as grouped mode."""
    flags = ["group_by_branch", "group_by_location", "per_branch", "per_location"]
    return any(_to_bool(payload.get(flag)) for flag in flags)


def _group_dimension(payload: Dict[str, Any]) -> str:
    """Resolve whether grouping is by branch or location."""
    if _to_bool(payload.get("group_by_location")) or _to_bool(payload.get("per_location")):
        return "location"
    return "branch"


def _extract_rows(data: Any) -> List[Dict[str, Any]]:
    """Extract row records from common API response shapes."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]

    if not isinstance(data, dict):
        return []

    candidates = [
        data.get("rep"),
        data.get("rows"),
        data.get("items"),
        data.get("data"),
    ]
    nested_data = data.get("data") if isinstance(data.get("data"), dict) else None
    if nested_data:
        candidates.extend([
            nested_data.get("rep"),
            nested_data.get("rows"),
            nested_data.get("items"),
        ])

    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]

    return []


def _to_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _resolve_time_bucket(row: Dict[str, Any]) -> str:
    for key in ["jDate", "date", "dt", "YrMo", "bucket", "period", "month", "dDate"]:
        val = row.get(key)
        if val is not None and str(val).strip() != "":
            return str(val)
    return "Unknown"


def _resolve_group_name(row: Dict[str, Any], dimension: str) -> str:
    branch_keys = ["sBrch", "branchName", "branch", "brch", "sBranch", "warehouse", "ixBrch"]
    location_keys = ["location", "sLoc", "sLocation", "loc", "warehouse", "ixWH"]
    keys = location_keys if dimension == "location" else branch_keys

    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip() != "":
            return str(val)
    return "Unknown"


def _normalize_gl_row(row: Dict[str, Any], dimension: str) -> Dict[str, Any]:
    """Normalize row into stable keys for grouped charting/reporting."""
    dr = _to_number(row.get("Dr", row.get("tDr", row.get("debit", row.get("Debit", 0)))))
    cr = _to_number(row.get("Cr", row.get("tCr", row.get("credit", row.get("Credit", 0)))))
    run_bal = _to_number(row.get("runBal", row.get("endBal", row.get("balance", row.get("Bal", 0)))))
    group_value = _resolve_group_name(row, dimension)

    normalized = {
        "jDate": _resolve_time_bucket(row),
        "Dr": dr,
        "Cr": cr,
        "runBal": run_bal,
    }
    if dimension == "location":
        normalized["location"] = group_value
    else:
        normalized["sBrch"] = group_value
    return normalized


def _build_grouped_rep(rows: List[Dict[str, Any]], dimension: str) -> List[Dict[str, Any]]:
    return [_normalize_gl_row(row, dimension) for row in rows]


def _build_grouped_series(rep_rows: List[Dict[str, Any]], dimension: str) -> Dict[str, Any]:
    """Build stable grouped time-series output without duplicating combined totals per group."""
    id_key = "location" if dimension == "location" else "sBrch"
    labels: List[str] = []
    label_seen = set()
    for row in rep_rows:
        bucket = row.get("jDate", "Unknown")
        if bucket not in label_seen:
            label_seen.add(bucket)
            labels.append(bucket)

    # Aggregate by group + time bucket.
    grouped: Dict[str, Dict[str, Dict[str, float]]] = {}
    for row in rep_rows:
        group_name = str(row.get(id_key, "Unknown"))
        bucket = str(row.get("jDate", "Unknown"))
        grp = grouped.setdefault(group_name, {})
        acc = grp.setdefault(bucket, {"Dr": 0.0, "Cr": 0.0, "runBal": 0.0, "count": 0})
        acc["Dr"] += _to_number(row.get("Dr", 0))
        acc["Cr"] += _to_number(row.get("Cr", 0))
        # Use latest encountered running balance for bucket.
        acc["runBal"] = _to_number(row.get("runBal", 0))
        acc["count"] += 1

    series = []
    for group_name, by_bucket in grouped.items():
        debit_values = []
        credit_values = []
        run_bal_values = []
        for bucket in labels:
            metrics = by_bucket.get(bucket, {"Dr": 0.0, "Cr": 0.0, "runBal": 0.0})
            debit_values.append(metrics["Dr"])
            credit_values.append(metrics["Cr"])
            run_bal_values.append(metrics["runBal"])

        series.append({
            "name": group_name,
            id_key: group_name,
            "debit": debit_values,
            "credit": credit_values,
            "runBal": run_bal_values,
            "data": run_bal_values,
        })

    return {
        "labels": labels,
        "series": series,
    }


def _load_scraper_section(section_name: str) -> Dict[str, Any]:
    """Load one config section from canonical scraper config file."""
    if not os.path.exists(SCRAPER_CONFIG_FILE):
        return {}

    with open(SCRAPER_CONFIG_FILE, "r") as f:
        config = json.load(f)
    section = config.get(section_name, {})
    return section if isinstance(section, dict) else {}


def _list_scraper_config_keys() -> List[str]:
    if not os.path.exists(SCRAPER_CONFIG_FILE):
        return []
    try:
        with open(SCRAPER_CONFIG_FILE, "r") as f:
            config = json.load(f)
        if isinstance(config, dict):
            return sorted(list(config.keys()))
    except Exception:
        pass
    return []


def _extract_gl_proxy_auth(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract optional auth transport fields from flat endpoint payload."""
    if not isinstance(payload, dict):
        return {
            "user_auth_token": None,
            "user_cookie": None,
            "auth_header_name": "x-access-tokens",
            "extra_headers": None,
        }

    return {
        "user_auth_token": payload.pop("user_auth_token", None),
        "user_cookie": payload.pop("user_cookie", None),
        "auth_header_name": payload.pop("auth_header_name", "x-access-tokens"),
        "extra_headers": payload.pop("extra_headers", None),
    }


def _proxy_gl_endpoint(
    section_name: str,
    payload: Dict[str, Any],
    auth: Dict[str, Any],
    grouped_output: bool,
    fallback_payload_for_rows: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Proxy GL endpoint with optional backend grouping transformation."""
    scraper_config = _load_scraper_section(section_name)
    if not scraper_config:
        available = _list_scraper_config_keys()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Missing '{section_name}' config in scraper_config.json at {SCRAPER_CONFIG_FILE}. "
                f"Available sections: {available}"
            )
        )

    url = scraper_config.get("url")
    method = scraper_config.get("api_method", "POST")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing URL for config section '{section_name}'"
        )

    cookies = parse_cookie_header(auth.get("user_cookie"))
    resolved_token = resolve_site_token(auth.get("user_auth_token"))
    header_name = auth.get("auth_header_name") or scraper_config.get("api_fixed_auth_header", "x-access-tokens")

    scraper = WebScraper(
        proxy=None,
        auth_token=resolved_token,
        auth_header_name=header_name,
        cookies=cookies,
        extra_headers=auth.get("extra_headers"),
        config=scraper_config,
    )
    result = scraper.fetch_json_api(url, method=method, payload=payload)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch upstream GL endpoint: {result.get('error')}"
        )

    if not grouped_output:
        return {
            "success": True,
            "grouped": False,
            "data": result,
            "timestamp": datetime.utcnow().isoformat(),
        }

    dimension = _group_dimension(payload)

    # Prefer current endpoint rows; fallback to /api/reports/gl rows for graph endpoint.
    rows = _extract_rows(result)
    if not rows and isinstance(fallback_payload_for_rows, dict):
        report_config = _load_scraper_section("general_ledger_report")
        report_url = report_config.get("url")
        report_method = report_config.get("api_method", "POST")
        if report_url:
            report_scraper = WebScraper(
                proxy=None,
                auth_token=resolved_token,
                auth_header_name=header_name,
                cookies=cookies,
                extra_headers=auth.get("extra_headers"),
                config=report_config,
            )
            report_result = report_scraper.fetch_json_api(report_url, method=report_method, payload=fallback_payload_for_rows)
            if "error" not in report_result:
                rows = _extract_rows(report_result)

    rep = _build_grouped_rep(rows, dimension)
    grouped_series = _build_grouped_series(rep, dimension)

    return {
        "success": True,
        "grouped": True,
        "group_dimension": dimension,
        "labels": grouped_series.get("labels", []),
        "series": grouped_series.get("series", []),
        "rep": rep,
        "source": "backend_grouped_aggregation",
        "timestamp": datetime.utcnow().isoformat(),
    }


def _update_scraper_config_token(token: str):
    """Write the new token into every entry in scraper_config.json."""
    try:
        with open(SCRAPER_CONFIG_FILE, "r") as f:
            config = json.load(f)
        for section in config.values():
            if isinstance(section, dict) and "api_fixed_auth_token" in section:
                section["api_fixed_auth_token"] = token
        with open(SCRAPER_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: could not update scraper_config.json: {e}")


def perform_site_login() -> str:
    """
    Log in to clone.ulap.biz using credentials from .env,
    return the access token, and persist it to scraper_config.json.
    """
    username = os.getenv("SITE_USERNAME", "")
    password = os.getenv("SITE_PASSWORD", "")
    dev_id = os.getenv("SITE_DEV_ID", "")
    login_url = os.getenv("SITE_LOGIN_URL", "https://clone.ulap.biz/api/login")
    token_field = os.getenv("SITE_TOKEN_FIELD", "token")

    if not username or not password:
        raise ValueError("SITE_USERNAME and SITE_PASSWORD must be set in .env")

    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if dev_id:
        headers["Cookie"] = f"devID={dev_id}"

    resp = http_requests.get(login_url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Try configured field, then common fallbacks
    token = (
        data.get(token_field)
        or data.get("token")
        or data.get("access_token")
        or (data.get("data") or {}).get("token")
    )
    if not token:
        raise ValueError(f"Token not found in login response. Keys returned: {list(data.keys())}")

    global _site_token
    _site_token = token
    _update_scraper_config_token(token)
    return token


# API Endpoints

@app.on_event("startup")
async def startup_auto_login():
    """Attempt auto-login at startup when SITE_USERNAME/SITE_PASSWORD are configured."""
    if os.getenv("SITE_USERNAME") and os.getenv("SITE_PASSWORD"):
        try:
            perform_site_login()
            print("[Startup] Site token refreshed via auto-login")
        except Exception as e:
            print(f"[Startup] Auto-login failed: {e}")


@app.post("/api/config/auto-login")
async def trigger_auto_login(
    api_key: str = Depends(verify_token)
):
    """
    Perform login against the target site using .env credentials
    and refresh the token used by live-data scraping.
    """
    try:
        perform_site_login()
        return {"success": True, "message": "Auto-login successful. Site token refreshed."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto-login failed: {e}"
        )

@app.put("/api/config/site-token")
async def update_site_token(
    token: str,
    api_key: str = Depends(verify_token)
):
    """
    Store the daily site token used to access the target website.
    Call this once after logging in each day — all subsequent requests
    will use it automatically unless you pass user_auth_token explicitly.

    Example:
    PUT /api/config/site-token?token=YOUR_DAILY_TOKEN
    Headers: Authorization: Bearer YOUR_JWT
    """
    global _site_token
    _site_token = token
    _update_scraper_config_token(token)
    return {"success": True, "message": "Site token updated successfully"}


@app.get("/api/config/site-token")
async def get_site_token_status(
    api_key: str = Depends(verify_token)
):
    """Check whether a site token is currently stored (does not reveal the token value)."""
    return {"token_set": _site_token is not None}


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
        auth_context = {
            "user_auth_token": resolve_site_token(request.user_auth_token)
        }
        response = respond(request.message, auth_context=auth_context)
        
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
            elif isinstance(response, dict):
                if response.get('type') == 'chart':
                    message_type = "chart"
                elif response.get('type') == 'branches_request':
                    # Fetch branches data
                    try:
                        if not _site_token:
                            response = "No site token available. Please call /api/config/auto-login first."
                            message_type = "error"
                        else:
                            headers = {
                                "x-access-tokens": _site_token,
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                                "Cookie": f"devID={os.getenv('SITE_DEV_ID', '')}",
                                "Referer": "https://clone.ulap.biz/app/reports/sc",
                            }
                            resp = http_requests.get(
                                "https://clone.ulap.biz/api/lib/brch",
                                headers=headers,
                                timeout=10
                            )
                            resp.raise_for_status()
                            branches_data = resp.json()
                            
                            # Format branches for display
                            if isinstance(branches_data, list) and len(branches_data) > 0:
                                branch_list = "\n".join([
                                    f"• {b.get('brch', b.get('name', 'Unknown'))}"
                                    for b in branches_data[:20]
                                ])
                                response = f"Available branches:\n\n{branch_list}"
                                if len(branches_data) > 20:
                                    response += f"\n\n...and {len(branches_data) - 20} more."
                            elif isinstance(branches_data, dict):
                                response = f"Branches data: {json.dumps(branches_data, indent=2)}"
                            else:
                                response = f"Branches data retrieved successfully."
                            message_type = "text"
                    except Exception as e:
                        response = f"Error fetching branches: {str(e)}"
                        message_type = "error"
        
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
        
        auth_context = {"user_auth_token": resolve_site_token(None)}
        response = handle_balance_request(prompt, auth_context=auth_context)
        
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
    Generate a chart with specific type or fetch live chart data
    
    Parameters:
    - chart_type: 'line', 'bar', or 'pie'
    - message: The context/request about the chart
    """
    try:
        # Try to fetch live chart data first
        chart_result = handle_chart_request(request.message, auth_context={"user_auth_token": resolve_site_token(None)})
        
        if chart_result and isinstance(chart_result, dict) and chart_result.get('type') == 'chart':
            # Got live chart data
            return {
                "success": True,
                "chart_type": request.chart_type,
                "data": chart_result,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Fallback: use AI to generate chart
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


@app.post("/api/inventory")
async def get_inventory(
    request: InventoryRequest,
    api_key: str = Depends(verify_token)
):
    """
    Get inventory/stock card information
    
    Body:
    - category: Optional category filter (default: "all")
    - user_auth_token: Optional auth token from frontend for target website
    - user_cookie: Optional raw Cookie header from frontend session
    - csrf_token: Optional CSRF token value
    - auth_header_name: Optional auth header name override (e.g., x-access-token)
    - csrf_header_name: Optional CSRF header name override
    - extra_headers: Optional additional headers map
    """
    try:
        prompt = f"Show me the current inventory status"
        auth_context = {
            "user_auth_token": resolve_site_token(request.user_auth_token),
            "user_cookie": request.user_cookie,
            "csrf_token": request.csrf_token,
            "auth_header_name": request.auth_header_name,
            "csrf_header_name": request.csrf_header_name,
            "extra_headers": request.extra_headers,
        }
        
        response = handle_inventory_request(prompt, auth_context=auth_context)
        
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


@app.post("/api/general-ledger/accounts")
async def get_general_ledger_accounts(
    request: GLAccountsRequest,
    api_key: str = Depends(verify_token)
):
    """
    Fetch General Ledger account library from clone.ulap.biz `/api/lib/acc`.

    Body:
    - user_auth_token: Optional token override; stored site token is used if omitted
    - user_cookie: Optional raw Cookie header
    - auth_header_name: Optional auth header override (default: x-access-tokens)
    - extra_headers: Optional additional headers
    """
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")
        scraper_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                full_config = json.load(f)
                scraper_config = full_config.get("general_ledger_accounts", {})

        cookies = parse_cookie_header(request.user_cookie)
        resolved_token = resolve_site_token(request.user_auth_token)
        header_name = request.auth_header_name or scraper_config.get("api_fixed_auth_header", "x-access-tokens")

        scraper = WebScraper(
            proxy=None,
            auth_token=resolved_token,
            auth_header_name=header_name,
            cookies=cookies,
            extra_headers=request.extra_headers,
            config=scraper_config,
        )
        result = scraper.fetch_general_ledger_accounts()

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch general ledger accounts: {result.get('error')}"
            )

        return {
            "success": True,
            "data_source": "general_ledger_accounts",
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/api/reports/gl")
async def post_general_ledger_report(
    payload: Dict[str, Any] = Body(default_factory=dict),
    api_key: str = Depends(verify_token)
):
    """
    Proxy and normalize General Ledger report rows.

    Grouped mode is enabled when any of these flags is true:
    - group_by_branch, group_by_location, per_branch, per_location
    """
    try:
        request_payload = dict(payload) if isinstance(payload, dict) else {}
        auth = _extract_gl_proxy_auth(request_payload)
        grouped = _grouped_mode(request_payload)
        return _proxy_gl_endpoint(
            section_name="general_ledger_report",
            payload=request_payload,
            auth=auth,
            grouped_output=grouped,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/api/reports/gl/graph")
async def post_general_ledger_graph(
    payload: Dict[str, Any] = Body(default_factory=dict),
    api_key: str = Depends(verify_token)
):
    """
    Proxy and normalize General Ledger graph data.

    In grouped mode, backend rebuilds series per branch/location to avoid
    duplicated combined totals repeated under multiple group names.
    """
    try:
        request_payload = dict(payload) if isinstance(payload, dict) else {}
        auth = _extract_gl_proxy_auth(request_payload)
        grouped = _grouped_mode(request_payload)
        return _proxy_gl_endpoint(
            section_name="general_ledger_graph",
            payload=request_payload,
            auth=auth,
            grouped_output=grouped,
            fallback_payload_for_rows=request_payload,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Keep GET endpoint for backward compatibility
@app.get("/api/inventory")
async def get_inventory_legacy(
    search_term: Optional[str] = None,
    api_key: str = Depends(verify_token)
):
    """
    Get inventory/stock card information (legacy GET endpoint)
    
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


@app.get("/api/branches")
async def get_branches(
    api_key: str = Depends(verify_token)
):
    """
    Get list of branches/warehouses from the target site.
    Uses the stored site token to authenticate.
    
    Returns:
    - List of branches with their IDs and names
    """
    try:
        if not _site_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No site token available. Call /api/config/auto-login first."
            )
        
        headers = {
            "x-access-tokens": _site_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": f"devID={os.getenv('SITE_DEV_ID', '')}",
            "Referer": "https://clone.ulap.biz/app/reports/sc",
        }
        
        resp = http_requests.get(
            "https://clone.ulap.biz/api/lib/brch",
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        
        data = resp.json()
        
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch branches: {str(e)}"
        )
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
