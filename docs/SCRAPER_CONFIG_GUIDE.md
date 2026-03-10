# Scraper Configuration Guide

## 🔧 How to Update `scraper_config.json`

### Current Issue

The scraper is looking for inventory data at:

- `localhost:3000/api` (internal server, not the real company website)
- `reports/inv/sc` (relative paths without domain)

### What You Need to Do

1. **Replace `your-company-domain.com`** with your actual company website URL
2. **Update `inventory_paths`** with the correct paths to your Stock Card/Inventory pages
3. **Update `products_selector`** if your HTML structure is different

---

## 📝 Configuration Fields

### `url` (Required)

The base website domain - should be a real public URL, not localhost

```json
"url": "https://your-company-domain.com"
```

### `inventory_paths` (Required)

List of possible paths where inventory/stock card data might be found. The scraper will try each one.

```json
"inventory_paths": [
  "/inventory",
  "/stock-card",
  "/api/inventory",
  "/reports/inventory"
]
```

### `selector` (Required)

CSS selectors to extract content from the page

```json
"selector": "div.content, p, table, tr, td"
```

### `products_selector` (Optional)

Specific selector for product rows/items in tables

```json
"products_selector": "tr, .product-item, .inventory-row"
```

### `fallback_urls` (Optional)

Alternative URLs to try if the main `url` + `inventory_paths` don't work

```json
"fallback_urls": [
  "https://your-company-domain.com/inventory",
  "https://your-company-domain.com/api/stock-card"
]
```

---

## 🎯 Example Configurations

### Example 1: Simple Company Site

```json
{
  "company_website": {
    "url": "https://acme-corp.com",
    "inventory_paths": ["/inventory", "/products"],
    "selector": "table, tr, td"
  }
}
```

### Example 2: Enterprise System with API

```json
{
  "company_website": {
    "url": "https://erp.mycompany.com",
    "inventory_paths": [
      "/api/v1/inventory",
      "/api/v1/stock-card",
      "/inventory/list",
      "/reports/stock"
    ],
    "selector": "tbody tr, .data-table-row",
    "products_selector": "tr[data-product-id]"
  }
}
```

### Example 3: With Fallbacks

```json
{
  "company_website": {
    "url": "https://warehouse.example.com",
    "inventory_paths": ["/sc", "/stock-card"],
    "selector": "div.inventory-content",
    "fallback_urls": [
      "https://backup-warehouse.example.com/inventory",
      "https://reports.example.com/stock-card"
    ]
  }
}
```

---

## 🔍 How to Find the Right Paths

1. **Go to your company website** in a browser
2. **Navigate to the Stock Card / Inventory section**
3. **Look at the URL** in the address bar
   - Example: `https://mycompany.com/reports/inv/sc`
   - The path is: `/reports/inv/sc`
4. **Add that path** to `inventory_paths`

### Common Paths by System

| System         | Common Paths                                         |
| -------------- | ---------------------------------------------------- |
| SAP            | `/sap/inventory`, `/mm/stock-card`, `/api/inventory` |
| Oracle EBS     | `/oracle/inventory`, `/apps/inventory`               |
| NetSuite       | `/app/inventory`, `/api/inventory`                   |
| Custom Web App | `/inventory`, `/products`, `/stock`                  |
| REST API       | `/api/inventory`, `/api/v1/products`                 |

---

## ⚙️ Testing Your Configuration

After updating `scraper_config.json`, test with:

```bash
# Test the Python bot directly
python3 main.py
```

Then try asking:

```
What inventory do we have?
Show me the stock cards
List the products
```

Or use the API:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Show inventory"}'
```

If it still doesn't work, the scraper will print debug info showing which URLs it tried.

---

## 🐛 Debugging

Look for this message when you ask for inventory:

```
Attempted URLs:
```

It will show all the URLs the scraper tried. Use this to identify:

1. Did it try the right paths?
2. Are the URLs accessible?
3. Do they return valid HTML?

---

## 📋 Quick Checklist

- [ ] Replaced `your-company-domain.com` with real domain
- [ ] Added correct inventory page paths
- [ ] Tested by asking "What inventory do we have?"
- [ ] Checked debug output for which URLs were tried
- [ ] Updated `products_selector` if needed (usually not)

---

## Questions?

If inventory still won't load:

1. Verify the URLs work in your browser
2. Check if the site requires authentication (might need firewall bypass)
3. Inspect the HTML to find correct CSS selectors
4. Add the correct paths to `fallback_urls`
