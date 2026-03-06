# PythonAI with FastAPI - Complete Setup Guide

## 🎯 What You Now Have

A complete AI-powered financial analysis system with:

- **Web UI**: Interactive chat interface (Node.js + Express)
- **FastAPI Server**: RESTful API with authentication for programmatic access
- **Python Backend**: Core AI logic with financial data analysis
- **Authentication**: API keys + JWT tokens
- **Live Data Integration**: Ability to fetch data from websites + sample data fallback
- **Multiple Chart Types**: Line, bar, and pie charts for data visualization

---

## 🚀 Running the System

### Terminal 1: Start the Web UI (Port 3000)

```bash
cd /Users/mcbair/Desktop/pythonbotAI
npm start
```

**Access:** http://localhost:3000

### Terminal 2: Start the FastAPI Server (Port 8000)

```bash
cd /Users/mcbair/Desktop/pythonbotAI
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload
```

**Access:**

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 📡 Using the API

### Quick Start (30 seconds)

```bash
# 1. Generate API Key
curl -X POST http://localhost:8000/api/auth/generate-key

# 2. Use returned api_key to get JWT token
curl -X POST "http://localhost:8000/api/auth/token?api_key=YOUR_API_KEY"

# 3. Use token to chat
curl -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current balance?"}'
```

### Automated Quick Start

```bash
bash test_fastapi_quickstart.sh
```

This script will:

1. Check API health
2. Generate an API key
3. Get a JWT token
4. Test all major endpoints
5. Display sample responses

---

## 🔐 Authentication Flow

```
┌─────────────────────────────────────────────────────┐
│  1. Generate API Key (one-time)                     │
│     POST /api/auth/generate-key                     │
│     └─> api_key: "xyz123..."                        │
├─────────────────────────────────────────────────────┤
│  2. Get JWT Token (daily or on expiration)          │
│     POST /api/auth/token?api_key=xyz123             │
│     └─> token: "eyJhbGc..."                         │
├─────────────────────────────────────────────────────┤
│  3. Use Token in Requests                           │
│     Headers: Authorization: Bearer eyJhbGc...       │
│     ✓ POST /api/chat                                │
│     ✓ GET /api/balance                              │
│     ✓ POST /api/chart                               │
│     ✓ GET /api/inventory                            │
└─────────────────────────────────────────────────────┘
```

---

## 📚 API Endpoints

### Authentication

- `POST /api/auth/generate-key` - Get a new API key
- `POST /api/auth/token` - Exchange API key for JWT token

### Chat & Analysis

- `POST /api/chat` - Send message to AI chatbot
- `GET /api/balance` - Get GL/stock card balance with optional chart
- `POST /api/chart` - Generate chart with specific type (line/bar/pie)
- `GET /api/inventory` - Get inventory information

### System

- `GET /api/health` - Health check (no auth required)
- `GET /docs` - Interactive Swagger documentation
- `GET /redoc` - ReDoc API documentation

---

## 💻 Client Examples

### Python

```python
import requests

# Setup
BASE_URL = "http://localhost:8000"

# 1. Generate key
key_resp = requests.post(f"{BASE_URL}/api/auth/generate-key")
api_key = key_resp.json()["api_key"]

# 2. Get token
token_resp = requests.post(f"{BASE_URL}/api/auth/token",
                          params={"api_key": api_key})
jwt_token = token_resp.json()["access_token"]

# 3. Chat with AI
headers = {"Authorization": f"Bearer {jwt_token}"}
chat_resp = requests.post(
    f"{BASE_URL}/api/chat",
    headers=headers,
    json={"message": "Show me the credit and debit chart"}
)
print(chat_resp.json()["response"])

#4. Get chart
chart_resp = requests.post(
    f"{BASE_URL}/api/chart",
    headers=headers,
    json={"chart_type": "line", "message": "balance evolution"}
)
```

### JavaScript/Node.js

```javascript
const axios = require("axios");

const BASE_URL = "http://localhost:8000";

async function main() {
  // 1. Generate API key
  const keyResp = await axios.post(`${BASE_URL}/api/auth/generate-key`);
  const apiKey = keyResp.data.api_key;

  // 2. Get JWT token
  const tokenResp = await axios.post(
    `${BASE_URL}/api/auth/token?api_key=${apiKey}`,
  );
  const token = tokenResp.data.access_token;

  // 3. Chat with AI
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const chatResp = await axios.post(
    `${BASE_URL}/api/chat`,
    { message: "What is the balance?" },
    { headers },
  );

  console.log(chatResp.data.response);
}

main();
```

### cURL

```bash
# Get health
curl http://localhost:8000/api/health

# Generate key
API_KEY=$(curl -s -X POST http://localhost:8000/api/auth/generate-key | jq -r '.api_key')

# Get token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/token?api_key=$API_KEY" | jq -r '.access_token')

# Chat
curl -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me the current balance"}'

# Get balance
curl "http://localhost:8000/api/balance" \
  -H "Authorization: Bearer $TOKEN"

# Generate chart
curl -X POST "http://localhost:8000/api/chart" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chart_type": "line", "message": "balance evolution"}'
```

---

## 📊 Chart Types Supported

The AI automatically detects requested chart types:

### Line Chart

```
"Show me a historical graph of the balance"
"Give me the balance evolution as a line chart"
"Show me over time"
```

### Bar Chart

