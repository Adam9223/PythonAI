"""
Web Scraper Module with Proxy Support
Handles fetching and parsing data from company websites
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from typing import Dict, List, Optional
from urllib.parse import urljoin

# Configuration file for storing website URLs and proxy settings
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "scraper_config.json")


class WebScraper:
    """Web scraper with proxy support for gathering company data"""
    
    def __init__(self, proxy: Optional[str] = None, auth_token: Optional[str] = None):
        """
        Initialize the web scraper
        
        Args:
            proxy: Proxy URL in format 'http://ip:port' or 'https://ip:port'
            auth_token: Bearer token for authenticated API requests
        """
        self.proxy = proxy
        self.auth_token = auth_token
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
        
        # Add auth token if provided
        if auth_token:
            self.headers['Authorization'] = f'Bearer {auth_token}'
    
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
    
    def fetch_json_api(self, url: str) -> Dict:
        """
        Fetch JSON data from an API endpoint
        
        Args:
            url: The API URL to fetch
            
        Returns:
            JSON data as dictionary, or error dict if failed
        """
        try:
            response = self.session.get(
                url, 
                headers=self.headers, 
                timeout=self.timeout,
                verify=True
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"API request failed: {str(e)}", "url": url}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {str(e)}", "url": url}
    
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

        if not base_url:
            return {"error": "Missing 'url' in scraper config"}
        
        # If JSON API mode, fetch directly
        if is_json_api:
            result = self.fetch_json_api(base_url)
            if "error" in result:
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
