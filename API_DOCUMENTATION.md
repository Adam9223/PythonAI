# PythonAI FastAPI Documentation

## Overview

The PythonAI FastAPI server provides programmatic access to the AI chatbot, financial data analysis, and chart generation. All API requests require authentication via JWT tokens.

**Base URL:** `http://localhost:8000`

**Interactive API Docs:**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Authentication Flow

### Step 1: Generate API Key

Generate a new API key (first time only or when credentials are lost).

```bash
curl -X GET "http://localhost:8000/api/auth/generate-key"
```

**Response:**

```json
{
  "api_key": "t7h9k2x5m8p1q4r6s9w2v3c5d8e1f4g7",
  "created_at": "2026-03-06T15:30:45.123456",
  "expires_at": null
}
```

### Step 2: Exchange API Key for JWT Token

Get a JWT token valid for 24 hours.

```bash
curl -X POST "http://localhost:8000/api/auth/token?api_key=YOUR_API_KEY"
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Step 3: Use Token in Requests

Include the token in the `Authorization` header for all subsequent requests:

```bash
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## API Endpoints

### 1. Health Check (No Auth Required)

Check if the API is running.

```
GET /api/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-03-06T15:30:45.123456"
}
```

**Example:**

```bash
curl http://localhost:8000/api/health
```

---

### 2. Chat Endpoint

Send a message to the AI chatbot.

```
POST /api/chat
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json
```

**Request Body:**

```json
{
  "message": "Give me the current balance",
  "use_live_data": false
}
```

**Response:**

```json
{
  "success": true,
  "response": "The current General Ledger running balance is 336.1 million...",
  "timestamp": "2026-03-06T15:30:45.123456",
  "message_type": "text"
}
```

**Example - Text Response:**

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me the current balance"}'
```

**Example - Chart Response:**

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "show me the credit and debit chart"}'
```

**Response (Chart):**

```json
{
  "success": true,
  "response": {
    "type": "chart",
    "chartType": "bar",
    "title": "General Ledger - Debits vs Credits",
    "chartData": {
      "labels": ["2026-01", "2026-01", "2026-02", ...],
      "datasets": [
        {
          "label": "Debits",
          "data": [1250000, 1300000, ...],
          "backgroundColor": "rgba(102, 126, 234, 0.8)"
        },
        {
          "label": "Credits",
          "data": [950000, 1050000, ...],
          "backgroundColor": "rgba(237, 100, 166, 0.8)"
        }
      ]
    }
  },
  "timestamp": "2026-03-06T15:30:45.123456",
  "message_type": "chart"
}
```

---

### 3. Balance Endpoint

Get current balance information with optional chart.

```
GET /api/balance
Authorization: Bearer YOUR_TOKEN
```

**Query Parameters:**

- `data_source` (string): `"general_ledger"` or `"stock_card"` (default: `"general_ledger"`)
- `use_live_data` (boolean): Fetch from live website data (default: `false`)

**Response:**

```json
{
  "success": true,
  "data_source": "general_ledger",
  "response": "The current General Ledger running balance is 336.1 million...",
  "is_chart": false,
  "timestamp": "2026-03-06T15:30:45.123456"
}
```

**Example:**

```bash
# Get General Ledger balance
curl "http://localhost:8000/api/balance?data_source=general_ledger" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get balance from live website data
curl "http://localhost:8000/api/balance?data_source=general_ledger&use_live_data=true" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 4. Chart Endpoint

Generate a chart with specific type.

```
POST /api/chart
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json
```

**Request Body:**

```json
{
  "chart_type": "line",
  "message": "credit and debit data"
}
```

**Supported Chart Types:**

- `"line"` - Line chart (time series)
- `"bar"` - Bar chart (comparisons)
- `"pie"` - Pie chart (proportions)

**Response:**

```json
{
  "success": true,
  "chart_type": "line",
  "data": {
    "type": "chart",
    "chartType": "line",
    "title": "General Ledger - Debits vs Credits",
    "chartData": { ... }
  },
  "timestamp": "2026-03-06T15:30:45.123456"
}
```

**Examples:**

```bash
# Get line chart
curl -X POST "http://localhost:8000/api/chart" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chart_type": "line", "message": "balance evolution"}'

# Get bar chart
curl -X POST "http://localhost:8000/api/chart" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chart_type": "bar", "message": "credit and debit comparison"}'

# Get pie chart
curl -X POST "http://localhost:8000/api/chart" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chart_type": "pie", "message": "total debits vs credits"}'
```

---

### 5. Inventory Endpoint

Get inventory/stock card information.

```
GET /api/inventory
Authorization: Bearer YOUR_TOKEN
```

**Query Parameters:**

- `search_term` (string, optional): Search for specific inventory items

**Response:**

```json
{
  "success": true,
  "data": "Current inventory status...",
  "timestamp": "2026-03-06T15:30:45.123456"
}
```

**Examples:**

```bash
# Get overall inventory status
curl "http://localhost:8000/api/inventory" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Search for specific item
curl "http://localhost:8000/api/inventory?search_term=widgets" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Error Responses

### 401 Unauthorized

```json
{
  "detail": "Invalid API key"
}
```

### 401 Token Expired

