# Next Steps: Connecting AI to Live clone.ulap.biz Stock Card

## Current Status

✅ **Backend Ready:**
- AI backend supports cookie, CSRF tokens, custom auth headers, and extra header forwarding
- Error diagnostics now show exact upstream HTTP status/body/URL
- Scraper config loads from correct path (`config/scraper_config.json`)
- JSON API mode configured for `POST https://clone.ulap.biz/api/reports/inv/sc`

❌ **Connection Blocked:**
- All authentication attempts return `401 Missing token.`
- Tested token (`eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...`) doesn't authenticate
- Tested formats: 16 header combinations + 6 cookie variations = all rejected

## What the Token Likely Needs

The token you provided may be:
1. **Expired** - JWT `exp: 1773154184` may be past current server time
2. **Wrong secret** - Server validates with different key
3. **Requires session** - Needs browser session cookie + JWT together
4. **Different flow** - Token is for frontend auth, API needs separate backend token

## How to Fix This (Action Required)

### Option 1: Capture Working Browser Request (Recommended)

1. **Open your working frontend** where you're logged into clone.ulap.biz
2. **Open Chrome DevTools** (F12) → Network tab
3. **Load the Stock Card page** or make inventory request
4. **Find the successful `/api/reports/inv/sc` request**
5. **Right-click → Copy → Copy as cURL**
6. **Send me the cURL command** (or paste headers/cookies below)

I'll extract the exact working headers/cookies and configure the AI backend to match.

### Option 2: Get Fresh Token from Frontend

If your frontend has a token refresh/renewal function:

```javascript
// In your frontend console or code:
console.log('Token:', localStorage.getItem('token'));
console.log('Cookies:', document.cookie);
console.log('Session:', sessionStorage);
```

Send me all three outputs.

### Option 3: Use Backend-to-Backend Auth

If clone.ulap.biz has a machine/service account or API key system:

1. Create service account credentials
2. Get long-lived API key/secret
3. Add to `config/scraper_config.json`:

```json
{
  "company_website": {
    "url": "https://clone.ulap.biz/api/reports/inv/sc",
    "is_json_api": true,
    "api_method": "POST",
    "api_fixed_auth_header": "API-Key",
    "api_fixed_auth_value": "your-service-account-key-here"
  }
}
```

## Testing Once Configured

After you provide working auth details, test with:

```bash
cd pythonbotAI
python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request('http://localhost:8000/api/auth/generate-key', method='POST')
api_key = json.loads(urllib.request.urlopen(req).read().decode())['api_key']
req = urllib.request.Request(f'http://localhost:8000/api/auth/token?api_key={api_key}', method='POST')
ai_token = json.loads(urllib.request.urlopen(req).read().decode())['access_token']

# Replace with working auth details you provide
payload = {
  'category': 'all',
  'user_auth_token': 'YOUR_WORKING_TOKEN',
  'user_cookie': 'session=YOUR_SESSION_COOKIE',
  'csrf_token': 'YOUR_CSRF_TOKEN',
  'auth_header_name': 'Authorization',  # or x-access-token, etc.
  'csrf_header_name': 'X-CSRF-Token'
}

body = json.dumps(payload).encode()
req = urllib.request.Request('http://localhost:8000/api/inventory', data=body, method='POST', headers={
  'Authorization': f'Bearer {ai_token}',
  'Content-Type': 'application/json'
})
result = urllib.request.urlopen(req).read().decode()
print(result)
PY
```

Look for:
- ✅ `"success": true` with real inventory data
- ❌ `Status: 401` → auth still wrong
- ❌ `Status: 403` → auth works but permissions issue
- ❌ `Status: 500` → server error (different issue)

## What I've Already Built

1. **WebScraper** accepts:
   - `auth_token`
   - `auth_header_name` (custom header like `x-access-token`)
   - `cookies` (dict or raw Cookie header string)
   - `csrf_token`
   - `csrf_header_name`
   - `extra_headers` (dict for other required headers)

2. **FastAPI /api/inventory endpoint** accepts all fields in request body

3. **Frontend integration code** updated in:
   - [examples/frontend_integration_example.js](../examples/frontend_integration_example.js)
   - [docs/FRONTEND_INTEGRATION_GUIDE.md](FRONTEND_INTEGRATION_GUIDE.md)

4. **Error diagnostics** now show:
   - Upstream URL
   - HTTP method
   - Status code
   - Response body preview

## Summary

**AI backend is 100% ready to connect.** The only remaining blocker is getting valid authentication credentials that match what your browser uses successfully.

**Next step:** Capture a working browser request and send me the headers/cookies, OR get a fresh token from your logged-in frontend session.
