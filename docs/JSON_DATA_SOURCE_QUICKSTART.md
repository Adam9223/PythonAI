# ✅ JSON File Data Source - QUICK START

## 🎉 Good News!

Web scraping is now **optional**. Your AI can read from `company_data.json` instead!

---

## ⚡ How to Use (3 Steps)

### Step 1: Edit `company_data.json`

The file is already created with sample data. Update it with your real data:

```bash
open company_data.json
```

Or create your own from scratch:

```json
{
  "company_name": "Your Company Name",
  "last_updated": "2026-03-06",

  "inventory": [
    {
      "product_name": "Item 1",
      "quantity": 100,
      "unit": "pcs",
      "location": "Warehouse A",
      "status": "In Stock"
    }
  ],

  "general_ledger": {
    "current_balance": 336100000,
    "currency": "USD",
    "last_transaction_date": "2026-03-05"
  }
}
```

### Step 2: Start the API

```bash
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --port 8000
```

### Step 3: Ask Questions!

```bash
# Get API key
API_KEY=$(curl -s -X POST http://localhost:8000/api/auth/generate-key | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")

# Get token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/token?api_key=$API_KEY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Ask about inventory
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What inventory do we have?"}'

# Ask about balance
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the balance?"}'
```

---

## 🔄 How to Update Data

### Option A: Manual Edit

```bash
open company_data.json
# Edit the file, save
# AI instantly sees new data (no restart needed!)
```

### Option B: Script/Export

Export from your system → Convert to JSON → Replace file

### Option C: Automated Script

Create a cron job or script that updates `company_data.json` daily:

```bash
#!/bin/bash
# fetch_data.sh - Run this daily
curl https://your-api.com/export > company_data.json
```

---

## 📋 Full Field Reference

### Inventory Item Fields

```json
{
  "product_code": "ABC-123", // Optional
  "product_name": "Widget A", // Required
  "quantity": 150, // Required
  "unit": "pcs", // Required
  "location": "Warehouse 1", // Optional
  "reorder_level": 50, // Optional
  "status": "In Stock" // Optional
}
```

### General Ledger Fields

```json
{
  "current_balance": 336100000, // Required
  "currency": "USD", // Required
  "fiscal_year": "2026", // Optional
  "last_transaction_date": "2026-03-05", // Optional
  "account_status": "Active" // Optional
}
```

### Financial Summary (Optional)

```json
{
  "total_assets": 450000000,
  "total_liabilities": 113900000,
  "equity": 336100000,
  "currency": "USD"
}
```

---

## ✅ Advantages vs Web Scraping

| Feature                | JSON File       | Web Scraping     |
| ---------------------- | --------------- | ---------------- |
| **Works immediately**  | ✅ Yes          | ❌ Needs config  |
| **No authentication**  | ✅ Yes          | ❌ Often blocked |
| **No firewall issues** | ✅ Yes          | ❌ Often blocked |
| **Easy to update**     | ✅ Edit file    | ❌ HTML changes  |
| **Version control**    | ✅ Git friendly | ❌ N/A           |
| **Real-time**          | ⚠️ Manual       | ✅ If working    |

---

## 🧪 Test It Now!

```bash
# 1. Start API
/Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --port 8000 &

# 2. Wait 3 seconds
sleep 3

# 3. Test
curl -X POST http://localhost:8000/api/auth/generate-key
```

You should see your API key!

---

## 💡 Tips

1. **Start with JSON** - Get it working, then add API/database later
2. **Keep it simple** - Only add fields you actually need
3. **Update regularly** - Set up daily/weekly data refresh
4. **Version control** - Commit `company_data.json` to track changes
5. **Backup** - Keep a copy in case of accidental edits

---

## 🐛 Troubleshooting

**Q: AI says "Inventory not found"**  
A: Make sure `company_data.json` exists and has an `"inventory"` field

**Q: Balance shows old data**  
A: Update `last_updated` field and restart API

**Q: Can I use both JSON and web scraping?**  
A: Yes! JSON takes priority. If missing, AI falls back to scraper.

**Q: How do I go back to web scraping?**  
A: Delete or rename `company_data.json`

---

## 🚀 Next Steps

Once JSON works:

1. ✅ Set up automated export from your ERP
2. ✅ Add more fields as needed
3. ✅ Consider REST API for real-time data
4. ✅ Add database connection for production

---

**You're all set! Web scraping is now optional.** 🎉