```json
{
  "detail": "Token expired"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Python Client Example

```python
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
API_KEY = "your_api_key_here"

class PythonAIClient:
    def __init__(self, api_key, base_url=BASE_URL):
        self.api_key = api_key
        self.base_url = base_url
        self.token = None
        self.authenticate()

    def authenticate(self):
        """Get JWT token from API key"""
        response = requests.post(
            f"{self.base_url}/api/auth/token",
            params={"api_key": self.api_key}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def _get_headers(self):
        """Get headers with authentication"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def chat(self, message, use_live_data=False):
        """Send message to AI"""
        response = requests.post(
            f"{self.base_url}/api/chat",
            headers=self._get_headers(),
            json={
                "message": message,
                "use_live_data": use_live_data
            }
        )
        response.raise_for_status()
        return response.json()

    def get_balance(self, data_source="general_ledger", use_live_data=False):
        """Get balance information"""
        response = requests.get(
            f"{self.base_url}/api/balance",
            headers=self._get_headers(),
            params={
                "data_source": data_source,
                "use_live_data": use_live_data
            }
        )
        response.raise_for_status()
        return response.json()

    def get_chart(self, chart_type, message):
        """Generate chart"""
        response = requests.post(
            f"{self.base_url}/api/chart",
            headers=self._get_headers(),
            json={
                "chart_type": chart_type,
                "message": message
            }
        )
        response.raise_for_status()
        return response.json()

    def get_inventory(self, search_term=None):
        """Get inventory information"""
        response = requests.get(
            f"{self.base_url}/api/inventory",
            headers=self._get_headers(),
            params={"search_term": search_term} if search_term else {}
        )
        response.raise_for_status()
        return response.json()

# Usage
if __name__ == "__main__":
    # Create client
    client = PythonAIClient(API_KEY)

    # Chat example
    result = client.chat("Give me the current balance")
    print("AI Response:", result["response"])

    # Balance example
    balance = client.get_balance()
    print("Balance:", balance)

    # Chart example
    chart = client.get_chart("line", "balance evolution")
    print("Chart Data:", chart["data"]["chartData"]["labels"])

    # Inventory example
    inventory = client.get_inventory()
    print("Inventory:", inventory)
```

---

## Node.js/JavaScript Client Example

```javascript
const axios = require("axios");

class PythonAIClient {
  constructor(apiKey, baseUrl = "http://localhost:8000") {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
    this.token = null;
  }

  async authenticate() {
    const response = await axios.post(`${this.baseUrl}/api/auth/token`, null, {
      params: { api_key: this.apiKey },
    });
    this.token = response.data.access_token;
  }

  getHeaders() {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
    };
  }

  async chat(message, useLiveData = false) {
    const response = await axios.post(
      `${this.baseUrl}/api/chat`,
      { message, use_live_data: useLiveData },
      { headers: this.getHeaders() },
    );
    return response.data;
  }

  async getBalance(dataSource = "general_ledger", useLiveData = false) {
    const response = await axios.get(`${this.baseUrl}/api/balance`, {
      params: { data_source: dataSource, use_live_data: useLiveData },
      headers: this.getHeaders(),
    });
    return response.data;
  }

  async getChart(chartType, message) {
    const response = await axios.post(
      `${this.baseUrl}/api/chart`,
      { chart_type: chartType, message },
      { headers: this.getHeaders() },
    );
    return response.data;
  }

  async getInventory(searchTerm = null) {
    const response = await axios.get(`${this.baseUrl}/api/inventory`, {
      params: searchTerm ? { search_term: searchTerm } : {},
      headers: this.getHeaders(),
    });
    return response.data;
  }
}

// Usage
(async () => {
  const client = new PythonAIClient("your_api_key_here");
  await client.authenticate();

  const result = await client.chat("What is the balance?");
  console.log("Response:", result.response);

  const chart = await client.getChart("line", "balance evolution");
  console.log("Chart labels:", chart.data.chartData.labels);
})();
```

---

## Live Data Integration

When `use_live_data=true` is set, the API will:

1. Attempt to fetch real-time data from configured website sources
2. Fall back to sample data if live sources are unavailable
3. Cache results for 90 seconds to reduce requests

### Configuring Live Data Sources

Edit `scraper_config.json` to specify website URLs and data extraction patterns.

---

## Rate Limiting & Best Practices

- JWT tokens expire after 24 hours. Generate a new one using your API key.
- Each API request updates the `last_used` timestamp for your API key.
- Cache responses when possible to reduce server load.
- Live data is cached for 90 seconds; repeated calls within that window return cached data.

---

## Troubleshooting

**401 Unauthorized - Invalid API Key**

- Generate a new API key: `GET /api/auth/generate-key`
- Verify you're using the correct token format: `Bearer YOUR_TOKEN`

**401 Token Expired**

- Get a new token: `POST /api/auth/token?api_key=YOUR_KEY`

**Connection Refused**

- Ensure FastAPI server is running: `lsof -i :8000`
- Start server: `uvicorn fastapi_server:app --host 0.0.0.0 --port 8000`

**Chart data empty in response**

- Verify `use_live_data=false` or that website is accessible
- Check `gl_sample_data.json` exists in project root

---

## Support

For issues or feature requests, check the documentation or examine the Python code in `fastapi_server.py`.
