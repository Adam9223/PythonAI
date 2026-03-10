# PythonAI Backend Architecture

## 🎯 Primary Use: Backend API for External Applications

Your PythonAI is now a **backend service** that other websites and applications call via REST API.

```
┌─────────────────────────────────────────────────────────┐
│                  External Applications                   │
│    (Your Website, Mobile App, Desktop Software, etc.)    │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP/REST API Calls
                   ▼
        ┌──────────────────────┐
        │  FastAPI Backend     │  ← PRIMARY
        │  (Port 8000)         │    Production use
        │  - JWT Auth          │
        │  - 7 Endpoints       │
        └──────────────────────┘
                   ▲
                   │ (Optional Testing)
                   │
        ┌──────────────────────┐
        │  Web UI (Port 3000)  │  ← SECONDARY
        │  Development/Testing │    For testing AI updates
        │  (Keep Available)    │
        └──────────────────────┘
```

---

## 📡 Primary Entry Point: FastAPI (Port 8000)

### Start the Backend Server

```bash
cd /Users/mcbair/Desktop/pythonbotAI
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload
```

### How External Apps Use It

```python
# Your website backend calls this
import requests

BASE_URL = "http://your-pythonai-server:8000"

# Get token
api_key_resp = requests.post(f"{BASE_URL}/api/auth/generate-key")
api_key = api_key_resp.json()["api_key"]

token_resp = requests.post(f"{BASE_URL}/api/auth/token?api_key={api_key}")
jwt_token = token_resp.json()["access_token"]

# Make requests
headers = {"Authorization": f"Bearer {jwt_token}"}

# Chat with AI
chat = requests.post(
    f"{BASE_URL}/api/chat",
    headers=headers,
    json={"message": "What's the balance?"}
)
print(chat.json()["response"])

# Get chart data
chart = requests.post(
    f"{BASE_URL}/api/chart",
    headers=headers,
    json={"chart_type": "line", "message": "balance evolution"}
)
```

---

## 🧪 Secondary (Testing): Web UI (Port 3000)

### Start the UI for Testing

```bash
cd /Users/mcbair/Desktop/pythonbotAI
npm start
```

### When to Use

- ✅ Manual testing of AI responses
- ✅ Testing new features
- ✅ Debugging chat functionality
- ✅ Verifying chart generation
- ✅ Checking UI/UX changes

### When NOT to Use

- ❌ Don't expose to end users (use API instead)
- ❌ User queries should go through your website → FastAPI
- ❌ Not meant for production traffic

---

## 🚀 Startup Instructions

### Option A: API Only (Production)

```bash
# Terminal 1: FastAPI Server (Main)
cd /Users/mcbair/Desktop/pythonbotAI
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload
```

External applications call: `http://your-server:8000/api/chat` (with JWT token)

### Option B: API + UI for Testing

```bash
# Terminal 1: FastAPI Server (Main)
cd /Users/mcbair/Desktop/pythonbotAI
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Web UI (For Testing)
cd /Users/mcbair/Desktop/pythonbotAI
npm start
```

- External apps call: `http://your-server:8000/api/*`
- You test internally at: `http://localhost:3000`

---

## 📋 Deployment Architecture

```
Your Website                         Your Website
(Frontend)                          (Backend)
    │                                   │
    └───────────────────────────────────┤
                                        │
                    ┌───────────────────▼──────────────────┐
                    │    Your Server / Cloud Provider      │
                    │                                      │
                    │  ┌────────────────────────────────┐  │
                    │  │  FastAPI Backend  (Port 8000)  │  │
                    │  │  - Chat API                    │  │
                    │  │  - Balance/Chart API           │  │
                    │  │  - Inventory API               │  │
                    │  │  - JWT Authentication          │  │
                    │  └────────────────────────────────┘  │
                    │                                      │
                    │  ┌────────────────────────────────┐  │
                    │  │  Web UI (Port 3000) - Optional │  │
                    │  │  (For Dev/Testing Only)        │  │
                    │  └────────────────────────────────┘  │
                    │                                      │
                    │  ┌────────────────────────────────┐  │
                    │  │  Data Sources                  │  │
                    │  │ • GL Sample Data               │  │
                    │  │ • Live Website Data            │  │
                    │  │ • Conversation History         │  │
                    │  └────────────────────────────────┘  │
                    │                                      │
                    └──────────────────────────────────────┘

Your End Users access through YOUR website/app, not directly to PythonAI
```

---

## 🔐 Security for External Use

### API Keys & JWT

- Generate API key (once per client)
- Exchange for JWT token (valid 24 hours)
- Include JWT in all requests
- Tokens automatically expire
- API keys can be revoked

### Example: Your Website Backend

