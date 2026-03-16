"""
Web Scraper Module with Proxy Support
Handles fetching and parsing data from company websites
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import base64
from typing import Dict, List, Optional
from urllib.parse import urljoin

# Configuration file for storing website URLs and proxy settings
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")


def _load_env_credentials() -> Dict[str, str]:
    """Read site credentials from environment or .env file."""
    creds = {
        "username": os.environ.get("SITE_USERNAME", ""),
        "password": os.environ.get("SITE_PASSWORD", ""),
        "dev_id": os.environ.get("SITE_DEV_ID", ""),
        "login_url": os.environ.get("SITE_LOGIN_URL", "https://clone.ulap.biz/api/login"),
        "token_field": os.environ.get("SITE_TOKEN_FIELD", "token"),
    }
    # If any key is missing, also try reading .env directly
    if not creds["username"] or not creds["password"]:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        mapping = {
                            "SITE_USERNAME": "username",
                            "SITE_PASSWORD": "password",
                            "SITE_DEV_ID": "dev_id",
                            "SITE_LOGIN_URL": "login_url",
                            "SITE_TOKEN_FIELD": "token_field",
                        }
                        if key in mapping:
                            creds[mapping[key]] = value
            except Exception:
                pass
    return creds


def _persist_token_to_config(token: str):
    """Write a new token into every api_fixed_auth_token entry in scraper_config.json."""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        for section in config.values():
            if isinstance(section, dict) and "api_fixed_auth_token" in section:
                section["api_fixed_auth_token"] = token
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[WebScraper] Failed to persist token to config: {e}")


def _perform_auto_login() -> Optional[str]:
    """
    Attempt to re-login to the target site using credentials from .env.
    Returns the new token on success, or None if credentials are not available.
    """
    creds = _load_env_credentials()
    if not creds["username"] or not creds["password"]:
        return None

    try:
        credentials = base64.b64encode(
            f"{creds['username']}:{creds['password']}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if creds["dev_id"]:
            headers["Cookie"] = f"devID={creds['dev_id']}"

        resp = requests.get(creds["login_url"], headers=headers, timeout=10, verify=True)
        resp.raise_for_status()
        data = resp.json()

        token = (
            data.get(creds["token_field"])
            or data.get("token")
            or data.get("access_token")
            or (data.get("data") or {}).get("token")
        )
        if token:
            _persist_token_to_config(token)
            print("[WebScraper] Auto-login successful. Token refreshed.")
        return token
    except Exception as e:
        print(f"[WebScraper] Auto-login failed: {e}")
        return None


class WebScraper:
    """Web scraper with proxy support for gathering company data"""
    
    def __init__(
        self,
        proxy: Optional[str] = None,
        auth_token: Optional[str] = None,
        auth_header_name: str = "Authorization",
        cookies: Optional[Dict[str, str]] = None,
        csrf_token: Optional[str] = None,
        csrf_header_name: str = "X-CSRF-Token",
        extra_headers: Optional[Dict[str, str]] = None,
        config: Optional[Dict] = None,
    ):
        """
        Initialize the web scraper
        
        Args:
            proxy: Proxy URL in format 'http://ip:port' or 'https://ip:port'
            auth_token: Token for authenticated API requests
            auth_header_name: Header name for auth token (e.g., Authorization, x-access-token)
            cookies: Optional cookies to forward for session-based auth
            csrf_token: Optional CSRF token value
            csrf_header_name: Header name for CSRF token
            extra_headers: Optional additional headers to forward
            config: Optional scraper config dict with fixed API settings
        """
        self.proxy = proxy
        self.auth_token = auth_token
        self.config = config or {}
        self.session = requests.Session()
        
        if proxy:
            self.session.proxies = {
                'http': proxy,
                'https': proxy
            }
        
        # Set a reasonable timeout and headers
        self.timeout = 10
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Load fixed headers from config first
        config_headers = self.config.get('api_fixed_headers', {})
        if isinstance(config_headers, dict):
            self.headers.update(config_headers)
        
        # Add fixed auth from config (runtime auth_token overrides this)
        config_auth_header = self.config.get('api_fixed_auth_header')
        config_auth_token = self.config.get('api_fixed_auth_token')
        if not auth_token and config_auth_token and config_auth_header:
            self.headers[config_auth_header] = config_auth_token
        
        # Add runtime auth token if provided (overrides config)
        if auth_token:
            header_key = auth_header_name or "Authorization"
            if header_key.lower() == "authorization" and not auth_token.lower().startswith("bearer "):
                self.headers[header_key] = f"Bearer {auth_token}"
            else:
                self.headers[header_key] = auth_token

        # Add CSRF token header if provided
        if csrf_token:
            self.headers[csrf_header_name or "X-CSRF-Token"] = csrf_token

        # Add any extra headers (runtime overrides config)
        if isinstance(extra_headers, dict):
            for key, value in extra_headers.items():
                if key and value is not None:
                    self.headers[str(key)] = str(value)

        # Forward cookies - merge config and runtime (runtime adds to config)
        config_cookie_str = self.config.get('api_fixed_cookie')
        if config_cookie_str:
            # Parse cookie string like "devID=6515450; session=abc"
            for cookie_pair in config_cookie_str.split(';'):
                cookie_pair = cookie_pair.strip()
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    self.session.cookies.set(name.strip(), value.strip())
        
        if isinstance(cookies, dict):
            self.session.cookies.update(cookies)
    
    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from a URL
        
        Args:
            url: The URL to fetch
            
        Returns:
            HTML content as string, or None if failed
        """
        try:
            response = self.session.get(
                url, 
                headers=self.headers, 
                timeout=self.timeout,
                verify=True
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def parse_html(self, html: str, selector: str = None) -> List[str]:
        """
        Parse HTML content and extract text
        
        Args:
            html: HTML content as string
            selector: CSS selector to target specific elements (optional)
            
        Returns:
            List of extracted text strings
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        if selector:
            elements = soup.select(selector)
            return [elem.get_text(strip=True) for elem in elements]
        else:
            # Extract all paragraph text by default
            paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'div'])
            return [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
    
    def fetch_json_api(self, url: str, method: str = "GET", payload: Optional[Dict] = None) -> Dict:
        """
        Fetch JSON data from an API endpoint
        
        Args:
            url: The API URL to fetch
            
        Returns:
            JSON data as dictionary, or error dict if failed
        """
        try:
            request_method = method.upper() if isinstance(method, str) else "GET"
            request_kwargs = {
                "url": url,
                "headers": self.headers,
                "timeout": self.timeout,
                "verify": True
            }

            # Use config default body if no payload provided
            if payload is None and request_method in ["POST", "PUT", "PATCH"]:
                payload = self.config.get('api_default_body', {})

            if request_method in ["POST", "PUT", "PATCH"] and isinstance(payload, dict):
                request_kwargs["json"] = payload

            response = self.session.request(request_method, **request_kwargs)

            # On 401 (token expired/invalid), try to re-login automatically and retry once
            if response.status_code == 401:
                new_token = _perform_auto_login()
                if new_token:
                    auth_header = self.config.get("api_fixed_auth_header", "x-access-tokens")
                    self.headers[auth_header] = new_token
                    self.auth_token = new_token
                    request_kwargs["headers"] = self.headers
                    response = self.session.request(request_method, **request_kwargs)

            if response.status_code >= 400:
                body_preview = (response.text or "")[:500]
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "url": url,
                    "method": request_method,
                    "status_code": response.status_code,
                    "response_text": body_preview,
                }

            return response.json()
        except requests.RequestException as e:
            return {
                "error": f"API request failed: {str(e)}",
                "url": url,
                "method": method.upper() if isinstance(method, str) else "GET",
            }
        except json.JSONDecodeError as e:
            return {
                "error": f"Invalid JSON response: {str(e)}",
                "url": url,
                "method": method.upper() if isinstance(method, str) else "GET",
            }
    
    def extract_data(self, url: str, selector: str = None, is_json_api: bool = False) -> Dict:
        """
        Fetch and extract data from a URL (HTML or JSON API)
        
        Args:
            url: The URL to scrape
            selector: CSS selector for targeting specific content (HTML mode)
            is_json_api: If True, treat as JSON API endpoint instead of HTML
            
        Returns:
            Dictionary with extracted data
        """
        if is_json_api:
            data = self.fetch_json_api(url)
            if "error" in data:
                return data
            return {
                "url": url,
                "data": data,
                "content": data.get("data", []) if isinstance(data.get("data"), list) else [data],
                "total_items": len(data.get("data", [])) if isinstance(data.get("data"), list) else 1
            }
        
        html = self.fetch_page(url)
        
        if not html:
            return {"error": "Failed to fetch page", "url": url}
        
        content = self.parse_html(html, selector)
        
        return {
            "url": url,
            "content": content,
            "total_items": len(content)
        }
    
    def extract_tables(self, html: str) -> List[List[str]]:
        """
        Extract table data from HTML
        
        Args:
            html: HTML content as string
            
        Returns:
            List of tables, where each table is a list of rows
        """
        soup = BeautifulSoup(html, 'html.parser')
        tables = []
        
        for table in soup.find_all('table'):
            table_data = []
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_data = [cell.get_text(strip=True) for cell in cells]
                if row_data:
                    table_data.append(row_data)
            
            if table_data:
                tables.append(table_data)
        
        return tables
    
    def scrape_with_config(self, config_name: str = "default") -> Dict:
        """
        Scrape using predefined configuration
        
        Args:
            config_name: Name of the configuration to use
            
        Returns:
            Scraped data
        """
        config = self.load_config()
        
        if config_name not in config:
            return {"error": f"Configuration '{config_name}' not found"}
        
        site_config = config[config_name]
        url = site_config.get("url")
        selector = site_config.get("selector")
        
        return self.extract_data(url, selector)

    def scrape_inventory(self, config_name: str = "company_website") -> Dict:
        """Scrape inventory/product names from stock card (SC) or inventory pages."""
        config = self.load_config()

        if config_name not in config:
            return {"error": f"Configuration '{config_name}' not found"}

        site_config = config[config_name]
        base_url = site_config.get("url", "").strip()
        selector = site_config.get("selector")
        is_json_api = site_config.get("is_json_api", False)
        api_data_path = site_config.get("api_data_path", "data")
        api_method = site_config.get("api_method", "GET")
        api_payload = site_config.get("api_payload")

        if not base_url:
            return {"error": "Missing 'url' in scraper config"}
        
        # If JSON API mode, fetch directly
        if is_json_api:
            result = self.fetch_json_api(base_url, method=api_method, payload=api_payload)
            if "error" in result:
                result["attempted_urls"] = [base_url]
                return result
            
            # Extract products from JSON response
            products_data = result.get(api_data_path, result)
            if isinstance(products_data, list):
                products = [item.get("product_name", str(item)) if isinstance(item, dict) else str(item) for item in products_data]
            else:
                products = [str(products_data)]
            
            return {
                "products": products,
                "total_products": len(products),
                "source_url": base_url,
                "data_type": "json_api"
            }

        # HTML scraping mode (existing logic)
        default_paths = ["/sc", "/stock-card", "/stockcard", "/inventory", "/products"]
        configured_paths = site_config.get("inventory_paths", [])
        sc_path = site_config.get("sc_path")

        candidate_paths = []
        if isinstance(configured_paths, list):
            candidate_paths.extend(configured_paths)
        if sc_path:
            candidate_paths.append(sc_path)
        candidate_paths.extend(default_paths)

        # Build candidate URLs (include base page first)
        candidate_urls = [base_url]
        for path in candidate_paths:
            if isinstance(path, str) and path.strip():
                if path.startswith("http://") or path.startswith("https://"):
                    candidate_urls.append(path)
                else:
                    candidate_urls.append(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")))

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in candidate_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        attempted_urls = []
        all_products = []
        best_source_url = None

        for url in unique_urls:
            html = self.fetch_page(url)
            attempted_urls.append(url)
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # 1) Try parsing tables (most common for stock cards)
            tables = self.extract_tables(html)
            table_products = self._extract_products_from_tables(tables)
            if table_products:
                all_products.extend(table_products)
                if not best_source_url:
                    best_source_url = url

            # 2) Fallback to selector/text-based extraction
            text_items = self.parse_html(html, selector) if selector else []
            text_products = self._extract_products_from_text(text_items)
            if text_products:
                all_products.extend(text_products)
                if not best_source_url:
                    best_source_url = url

        # Deduplicate cleanly
        deduped = []
        seen_products = set()
        for product in all_products:
            key = product.lower().strip()
            if key and key not in seen_products:
                seen_products.add(key)
                deduped.append(product)

        if not deduped:
            return {
                "error": "No inventory products found from configured stock card/inventory pages",
                "attempted_urls": attempted_urls
            }

        return {
            "source_url": best_source_url or base_url,
            "products": deduped,
            "total_products": len(deduped),
            "attempted_urls": attempted_urls
        }

    def fetch_all_products_with_stock(self) -> Dict:
        """
        Fetch ALL products from product catalog.
        
        Uses `/api/lib/prod` and returns normalized product records.
        Quantity comes from catalog field `qtySC`.
        """
        config = self.load_config()
        products_config = config.get("products_list", {})
        
        if not products_config:
            return {"error": "Missing products_list config"}
        
        # Get all products first
        products_url = products_config.get("url")
        products_result = self.fetch_json_api(
            products_url,
            method=products_config.get("api_method", "POST")
        )
        
        if "error" in products_result:
            return {"error": f"Failed to fetch products list: {products_result.get('error')}"}
        
        # Extract product list
        products_list = products_result.get("items", [])
        if not products_list:
            return {"error": "No products found in catalog"}
        
        # Build consolidated inventory from catalog
        inventory_data = []
        for idx, product in enumerate(products_list[:50]):  # Support up to 50 products
            if not isinstance(product, dict):
                continue
            
            ixProd = product.get("ixProd")
            prod_name = product.get("sProd", "Unknown")
            prod_code = product.get("ProdCd", "")
            category = product.get("sProdCat", "")
            
            if not ixProd:
                continue
            
            # Quantity from product list (qtySC)
            qty = product.get("qtySC", 0)
            
            inventory_data.append({
                "product_id": ixProd,
                "product_code": prod_code,
                "product_name": prod_name,
                "category": category,
                "quantity": qty
            })
        
        return {
            "products": inventory_data,
            "total_products": len(inventory_data),
            "source_url": products_url,
            "data_type": "aggregated_stock_card"
        }

    def fetch_product_balance(self, product_id: int, warehouse_id: Optional[int] = None) -> Dict:
        """Fetch live stock-card balance for one product id."""
        config = self.load_config()
        stock_config = config.get("company_website", {})

        stock_url = stock_config.get("url")
        if not stock_url:
            return {"error": "Missing company_website.url config"}

        default_body = stock_config.get("api_default_body", {})
        payload = {
            "ixProd": int(product_id),
            "dt1": default_body.get("dt1", "2026-03-01T00:00:00+08:00"),
            "dt2": default_body.get("dt2", "2026-03-31T23:59:59+08:00"),
            "ixWH": default_body.get("ixWH", 0) if warehouse_id is None else int(warehouse_id),
            "SN": default_body.get("SN", ""),
            "SN2": default_body.get("SN2", ""),
        }

        result = self.fetch_json_api(stock_url, method=stock_config.get("api_method", "POST"), payload=payload)
        if "error" in result:
            return result

        return {
            "product_id": int(product_id),
            "balance": result.get("endQty", 0),
            "begin_qty": result.get("begQty", 0),
            "raw": result,
        }

    def fetch_general_ledger_accounts(self) -> Dict:
        """Fetch General Ledger accounts via configured /api/lib/acc endpoint."""
        config = self.load_config()
        gl_config = config.get("general_ledger_accounts", {})

        if not gl_config:
            return {"error": "Missing general_ledger_accounts config"}

        gl_url = gl_config.get("url")
        if not gl_url:
            return {"error": "Missing general_ledger_accounts.url config"}

        # Build a scoped scraper instance so section-specific headers/body are applied.
        cookie_jar = self.session.cookies.get_dict() if self.session else {}
        gl_auth_header = gl_config.get("api_fixed_auth_header", "Authorization")
        gl_scraper = WebScraper(
            proxy=self.proxy,
            auth_token=self.auth_token,
            auth_header_name=gl_auth_header,
            cookies=cookie_jar,
            config=gl_config,
        )

        result = gl_scraper.fetch_json_api(
            gl_url,
            method=gl_config.get("api_method", "POST"),
            payload=gl_config.get("api_default_body", {}),
        )
        if "error" in result:
            return result

        if isinstance(result, list):
            records = result
        elif isinstance(result, dict):
            records = (
                result.get("items")
                or result.get("data")
                or result.get("rep")
                or result.get("rows")
                or []
            )
            if not isinstance(records, list):
                records = [result]
        else:
            records = []

        return {
            "accounts": records,
            "total_accounts": len(records),
            "source_url": gl_url,
            "data_type": "general_ledger_accounts",
            "raw": result,
        }

    def _extract_products_from_tables(self, tables: List[List[str]]) -> List[str]:
        """Extract product names from HTML tables using header heuristics."""
        products = []
        product_header_keywords = ["product", "item", "description", "name", "sku", "code"]

        for table in tables:
            if len(table) < 2:
                continue

            headers = [cell.lower() for cell in table[0]]
            product_col_idx = None

            for idx, header in enumerate(headers):
                if any(keyword in header for keyword in product_header_keywords):
                    product_col_idx = idx
                    break

            # If no obvious header, try first column as fallback
            if product_col_idx is None:
                product_col_idx = 0

            for row in table[1:]:
                if product_col_idx < len(row):
                    value = row[product_col_idx].strip()
                    if self._is_valid_product_text(value):
                        products.append(value)

        return products

    def _extract_products_from_text(self, items: List[str]) -> List[str]:
        """Extract product-like lines from text blocks."""
        products = []
        for item in items:
            text = item.strip()
            if self._is_valid_product_text(text):
                products.append(text)
        return products

    def _is_valid_product_text(self, text: str) -> bool:
        """Basic quality filter for product strings."""
        if not text or len(text) < 2:
            return False

        lowered = text.lower()
        blocked = ["stock card", "inventory", "products", "search", "filter", "actions", "edit", "delete"]
        if any(word == lowered for word in blocked):
            return False

        # Avoid very long paragraph-style lines
        if len(text) > 120:
            return False

        return True
    
    @staticmethod
    def load_config() -> Dict:
        """Load scraper configuration from file"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    @staticmethod
    def save_config(config: Dict):
        """Save scraper configuration to file"""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, indent=2, fp=f)


def setup_scraper_config(name: str, url: str, selector: str = None, proxy: str = None):
    """
    Setup a new scraper configuration
    
    Args:
        name: Configuration name
        url: Target URL
        selector: CSS selector for content (optional)
        proxy: Proxy URL (optional)
    """
    config = WebScraper.load_config()
    
    config[name] = {
        "url": url,
        "selector": selector,
        "proxy": proxy
    }
    
    WebScraper.save_config(config)
    print(f"Configuration '{name}' saved successfully")


# Example usage
if __name__ == "__main__":
    # Example: Basic scraping
    scraper = WebScraper()
    data = scraper.extract_data("https://example.com")
    print(json.dumps(data, indent=2))
    
    # Example: With proxy
    # scraper = WebScraper(proxy="http://proxy-server:8080")
    # data = scraper.extract_data("https://company-website.com")
