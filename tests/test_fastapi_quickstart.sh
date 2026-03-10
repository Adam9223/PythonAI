#!/bin/bash

# PythonAI FastAPI - Quick Start Guide
# This script demonstrates how to use the FastAPI endpoints

BASE_URL="http://localhost:8000"

echo "╔════════════════════════════════════════════════════════╗"
echo "║     PythonAI FastAPI Quick Start                       ║"
echo "║     Interactive API Testing                            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Health Check (no auth needed)
echo "📊 Step 1: Check API Health"
echo "─────────────────────────────────────────────────────────"
echo "Command: curl $BASE_URL/api/health"
echo ""

HEALTH=$(curl -s "$BASE_URL/api/health")
echo "Response:"
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
echo ""

# Step 2: Generate API Key
echo "🔐 Step 2: Generate API Key"
echo "─────────────────────────────────────────────────────────"
echo "Command: curl -X POST $BASE_URL/api/auth/generate-key"
echo ""

API_KEY_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/generate-key")
API_KEY=$(echo "$API_KEY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('api_key', 'ERROR'))" 2>/dev/null)

echo "Response:"
echo "$API_KEY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$API_KEY_RESPONSE"
echo ""

if [ "$API_KEY" = "ERROR" ] || [ -z "$API_KEY" ]; then
  echo "❌ Failed to generate API key"
  exit 1
fi

echo "✅ Generated API Key: ${API_KEY:0:20}..."
echo ""

# Step 3: Get JWT Token
echo "🔑 Step 3: Exchange API Key for JWT Token"
echo "─────────────────────────────────────────────────────────"
echo "Command: curl -X POST \"$BASE_URL/api/auth/token?api_key=YOUR_API_KEY\""
echo ""

TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/token?api_key=$API_KEY")
JWT_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', 'ERROR'))" 2>/dev/null)

echo "Response:"
echo "$TOKEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$TOKEN_RESPONSE"
echo ""

if [ "$JWT_TOKEN" = "ERROR" ] || [ -z "$JWT_TOKEN" ]; then
  echo "❌ Failed to get JWT token"
  exit 1
fi

echo "✅ Got JWT Token: ${JWT_TOKEN:0:30}..."
echo ""

# Step 4: Test Chat Endpoint
echo "💬 Step 4: Test Chat Endpoint"
echo "─────────────────────────────────────────────────────────"
echo "Command:"
echo "curl -X POST \"$BASE_URL/api/chat\" \\"
echo "  -H \"Authorization: Bearer YOUR_TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"message\": \"Give me the current balance\"}'"
echo ""

CHAT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/chat" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me the current balance"}')

echo "Response:"
echo "$CHAT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CHAT_RESPONSE"
echo ""

# Step 5: Test Balance Endpoint
echo "💰 Step 5: Get Balance Information"
echo "─────────────────────────────────────────────────────────"
echo "Command:"
echo "curl \"$BASE_URL/api/balance\" \\"
echo "  -H \"Authorization: Bearer YOUR_TOKEN\""
echo ""

BALANCE_RESPONSE=$(curl -s "$BASE_URL/api/balance" \
  -H "Authorization: Bearer $JWT_TOKEN")

echo "Response:"
echo "$BALANCE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$BALANCE_RESPONSE"
echo ""

# Step 6: Test Chart Endpoint
echo "📈 Step 6: Generate Line Chart"
echo "─────────────────────────────────────────────────────────"
echo "Command:"
echo "curl -X POST \"$BASE_URL/api/chart\" \\"
echo "  -H \"Authorization: Bearer YOUR_TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"chart_type\": \"line\", \"message\": \"balance evolution\"}'"
echo ""

CHART_RESPONSE=$(curl -s -X POST "$BASE_URL/api/chart" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chart_type": "line", "message": "balance evolution"}')

echo "Response (first 500 chars):"
echo "$CHART_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(json.dumps(data, indent=2)[:500] + '...')" 2>/dev/null || echo "${CHART_RESPONSE:0:500}..."
echo ""

echo "╔════════════════════════════════════════════════════════╗"
echo "║  ✅ Quick Start Complete!                             ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📚 For detailed documentation, see API_DOCUMENTATION.md"
echo ""
echo "🎯 Next Steps:"
echo "  1. Save your API_KEY: $API_KEY"
echo "  2. Use the JWT_TOKEN in your application"
echo "  3. Read API_DOCUMENTATION.md for all endpoints"
echo "  4. Check out example clients in that doc"
echo ""
echo "🌐 Interactive Docs:"
echo "  - Swagger UI: http://localhost:8000/docs"
echo "  - ReDoc: http://localhost:8000/redoc"
echo ""
