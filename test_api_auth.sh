#!/bin/bash

# Test API Authentication and Usage
# This script shows you how to properly authenticate with the API

API_URL="http://localhost:8000"

echo "🔐 PythonAI API Authentication Test"
echo "===================================="
echo ""

# Step 1: Check if API is running
echo "1️⃣ Checking if API is running..."
HEALTH=$(curl -s ${API_URL}/api/health)
if [ $? -ne 0 ]; then
    echo "❌ Error: API is not running!"
    echo "   Start it with: /Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --port 8000"
    exit 1
fi
echo "✅ API is running: $HEALTH"
echo ""

# Step 2: Generate API Key
echo "2️⃣ Generating API Key..."
API_KEY_RESPONSE=$(curl -s -X POST ${API_URL}/api/auth/generate-key)
API_KEY=$(echo $API_KEY_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['api_key'])")
echo "✅ API Key: $API_KEY"
echo ""

# Step 3: Get JWT Token
echo "3️⃣ Getting JWT Token..."
TOKEN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/token?api_key=${API_KEY}")
JWT_TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "✅ JWT Token: ${JWT_TOKEN:0:50}..."
echo ""

# Step 4: Test Chat Endpoint
echo "4️⃣ Testing Chat Endpoint..."
CHAT_RESPONSE=$(curl -s -X POST ${API_URL}/api/chat \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the balance?"}')
echo "✅ Chat Response:"
echo "$CHAT_RESPONSE" | python3 -m json.tool
echo ""

# Step 5: Test Balance Endpoint
echo "5️⃣ Testing Balance Endpoint..."
BALANCE_RESPONSE=$(curl -s -X GET ${API_URL}/api/balance \
  -H "Authorization: Bearer ${JWT_TOKEN}")
echo "✅ Balance Response:"
echo "$BALANCE_RESPONSE" | python3 -m json.tool
echo ""

# Summary
echo "===================================="
echo "✅ All tests passed!"
echo ""
echo "📝 Save these for your code:"
echo "   API Key:  $API_KEY"
echo "   JWT Token: ${JWT_TOKEN:0:50}..."
echo ""
echo "💡 Use in your requests:"
echo '   curl -X POST http://localhost:8000/api/chat \'
echo "     -H \"Authorization: Bearer ${JWT_TOKEN}\" \\"
echo '     -H "Content-Type: application/json" \'
echo '     -d '"'"'{"message":"your message"}'"'"
echo ""
