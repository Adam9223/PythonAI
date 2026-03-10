# Frontend Authentication Integration

## Overview
The API now supports passing your frontend's authentication token to access protected backend resources (like `clone.ulap.biz`).

## How It Works

1. **Frontend Login**: Your frontend logs into the target website (e.g., `clone.ulap.biz`) and obtains a Bearer token
2. **Pass Token to API**: Include the token in API requests to this backend
3. **Backend Proxies Request**: The backend uses your token to fetch data from the protected endpoint

## API Endpoint Usage

### Inventory with Auth Token

```javascript
// Step 1: Your frontend already has the user's token after login
const userToken = localStorage.getItem('user_token'); // or from your auth system

// Step 2: Get API key and access token for THIS backend
const apiKeyResponse = await fetch('http://localhost:8000/api/auth/generate-key', {
  method: 'POST'
});
const { api_key } = await apiKeyResponse.json();

const tokenResponse = await fetch(`http://localhost:8000/api/auth/token?api_key=${api_key}`, {
  method: 'POST'
});
const { access_token } = await tokenResponse.json();

// Step 3: Call inventory endpoint with both tokens
const inventoryResponse = await fetch('http://localhost:8000/api/inventory', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,  // Auth for THIS API
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    category: 'all',
    user_auth_token: userToken  // Auth token for clone.ulap.biz
  })
});

const data = await inventoryResponse.json();
console.log(data);
```

### Chat with Auth Token

```javascript
const chatResponse = await fetch('http://localhost:8000/api/chat', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    message: 'Show me the inventory',
    user_auth_token: userToken  // Frontend's token for target website
  })
});
```

## Configuration

Update `config/scraper_config.json` to specify JSON API endpoints:

```json
{
  "company_website": {
    "url": "https://clone.ulap.biz/api/reports/inv/sc",
    "is_json_api": true,
    "api_data_path": "data",
    "description": "JSON API endpoint - requires Bearer token from frontend"
  }
}
```

## Security Notes

- The `user_auth_token` is only used to access your protected backend (clone.ulap.biz)
- This backend never stores the user's token
- The token is passed directly in the HTTP request to the target API
- Make sure to use HTTPS in production

## Example Flow

```
Frontend → THIS API (with both tokens) → clone.ulap.biz API → Response back through chain
         ↓
    access_token: For this API authentication
    user_auth_token: For clone.ulap.biz authentication
```

## Testing

```bash
# Test with curl
curl -X POST http://localhost:8000/api/inventory \
  -H "Authorization: Bearer YOUR_API_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "all",
    "user_auth_token": "YOUR_CLONE_ULAP_TOKEN"
  }'
```