```
"Give me the credit and debit chart"  # Default
"Show me bars comparing..."
"Display as a bar chart"
```

### Pie Chart

```
"Show me as a pie chart"
"Give me a pie breakdown"
"Chart as pie"
```

---

## 📁 Project Structure

```
pythonbotAI/
├── fastapi_server.py          # FastAPI server with all endpoints
├── main.py                     # Core AI logic and response handlers
├── python_api.py               # Node.js subprocess wrapper
├── server.js                   # Express web server
├── web_scraper.py              # Website data scraping
├── public/
│   ├── index.html              # Web UI
│   ├── chat.js                 # Chat interface  + chart rendering
│   └── style.css               # UI styling
├── gl_sample_data.json         # Sample GL data (fallback)
├── conversation_store.json     # Persistent conversation history
├── scraper_config.json         # Website scraping configuration
├── api_keys.json               # Generated API keys (auto-created)
├── API_DOCUMENTATION.md        # Full API documentation
├── test_fastapi_quickstart.sh  # Interactive API testing script
└── requirements.txt            # Python dependencies
```

---

## 🌐 Data Sources

### Sample Data (Default)

- `gl_sample_data.json` - Pre-loaded GL data with 12 transaction periods
- Balance: $335.8M - $336.1M
- Full debit/credit breakdown
- Always available, no network required

### Live Data (Optional)

When `use_live_data=true` is set:

1. System attempts to fetch from configured websites
2. Falls back to sample data if websites unavailable
3. Caches results for 90 seconds to reduce requests

Configure live sources in `scraper_config.json`

---

## 🔄 Upgrade Path

The system is designed for easy upgrades:

### From Sample → Live Data

Edit `scraper_config.json` to point to your websites, then use:

```python
requests.post(
  f"{BASE_URL}/api/chat",
  headers=headers,
  json={"message": "...", "use_live_data": true}
)
```

### Adding New Data Sources

1. Add scraping logic to `web_scraper.py`
2. Add handlers in `main.py` (see `handle_balance_request`)
3. Create new FastAPI endpoints in `fastapi_server.py`

### Integrating into Your System

The FastAPI server can be accessed from:

- ✅ Python applications
- ✅ Node.js / JavaScript
- ✅ Java / C# / Go / Ruby
- ✅ Mobile apps (iOS/Android)
- ✅ Any system that can make HTTP requests

---

## 🔧 Troubleshooting

### Port Already in Use

```bash
# Port 3000 (Web UI)
lsof -i :3000
kill -9 <PID>

# Port 8000 (FastAPI)
lsof -i :8000
kill -9 <PID>
```

### API Key/Token Issues

- Generate new key: `POST /api/auth/generate-key`
- Get new token: `POST /api/auth/token?api_key=YOUR_KEY`
- Tokens expire after 24 hours

### Chart Data Not Showing

- Ensure `gl_sample_data.json` exists
- Check conversation_store.json has valid data
- Verify live website is accessible if using `use_live_data=true`

### Connection Refused

```bash
# Verify services running
lsof -i :3000    # Web UI
lsof -i :8000    # FastAPI

# Manual restart
npm start         # Terminal 1
uvicorn fastapi_server:app --host 0.0.0.0 --port 8000  # Terminal 2
```

---

## 📖 Documentation

- **API_DOCUMENTATION.md** - Complete API reference with examples
- **http://localhost:8000/docs** - Interactive Swagger UI
- **http://localhost:8000/redoc** - ReDoc interactive docs

---

## 🎓 Learning Resources

### Test the API Interactively

```bash
# Run the quick start test script
bash test_fastapi_quickstart.sh

# Or manually test in Swagger UI
# http://localhost:8000/docs
```

### View Conversation History

```bash
cat conversation_store.json | python3 -m json.tool
```

### Check Generated API Keys

```bash
cat api_keys.json | python3 -m json.tool
```

---

## ✅ Features Recap

✅ **Web UI** - Interactive chat interface  
✅ **FastAPI** - RESTful API with full authentication  
✅ **JWT Tokens** - Secure API access  
✅ **Chart Generation** - Dynamic line/bar/pie charts  
✅ **Live Data** - Website scraping integration  
✅ **Conversation Memory** - Persistent history across requests  
✅ **Context Awareness** - AI understands references to previous exchanges  
✅ **Chart Type Detection** - Automatically switches chart types on user request  
✅ **Multiple Data Sources** - GL data, inventory, custom sources  
✅ **Error Handling** - Graceful fallbacks and detailed errors

---

## 🚀 Next Steps

1. **Test the Web UI**: Open http://localhost:3000
2. **Explore the API**: Visit http://localhost:8000/docs
3. **Run Quick Start**: Execute `test_fastapi_quickstart.sh`
4. **Build Integration**: Use API_DOCUMENTATION.md for your app
5. **Configure Live Data**: Update `scraper_config.json` for your sources
6. **Customize AI**: Add new handlers to `main.py`

---

## 📞 Support

For issues or questions:

1. Check **API_DOCUMENTATION.md** for complete endpoint reference
2. Review **fastapi_server.py** for implementation details
3. Test endpoints in **http://localhost:8000/docs** Swagger UI
4. Run `bash test_fastapi_quickstart.sh` for diagnostics
5. Check logs in your terminal windows for error messages

---

**Created: March 6, 2026**  
**Version: 1.0.0**  
**Status: Production Ready** ✨