```javascript
// Your website backend
const axios = require("axios");

const PYTHONAI_URL = process.env.PYTHONAI_SERVER; // e.g., http://pythonai.yourserver.com:8000
const PYTHONAI_API_KEY = process.env.PYTHONAI_API_KEY; // Store securely

class PythonAIClient {
  async initialize() {
    // Get JWT token on startup
    const tokenResp = await axios.post(
      `${PYTHONAI_URL}/api/auth/token?api_key=${PYTHONAI_API_KEY}`,
    );
    this.token = tokenResp.data.access_token;
  }

  async chat(userMessage) {
    // Your website users send messages here
    const response = await axios.post(
      `${PYTHONAI_URL}/api/chat`,
      { message: userMessage },
      { headers: { Authorization: `Bearer ${this.token}` } },
    );
    return response.data.response;
  }
}

module.exports = new PythonAIClient();
```

---

## 📚 API Endpoints (What Your External App Calls)

| Endpoint                 | Method | Purpose                   | Auth |
| ------------------------ | ------ | ------------------------- | ---- |
| `/api/health`            | GET    | Check if service is alive | ❌   |
| `/api/auth/generate-key` | POST   | Get API key (one-time)    | ❌   |
| `/api/auth/token`        | POST   | Get JWT token             | ✅   |
| `/api/chat`              | POST   | Chat with AI              | ✅   |
| `/api/balance`           | GET    | Get GL/stock balance      | ✅   |
| `/api/chart`             | POST   | Generate chart            | ✅   |
| `/api/inventory`         | GET    | Get inventory             | ✅   |

---

## 🧪 Testing & Development Workflow

### 1. Make Changes to AI

Edit `main.py` to improve responses, add features, etc.

### 2. Test Changes

```bash
# Option A: Use Web UI (Easiest)
curl http://localhost:3000
# Type messages and see responses

# Option B: Use API with Testing Script
bash test_fastapi_quickstart.sh

# Option C: Use Swagger UI
curl http://localhost:8000/docs
# Test endpoints interactively
```

### 3. Verify with API

```bash
# Make sure your API calls work correctly for external apps
curl -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Test message"}'
```

### 4. Deploy to Production

Copy to your server and restart FastAPI:

```bash
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app \
  --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🎯 Key Points

✅ **FastAPI (8000) is PRIMARY** - This is what external apps/websites call  
✅ **Web UI (3000) is SECONDARY** - Keep for internal testing only  
✅ **Don't expose UI to users** - Route them through your website  
✅ **Keep Both Running** - UI for dev, API for production  
✅ **API is stateless** - Each request is independent  
✅ **Authentication required** - API key + JWT tokens

---

## 📊 Usage Statistics (Monitoring)

Check `api_keys.json` to see:

- How many requests each client made
- Last time API key was used
- When each key was created

```bash
cat api_keys.json | python3 -m json.tool
```

---

## 🚀 Production Deployment Checklist

- [ ] Change SECRET_KEY in `fastapi_server.py` (not default)
- [ ] Use domain name instead of IP for API calls
- [ ] Enable HTTPS (use nginx/Apache as reverse proxy)
- [ ] Set up monitoring/logging
- [ ] Create API keys for each external application
- [ ] Document API usage for your clients
- [ ] Set up backup for `api_keys.json`
- [ ] Plan for capacity (number of concurrent users)
- [ ] Keep UI disabled in production (or password protect)

---

## 📞 Your Workflow

```
You Update AI
    ↓
Restart FastAPI (8000)
    ↓
Test with UI (3000) or test script
    ↓
Verify with API calls
    ↓
Deploy to production
    ↓
External apps continue calling API
    ↓
Your website users see updated responses
```

---

## 💡 Example: Your Real Website Integration

```html
<!-- Your website -->
<div id="chat">
  <input type="text" id="message" placeholder="Ask anything..." />
  <button onclick="sendMessage()">Send</button>
  <div id="response"></div>
</div>

<script>
  async function sendMessage() {
    const message = document.getElementById("message").value;

    // Call YOUR website backend
    const response = await fetch("/api/ai-chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    const data = await response.json();
    document.getElementById("response").innerHTML = data.response;
  }
</script>

<!-- Your backend (Node.js/Python) -->
// POST /api/ai-chat async function handleAIChat(req, res) { // Your backend
calls PythonAI FastAPI const pythonaiResponse = await axios.post(
'http://pythonai-server:8000/api/chat', { message: req.body.message }, {
headers: { 'Authorization': `Bearer ${JWT_TOKEN}` } } ); // Return to frontend
res.json(pythonaiResponse.data); }
```

---

**Your PythonAI is now a production backend service.** 🎉

External applications (your website, mobile app, etc.) call the FastAPI endpoints with proper authentication, while you maintain the Web UI for testing and development purposes.
