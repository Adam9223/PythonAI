import json
import os
import re
import sys
import time
import threading
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# Import new modules for web scraping and graph generation
try:
    from .web_scraper import WebScraper, _perform_auto_login as _scraper_auto_login
    from .graph_generator import GraphGenerator
    SCRAPER_AVAILABLE = True
    GRAPH_AVAILABLE = True
except ImportError:
    # Fallback for direct script execution
    try:
        from web_scraper import WebScraper, _perform_auto_login as _scraper_auto_login
        from graph_generator import GraphGenerator
        SCRAPER_AVAILABLE = True
        GRAPH_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: Some features unavailable - {e}")
        SCRAPER_AVAILABLE = False
        GRAPH_AVAILABLE = False
        _scraper_auto_login = None

# Attempt a proactive token refresh on startup so we don't hit 401 on the first request
if SCRAPER_AVAILABLE and _scraper_auto_login is not None:
    try:
        _scraper_auto_login()
    except Exception:
        pass

# Ollama local LLM integration
# Default to ultra-lightweight qwen2.5:0.5b (397MB, 10-15x faster than llama3)
# Set env vars OLLAMA_MODEL or LLAMA_MODEL to override:
#   OLLAMA_MODEL=mistral:latest  (4.1GB, balanced)
#   OLLAMA_MODEL=llama3:latest   (4.7GB, slower but higher quality)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("LLAMA_MODEL", "qwen2.5:0.5b"))
OLLAMA_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("OLLAMA_FALLBACK_MODELS", f"{OLLAMA_MODEL},llama3:latest").split(",") if m.strip()
]
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "1024"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "100"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "2m")
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "none")
OLLAMA_LIVE_CONTEXT_MAX_CHARS = int(os.getenv("OLLAMA_LIVE_CONTEXT_MAX_CHARS", "1200"))
OLLAMA_AVAILABLE = False
_ollama_lib = None
try:
    import ollama as _ollama_lib
    OLLAMA_AVAILABLE = True
    print("Ollama AI engine loaded successfully")
except ImportError:
    print("Ollama not installed — using rule-based fallback. Run: pip install ollama")

FILE_NAME = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge.json")
ARTICLES_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "articles_db.json")

# Global cache for articles database
articles_cache = None
last_chart_context = None
balance_context = None  # Track the last balance query for chart generation
live_site_cache = None
live_site_cache_timestamp = 0
LIVE_SITE_CACHE_SECONDS = 90

# Conversation context storage
conversation_history = []  # List of dicts with user input and AI response
extracted_context = {  # Store extracted facts and entities
    'mentioned_data_sources': [],  # e.g., 'general_ledger', 'stock_card'
    'data_values': {},  # e.g., {'balance': '336.1M'}
    'user_preferences': {},  # e.g., {'chart_type': 'line'}
    'facts': []  # e.g., 'User is interested in GL data'
}
MAX_HISTORY = 20  # Keep most recent 20 exchanges
CONVERSATION_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "conversation_store.json")

print("AI Assistant - Retrieval-Augmented Generation System")


# Persistent conversation storage
def load_conversation_store():
    """Load conversation history from persistent JSON file."""
    global conversation_history, extracted_context
    
    try:
        if os.path.exists(CONVERSATION_STORE):
            with open(CONVERSATION_STORE, 'r') as f:
                store = json.load(f)
                conversation_history = store.get('history', [])
                extracted_context = store.get('context', extracted_context)
    except Exception as e:
        print(f"Error loading conversation store: {e}")


def save_conversation_store():
    """Save conversation history to persistent JSON file."""
    global conversation_history, extracted_context
    
    try:
        store = {
            'history': conversation_history[-MAX_HISTORY:],
            'context': extracted_context
        }
        with open(CONVERSATION_STORE, 'w') as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Error saving conversation store: {e}")


# Context Management Functions
def store_conversation(user_input, ai_response):
    """
    Store user input and AI response in conversation history.
    """
    global conversation_history, MAX_HISTORY
    
    # Load before appending to get latest
    load_conversation_store()
    
    conversation_history.append({
        'user': user_input,
        'ai': ai_response,
        'timestamp': time.time()
    })
    
    # Keep only recent history
    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]
    
    # Save immediately
    save_conversation_store()


def extract_context_from_input(user_input):
    """
    Extract important facts and entities from user input.
    """
    global extracted_context
    normalized = user_input.lower()
    
    # Detect data source mentions
    if any(term in normalized for term in ['general ledger', 'gl', 'ledger']):
        if 'general_ledger' not in extracted_context['mentioned_data_sources']:
            extracted_context['mentioned_data_sources'].append('general_ledger')
    
    if any(term in normalized for term in ['stock card', 'stock', 'inventory']):
        if 'stock_card' not in extracted_context['mentioned_data_sources']:
            extracted_context['mentioned_data_sources'].append('stock_card')
    
    # Detect chart type preferences
    if 'line' in normalized:
        extracted_context['user_preferences']['chart_type'] = 'line'
    elif 'bar' in normalized:
        extracted_context['user_preferences']['chart_type'] = 'bar'
    elif 'pie' in normalized:
        extracted_context['user_preferences']['chart_type'] = 'pie'
    
    # Extract numbers (could be balances, periods, etc.)
    numbers = re.findall(r'\d+(?:\.\d+)?', user_input)
    if numbers:
        extracted_context['data_values']['mentioned_numbers'] = numbers


def get_relevant_history(query, max_results=3):
    """
    Search conversation history for relevant past exchanges.
    """
    if not conversation_history:
        return []
    
    query_tokens = set(tokenize(query.lower()))
    relevant = []
    
    for exchange in conversation_history:
        user_sim = token_similarity(query.lower(), exchange['user'].lower())
        # Handle AI response that might be a dict (chart data) or string
        ai_response = exchange['ai']
        if isinstance(ai_response, dict):
            ai_response_str = str(ai_response)
        else:
            ai_response_str = ai_response
        ai_sim = token_similarity(query.lower(), ai_response_str.lower())
        max_sim = max(user_sim, ai_sim)
        
        if max_sim > 0.3:  # Relevance threshold
            relevant.append({
                'user': exchange['user'],
                'ai': exchange['ai'],
                'relevance': max_sim
            })
    
    # Sort by relevance and return top results
    relevant.sort(key=lambda x: x['relevance'], reverse=True)
    return relevant[:max_results]


def build_context_reminder():
    """
    Generate a reminder of relevant past context for the AI to consider.
    """
    reminders = []
    
    if extracted_context['mentioned_data_sources']:
        reminders.append(f"User is interested in: {', '.join(extracted_context['mentioned_data_sources'])}")
    
    if extracted_context['user_preferences']:
        reminders.append(f"User preferences: {json.dumps(extracted_context['user_preferences'])}")
    
    return " ".join(reminders) if reminders else ""



print("Using tokenized Wikipedia corpus for context-aware responses\n")


class LoadingAnimation:
    """Display a loading animation while AI is thinking"""
    def __init__(self):
        self.is_loading = False
        self.thread = None
    
    def _animate(self):
        """Show animated dots"""
        dots = ["   ", ".  ", ".. ", "..."]
        idx = 0
        while self.is_loading:
            sys.stdout.write(f"\rAI is thinking{dots[idx % len(dots)]}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.3)
        sys.stdout.write("\r" + " " * 30 + "\r")  # Clear the line
        sys.stdout.flush()
    
    def start(self):
        """Start the loading animation"""
        self.is_loading = True
        self.thread = threading.Thread(target=self._animate)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Stop the loading animation"""
        self.is_loading = False
        if self.thread:
            self.thread.join()


def normalize_text(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", text.lower())).strip()


def tokenize(text):
    """Split text into tokens and remove common stop words"""
    stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 
                  'would', 'should', 'can', 'could', 'may', 'might', 'must',
                  'i', 'you', 'he', 'she', 'it', 'we', 'they', 'my', 'your',
                  'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'from'}
    
    normalized = normalize_text(text)
    tokens = [word for word in normalized.split() if word not in stop_words]
    return tokens


def parse_chart_date_range(user_input, default_dt1=None, default_dt2=None):
    """Parse date range phrases for chart queries.

    Supports examples:
    - from Jan to Mar 2026
    - from January 2026 to March 2026
    - from 2026-01-01 to 2026-03-31
    - last 30 days / last 12 weeks / last 6 months
    """
    text = user_input.lower()
    now = datetime.now()

    def fmt_start(dt):
        return dt.strftime("%Y-%m-%dT00:00:00+08:00")

    def fmt_end(dt):
        return dt.strftime("%Y-%m-%dT23:59:59+08:00")

    # 0) Common calendar phrases
    if "this month" in text:
        start = datetime(now.year, now.month, 1)
        return fmt_start(start), fmt_end(now)

    if "last month" in text:
        if now.month == 1:
            y, m = now.year - 1, 12
        else:
            y, m = now.year, now.month - 1
        start = datetime(y, m, 1)
        if m == 12:
            next_month = datetime(y + 1, 1, 1)
        else:
            next_month = datetime(y, m + 1, 1)
        end = next_month - timedelta(days=1)
        return fmt_start(start), fmt_end(end)

    if "this year" in text:
        start = datetime(now.year, 1, 1)
        return fmt_start(start), fmt_end(now)

    if "last year" in text:
        start = datetime(now.year - 1, 1, 1)
        end = datetime(now.year - 1, 12, 31)
        return fmt_start(start), fmt_end(end)

    # Quarter pattern: Q1 2026 or quarter 1 2026
    q_match = re.search(r"(?:q|quarter\s*)([1-4])\s*(\d{4})", text)
    if q_match:
        quarter = int(q_match.group(1))
        year = int(q_match.group(2))
        start_month = 1 + (quarter - 1) * 3
        end_month = start_month + 2
        start = datetime(year, start_month, 1)
        if end_month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, end_month + 1, 1)
        end = next_month - timedelta(days=1)
        return fmt_start(start), fmt_end(end)

    # 1) Relative ranges: last N days|weeks|months
    rel = re.search(r"last\s+(\d{1,3})\s+(day|days|week|weeks|month|months)", text)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        if "day" in unit:
            start = now - timedelta(days=amount)
        elif "week" in unit:
            start = now - timedelta(weeks=amount)
        else:
            start = now - timedelta(days=amount * 30)
        return fmt_start(start), fmt_end(now)

    # 2) Explicit ISO date range: from YYYY-MM-DD to YYYY-MM-DD
    iso = re.search(r"(?:from|between)\s+(\d{4}-\d{2}-\d{2})\s+(?:to|and)\s+(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            start = datetime.strptime(iso.group(1), "%Y-%m-%d")
            end = datetime.strptime(iso.group(2), "%Y-%m-%d")
            return fmt_start(start), fmt_end(end)
        except ValueError:
            pass

    # 3) Month-name range: from Jan to Mar 2026 / from January 2026 to March 2026
    months = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    mo = re.search(
        r"(?:from|between)\s+([a-z]{3,9})(?:\s+(\d{4}))?\s+(?:to|and)\s+([a-z]{3,9})(?:\s+(\d{4}))?",
        text
    )
    if mo:
        m1_name, y1, m2_name, y2 = mo.group(1), mo.group(2), mo.group(3), mo.group(4)
        if m1_name in months and m2_name in months:
            month1 = months[m1_name]
            month2 = months[m2_name]
            year2 = int(y2) if y2 else int(y1) if y1 else now.year
            year1 = int(y1) if y1 else year2

            start = datetime(year1, month1, 1)
            # End = last day of end month
            if month2 == 12:
                next_month = datetime(year2 + 1, 1, 1)
            else:
                next_month = datetime(year2, month2 + 1, 1)
            end = next_month - timedelta(days=1)
            return fmt_start(start), fmt_end(end)

    # Fallback to defaults
    return default_dt1, default_dt2


def token_similarity(text1, text2):
    """Calculate similarity based on token overlap"""
    tokens1 = set(tokenize(text1))
    tokens2 = set(tokenize(text2))
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    
    return len(intersection) / len(union) if union else 0.0


def combined_similarity(text1, text2):
    """Combine string similarity and token similarity"""
    string_sim = SequenceMatcher(None, normalize_text(text1), normalize_text(text2)).ratio()
    token_sim = token_similarity(text1, text2)
    
    # Weight: 60% token similarity, 40% string similarity
    return 0.6 * token_sim + 0.4 * string_sim


def load_articles_db():
    """Load the Wikipedia articles database"""
    global articles_cache
    
    if articles_cache is not None:
        return articles_cache
    
    if not os.path.exists(ARTICLES_DB):
        return {"articles": []}
    
    print("[Loading articles database...]")
    with open(ARTICLES_DB, "r") as f:
        articles_cache = json.load(f)
    print(f"[Loaded {len(articles_cache.get('articles', []))} articles]\n")
    return articles_cache


def search_articles(query, max_results=3):
    """Search through articles database for relevant context"""
    db = load_articles_db()
    articles = db.get("articles", [])
    
    if not articles:
        return []
    
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return []
    
    # Score each article based on relevance
    scored_articles = []
    
    for article in articles:
        title = article.get("title", "")
        content = article.get("content", "")[:1000]  # First 1000 chars for scoring
        
        # Calculate title match
        title_sim = combined_similarity(query, title)
        
        # Calculate content token overlap
        content_tokens = set(tokenize(content))
        token_overlap = len(query_tokens.intersection(content_tokens))
        token_score = token_overlap / len(query_tokens) if query_tokens else 0
        
        # Combined score: 70% title, 30% content
        score = 0.7 * title_sim + 0.3 * token_score
        
        if score > 0.35:  # Higher threshold to avoid weak matches
            scored_articles.append((article, score))
    
    # Sort by score and return top results
    scored_articles.sort(key=lambda x: x[1], reverse=True)
    # Only return articles with strong relevance
    return [article for article, score in scored_articles[:max_results]]


def load_knowledge():
    if not os.path.exists(FILE_NAME):
        with open(FILE_NAME, "w") as f:
            json.dump({"knowledge": []}, f)

    with open(FILE_NAME, "r") as f:
        return json.load(f)


def save_knowledge(data):
    with open(FILE_NAME, "w") as f:
        json.dump(data, f, indent=4)


def add_knowledge(pattern, response):
    if not response.strip():
        return 

    data = load_knowledge()

    data["knowledge"].append({
        "pattern": pattern,
        "response": response
    })

    save_knowledge(data)
    print("Knowledge saved!")


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def check_knowledge(user_input):
    data = load_knowledge()
    normalized_input = normalize_text(user_input)

    if not normalized_input:
        return None, []

    # Check for exact match first
    for item in data["knowledge"]:
        if normalize_text(item["pattern"]) == normalized_input:
            return item["response"], []

    # Calculate similarity using tokenization and string matching
    best_matches = []

    for item in data["knowledge"]:
        # Use combined similarity (token + string)
        score = combined_similarity(user_input, item["pattern"])
        best_matches.append((item, score))

    # If no matches at all, return empty
    if not best_matches:
        return None, []

    # Sort by score and get top 3 matches
    best_matches.sort(key=lambda x: x[1], reverse=True)
    top_matches = best_matches[:3]

    # If top match is very strong, return it directly
    if top_matches and top_matches[0][1] > 0.75:  # Lowered threshold due to tokenization improving accuracy
        return top_matches[0][0]["response"], []

    # Only return context matches if they're reasonably similar (high threshold to avoid weak matches)
    context_matches = [item for item, score in top_matches if score > 0.6]
    return None, context_matches


def handle_greeting_request(user_input):
    normalized_input = normalize_text(user_input)
    if not normalized_input:
        return None

    greeting_patterns = [
        r"^(hi|hello|hey)\b",
        r"^good\s+(morning|afternoon|evening)\b",
        r"^how\s+are\s+you\b"
    ]

    if any(re.search(pattern, normalized_input) for pattern in greeting_patterns):
        return "Hello! I can help with balances, inventory, charts, and financial questions. What would you like to check?"

    return None

def try_math(user_input):
    match = re.search(r'(\d+\s*[\+\-\*\/]\s*\d+)', user_input)
    if match:
        expression = match.group()
        try:
            result = eval(expression)
            return f"{expression} = {result}"
        except:
            return None
    return None

def format_natural_response(context_parts, query):
    """Format retrieved context into a natural, ChatGPT-like response"""
    # Clean up all context parts
    cleaned_parts = []
    for part in context_parts:
        # Remove tokenization artifacts
        clean = re.sub(r'@\.@', '.', part)
        clean = re.sub(r'@-@', '-', clean)
        clean = re.sub(r'<unk>', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        cleaned_parts.append(clean)
    
    # Take only the first context part (most relevant)
    if not cleaned_parts:
        return "I found some information but couldn't format it properly."
    
    main_context = cleaned_parts[0]
    
    # Extract sentences - be more lenient with requirements
    sentences = []
    for s in main_context.split('.'):
        s = s.strip()
        # Accept any sentence that's at least 15 characters
        if len(s) > 15 and s:
            sentences.append(s + '.')
    
    if not sentences:
        # Fallback: just return the context as-is, truncated
        return main_context[:400] if len(main_context) > 400 else main_context
    
    # Use up to 2-3 complete sentences for a concise response
    content = ' '.join(sentences[:3])
    
    # If too long, truncate to reasonable length
    if len(content) > 500:
        content = content[:497] + "..."
    
    return content


def extract_relevant_text(content, query_tokens, max_length=500):
    """Extract the most relevant section from article content"""
    # Split content into sentences
    sentences = re.split(r'[.!?]\s+', content)
    
    # Score each sentence by token overlap
    scored_sentences = []
    for sentence in sentences:
        if len(sentence) < 20:  # Skip very short sentences
            continue
        sentence_tokens = set(tokenize(sentence))
        overlap = len(query_tokens.intersection(sentence_tokens))
        if overlap > 0:
            scored_sentences.append((sentence, overlap))
    
    # Sort by relevance and take top sentences
    scored_sentences.sort(key=lambda x: x[1], reverse=True)
    
    # Build response from top sentences
    result = []
    current_length = 0
    for sentence, score in scored_sentences[:5]:  # Top 5 sentences
        if current_length + len(sentence) > max_length:
            break
        result.append(sentence)
        current_length += len(sentence)
    
    return '. '.join(result) + '.' if result else content[:max_length]


def parse_cookie_header(cookie_header):
    """Parse a Cookie header string into a dict for requests session cookies."""
    if not cookie_header or not isinstance(cookie_header, str):
        return {}

    cookies = {}
    parts = cookie_header.split(";")
    for part in parts:
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def get_company_scraper(auth_context=None):
    """Create scraper with optional auth context from frontend."""
    # Load scraper config
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")
    config = {}
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                config = full_config.get('company_website', {})
    except Exception:
        pass
    
    if isinstance(auth_context, str):
        return WebScraper(proxy=None, auth_token=auth_context, config=config)

    if not isinstance(auth_context, dict):
        return WebScraper(proxy=None, config=config)

    auth_token = auth_context.get("user_auth_token")
    auth_header_name = auth_context.get("auth_header_name") or "Authorization"
    csrf_token = auth_context.get("csrf_token")
    csrf_header_name = auth_context.get("csrf_header_name") or "X-CSRF-Token"
    extra_headers = auth_context.get("extra_headers") if isinstance(auth_context.get("extra_headers"), dict) else None

    raw_cookie = auth_context.get("user_cookie")
    cookies = raw_cookie if isinstance(raw_cookie, dict) else parse_cookie_header(raw_cookie)

    return WebScraper(
        proxy=None,
        auth_token=auth_token,
        auth_header_name=auth_header_name,
        cookies=cookies,
        csrf_token=csrf_token,
        csrf_header_name=csrf_header_name,
        extra_headers=extra_headers,
        config=config,
    )


def normalize_site_context(site_context):
    """Normalize optional frontend-provided site context payload."""
    if not isinstance(site_context, dict):
        return None

    content = site_context.get("content")
    products = site_context.get("products")
    source_url = site_context.get("url") or site_context.get("source_url") or "frontend-provided source"

    normalized_content = []
    if isinstance(content, list):
        normalized_content = [str(item).strip() for item in content if str(item).strip()]

    normalized_products = []
    if isinstance(products, list):
        normalized_products = [str(item).strip() for item in products if str(item).strip()]

    if not normalized_content and not normalized_products:
        return None

    return {
        "url": source_url,
        "content": normalized_content,
        "products": normalized_products
    }


def should_try_live_site_lookup(user_input):
    """Decide whether a question should automatically query the proxied company website."""
    normalized_input = normalize_text(user_input)

    # Avoid scraping for simple greetings/chitchat
    small_talk_patterns = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "how are you", "thanks", "thank you", "bye"
    ]
    if any(pattern in normalized_input for pattern in small_talk_patterns):
        return False

    # Avoid scraping for explicit graph questions (handled elsewhere)
    if any(word in normalized_input for word in ["graph", "chart", "plot", "visualize"]):
        return False

    tokens = tokenize(user_input)
    if len(tokens) < 2:
        return False

    factual_markers = [
        "what", "which", "who", "where", "when", "how", "list", "show",
        "current", "latest", "available", "inventory", "stock", "product",
        "price", "status", "total", "count"
    ]
    return any(marker in normalized_input for marker in factual_markers)


def get_live_company_data(force_refresh=False):
    """Fetch and cache company website data from proxied source."""
    global live_site_cache, live_site_cache_timestamp

    now = time.time()
    cache_valid = (now - live_site_cache_timestamp) < LIVE_SITE_CACHE_SECONDS
    if not force_refresh and live_site_cache is not None and cache_valid:
        return live_site_cache

    scraper = get_company_scraper()
    data = scraper.scrape_with_config("company_website")

    if "error" not in data:
        live_site_cache = data
        live_site_cache_timestamp = now
        try:
            with open('scraped_data_temp.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    return data


def get_live_gl_data(force_refresh=False):
    """
    Fetch live General Ledger data from website data.
    Attempts to extract GL data from scraped website content.
    Falls back to sample data if website data unavailable.
    """
    global live_site_cache, live_site_cache_timestamp
    
    try:
        # Primary source: configured GL accounts API (/api/lib/acc).
        if SCRAPER_AVAILABLE:
            scraper = get_company_scraper()
            gl_accounts = scraper.fetch_general_ledger_accounts()
            if "error" not in gl_accounts:
                return {
                    'source': 'live_gl_accounts_api',
                    'data': gl_accounts,
                    'timestamp': datetime.now().isoformat()
                }

        # Secondary source: generic company website scraping cache.
        live_data = get_live_company_data(force_refresh)
        if live_data and "error" not in live_data:
            if "financial" in live_data or "ledger" in live_data or "balance" in live_data:
                return {
                    'source': 'live_website',
                    'data': live_data,
                    'timestamp': datetime.now().isoformat()
                }

    except Exception as e:
        print(f"Error fetching live GL data: {e}")
    
    # Fallback to sample data
    if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                sample_data = json.load(f)
                return {
                    'source': 'sample_data',
                    'data': sample_data,
                    'timestamp': datetime.now().isoformat()
                }
        except Exception as e:
            print(f"Error loading sample GL data: {e}")
    
    return None


def answer_from_live_site(user_input, site_context=None):
    """Answer factual queries directly from the proxied company website when relevant."""
    if not SCRAPER_AVAILABLE:
        return None

    if not should_try_live_site_lookup(user_input):
        return None

    normalized_input = normalize_text(user_input)

    normalized_site_context = normalize_site_context(site_context)

    # Inventory-like questions should use stock card extraction
    inventory_markers = ["inventory", "stock card", "products", "items", "on hand", "sc"]
    if any(marker in normalized_input for marker in inventory_markers):
        if normalized_site_context and normalized_site_context.get("products"):
            products = normalized_site_context.get("products", [])
            total = len(products)
            source_url = normalized_site_context.get("url", "frontend-provided source")
            preview = products[:20]
            lines = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(preview)])
            more_note = f"\n...and {total - len(preview)} more products." if total > len(preview) else ""
            return (
                f"Current inventory products from {source_url} (total: {total}):\n\n"
                f"{lines}{more_note}"
            )

        scraper = get_company_scraper()
        inventory_result = scraper.scrape_inventory("company_website")
        if "error" not in inventory_result:
            products = inventory_result.get("products", [])
            total = inventory_result.get("total_products", len(products))
            source_url = inventory_result.get("source_url", "configured source")
            preview = products[:20]
            lines = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(preview)])
            more_note = f"\n...and {total - len(preview)} more products." if total > len(preview) else ""
            return (
                f"Current inventory products from {source_url} (total: {total}):\n\n"
                f"{lines}{more_note}"
            )

    # General factual lookup from frontend-provided context first
    if normalized_site_context and normalized_site_context.get("content"):
        data = {
            "url": normalized_site_context.get("url", "frontend-provided source"),
            "content": normalized_site_context.get("content", []),
            "total_items": len(normalized_site_context.get("content", []))
        }
    else:
        data = get_live_company_data(force_refresh=False)

    if "error" in data:
        return None

    content_items = data.get("content", [])
    if not content_items:
        return None

    query_tokens = set(tokenize(user_input))
    scored = []
    for item in content_items:
        if not item or len(item) < 5:
            continue
        item_tokens = set(tokenize(item))
        overlap = len(query_tokens.intersection(item_tokens))
        if overlap > 0:
            scored.append((item, overlap))

    if not scored:
        return None

    scored.sort(key=lambda x: x[1], reverse=True)
    top_items = [text for text, _ in scored[:3]]
    source_url = data.get("url", "configured company website")

    bullet_lines = "\n".join([f"- {item[:220]}" for item in top_items])
    return f"From your proxied company website ({source_url}):\n{bullet_lines}"


def handle_scrape_request(user_input):
    """Handle web scraping requests"""
    # Check if user is asking to scrape a website
    scrape_keywords = ['scrape', 'fetch', 'get data from', 'extract from', 'pull data from']
    if not any(keyword in user_input.lower() for keyword in scrape_keywords):
        return None

    if not SCRAPER_AVAILABLE:
        return "Web scraping is not available. Please install required packages: pip install requests beautifulsoup4"
    
    # Check for URL in the input
    url_match = re.search(r'https?://[^\s]+', user_input)
    
    if url_match:
        url = url_match.group(0)
        scraper = get_company_scraper()
        data = scraper.extract_data(url)
        
        if "error" in data:
            return f"Failed to scrape {url}: {data['error']}"
        
        # Return summary of scraped data
        preview = data['content'][:5] if len(data['content']) >= 5 else data['content']
        response = f"Successfully scraped {data['total_items']} items from {url}.\n\n"
        response += "Preview of content:\n"
        for i, item in enumerate(preview, 1):
            response += f"{i}. {item[:100]}...\n" if len(item) > 100 else f"{i}. {item}\n"
        
        # Save scraped data for potential graph generation
        with open('scraped_data_temp.json', 'w') as f:
            json.dump(data, f, indent=2)
        
        return response
    
    # Use predefined config
    elif 'company' in user_input.lower() or 'website' in user_input.lower():
        scraper = get_company_scraper()
        data = scraper.scrape_with_config('company_website')
        
        if "error" in data:
            return f"Please configure the company website in config/scraper_config.json first."
        
        return f"Scraped company website: {data['total_items']} items found"
    
    return None


def load_company_data():
    """Load data from company_data.json file (alternative to web scraping)"""
    company_data_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'company_data.json')
    if os.path.exists(company_data_file):
        try:
            with open(company_data_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading company_data.json: {e}")
    return None


def handle_branches_request(user_input):
    """
    Handle branch/warehouse/location inquiry requests.
    Returns a signal for the API to fetch branches data.
    """
    normalized_input = normalize_text(user_input)
    
    branch_triggers = [
        "branch",
        "branches",
        "warehouse",
        "warehouses",
        "location",
        "locations",
        "site",
        "sites",
        "facility",
        "facilities"
    ]
    
    query_intent = [
        "what",
        "which",
        "list",
        "show",
        "available",
        "do we have",
        "we have"
    ]
    
    has_trigger = any(trigger in normalized_input for trigger in branch_triggers)
    has_intent = any(intent in normalized_input for intent in query_intent)
    
    if has_trigger and has_intent:
        # Return a signal for the FastAPI endpoint to fetch branches
        return {
            "type": "branches_request",
            "message": "Fetching available branches..."
        }
    
    return None


def handle_inventory_request(user_input, site_context=None, auth_token=None, auth_context=None):
    """Handle inventory/product lookup requests from stock card (SC) or inventory pages."""
    normalized_input = normalize_text(user_input)

    # Let chart handler process chart/graph requests first
    if any(word in normalized_input for word in ["chart", "graph", "historical", "trend", "visual"]):
        return None
    inventory_triggers = [
        "inventory",
        "stock card",
        "current products",
        "products in inventory",
        "items in inventory",
        "on hand",
        "sc"
    ]

    # Require at least one trigger and at least one intent/action word
    intent_words = ["what", "list", "show", "get", "current", "available", "find", "give"]
    has_trigger = any(trigger in normalized_input for trigger in inventory_triggers)
    has_intent = any(word in normalized_input for word in intent_words)

    # Product-specific queries (even without explicit inventory trigger)
    product_lookup_markers = ["product", "units", "balance", "stock", "click", "beat", "item"]
    has_product_lookup = any(marker in normalized_input for marker in product_lookup_markers)

    # Distinguish between broad list requests vs specific product lookup requests.
    is_collection_request = (
        ("products in inventory" in normalized_input)
        or ("items in inventory" in normalized_input)
        or ("what are the products" in normalized_input)
        or bool(re.search(r"what\s+products?\s+(are\s+)?in\s+(the\s+)?inventory", normalized_input))
        or ("list products" in normalized_input)
        or ("show products" in normalized_input)
        or ("show all products" in normalized_input)
        or ("current products" in normalized_input)
    )

    specific_product_markers = [
        "balance",
        "find",
        "code",
        "sku",
        "exact",
        "named",
        "for",
    ]
    has_specific_product_marker = any(marker in normalized_input for marker in specific_product_markers)

    # If user asks for a specific item lookup/balance, enable match-scoring path.
    should_handle_product_query = has_product_lookup and has_specific_product_marker and not is_collection_request

    if not ((has_trigger and has_intent) or should_handle_product_query):
        return None
    
    # Try web scraping first (primary data source)
    if not SCRAPER_AVAILABLE:
        # Fallback to company_data.json only if web scraping not available
        company_data = load_company_data()
        if company_data and 'inventory' in company_data:
            inventory_items = company_data['inventory']
            total = len(inventory_items)
            company_name = company_data.get('company_name', 'Company Data')
            last_updated = company_data.get('last_updated', 'N/A')
            
            # Format inventory items
            lines = []
            for idx, item in enumerate(inventory_items[:20], 1):
                product = item.get('product_name', 'Unknown')
                qty = item.get('quantity', 0)
                unit = item.get('unit', 'units')
                location = item.get('location', 'N/A')
                status = item.get('status', '')
                lines.append(f"{idx}. {product}: {qty} {unit} @ {location} [{status}]")
            
            more_note = f"\n...and {total - 20} more items." if total > 20 else ""
            
            return (
                f"Current inventory from {company_name} (Last updated: {last_updated}):\n"
                f"Total products: {total}\n\n"
                + "\n".join(lines) + more_note +
                "\n\n💡 Using fallback data from company_data.json. Install web scraping packages to fetch live data."
            )
        return "Inventory lookup is not available. Please install: pip install requests beautifulsoup4"

    normalized_site_context = normalize_site_context(site_context)
    if normalized_site_context and normalized_site_context.get("products"):
        products = normalized_site_context.get("products", [])
        total = len(products)
        source_url = normalized_site_context.get("url", "frontend-provided source")
        preview = products[:20]
        lines = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(preview)])
        more_note = ""
        if total > len(preview):
            more_note = f"\n...and {total - len(preview)} more products."
        return (
            f"Current inventory products from {source_url} (total: {total}):\n\n"
            f"{lines}{more_note}"
        )

    resolved_auth_context = auth_context if isinstance(auth_context, dict) else auth_token
    scraper = get_company_scraper(auth_context=resolved_auth_context)

    # 1) Preferred path: aggregate all products from /api/lib/prod
    result_multi = scraper.fetch_all_products_with_stock()
    if "error" not in result_multi:
        products = result_multi.get("products", [])
        total = len(products)
        source_url = result_multi.get("source_url", "clone.ulap.biz")

        # Inventory management analytics intents
        ask_low_stock = any(term in normalized_input for term in ["low stock", "critical stock", "reorder"])
        ask_out_of_stock = any(term in normalized_input for term in ["out of stock", "no stock", "zero stock"])
        ask_top_stock = (
            any(term in normalized_input for term in ["top stock", "highest stock", "most stock", "top products"])
            or bool(re.search(r"\btop\s+\d+\s+products?\b", normalized_input))
            or bool(re.search(r"\btop\s+products?\b", normalized_input))
        )
        ask_summary = any(term in normalized_input for term in ["summary", "overview", "kpi", "status"])

        if products and (ask_low_stock or ask_out_of_stock or ask_top_stock or ask_summary):
            normalized_products = []
            for item in products:
                qty = item.get("quantity", 0)
                try:
                    qty = float(qty)
                except (TypeError, ValueError):
                    qty = 0.0
                normalized_products.append({**item, "quantity": qty})

            in_stock = [p for p in normalized_products if p["quantity"] > 0]
            out_stock = [p for p in normalized_products if p["quantity"] <= 0]
            low_stock = [p for p in normalized_products if 0 < p["quantity"] <= 2]

            if ask_out_of_stock:
                preview = out_stock[:15]
                lines = [
                    f"{idx + 1}. {p.get('product_name', 'Unknown')} ({p.get('product_code', '')})"
                    for idx, p in enumerate(preview)
                ]
                more = f"\n...and {len(out_stock) - len(preview)} more." if len(out_stock) > len(preview) else ""
                return (
                    f"Out-of-stock products (total: {len(out_stock)}):\n\n"
                    + ("\n".join(lines) if lines else "No out-of-stock products found.")
                    + more
                )

            if ask_low_stock:
                preview = low_stock[:15]
                lines = [
                    f"{idx + 1}. {p.get('product_name', 'Unknown')} ({p.get('product_code', '')}) - {p.get('quantity', 0)} units"
                    for idx, p in enumerate(preview)
                ]
                more = f"\n...and {len(low_stock) - len(preview)} more." if len(low_stock) > len(preview) else ""
                return (
                    f"Low-stock products (1-2 units, total: {len(low_stock)}):\n\n"
                    + ("\n".join(lines) if lines else "No low-stock products found.")
                    + more
                )

            if ask_top_stock:
                top_match = re.search(r"top\s+(\d{1,2})", normalized_input)
                top_n = int(top_match.group(1)) if top_match else 10
                ranked = sorted(normalized_products, key=lambda x: x.get("quantity", 0), reverse=True)
                preview = ranked[:max(1, min(top_n, 20))]
                lines = [
                    f"{idx + 1}. {p.get('product_name', 'Unknown')} ({p.get('product_code', '')}) - {p.get('quantity', 0)} units"
                    for idx, p in enumerate(preview)
                ]
                return f"Top {len(preview)} products by stock:\n\n" + "\n".join(lines)

            # summary
            avg_stock = round(sum(p["quantity"] for p in normalized_products) / len(normalized_products), 2) if normalized_products else 0
            return (
                "Inventory summary:\n"
                f"- Total products: {len(normalized_products)}\n"
                f"- In stock: {len(in_stock)}\n"
                f"- Out of stock: {len(out_stock)}\n"
                f"- Low stock (1-2 units): {len(low_stock)}\n"
                f"- Average units/product: {avg_stock}"
            )

        # If user asked for a specific product/balance, filter and answer directly
        if should_handle_product_query and products:
            query_tokens = set(tokenize(normalized_input))
            stop_tokens = {
                "give", "me", "the", "for", "a", "an", "with", "find", "show", "get",
                "balance", "product", "products", "item", "items", "stock", "units", "unit", "of"
            }
            target_tokens = [t for t in query_tokens if t not in stop_tokens and len(t) > 1]

            def product_score(item):
                name = normalize_text(str(item.get("product_name", "")))
                code = normalize_text(str(item.get("product_code", "")))
                category = normalize_text(str(item.get("category", "")))
                text = f"{name} {code} {category}"
                return sum(1 for t in target_tokens if t in text)

            # Special case: user asked for "with units"
            if "units" in normalized_input and ("find" in normalized_input or "product" in normalized_input):
                unit_matches = [p for p in products if normalize_text(str(p.get("category", ""))) == "units"]
                preview = unit_matches[:10]
                if preview:
                    lines = []
                    for idx, item in enumerate(preview, 1):
                        lines.append(
                            f"{idx}. {item.get('product_name', 'Unknown')} ({item.get('product_code', '')}): "
                            f"{item.get('quantity', 0)} units"
                        )
                    more_note = f"\n...and {len(unit_matches) - len(preview)} more in Units." if len(unit_matches) > len(preview) else ""
                    return (
                        f"Products in category 'Units' from {source_url} (total: {len(unit_matches)}):\n\n"
                        + "\n".join(lines)
                        + more_note
                    )

            ranked = sorted(products, key=product_score, reverse=True)
            best_matches = [p for p in ranked if product_score(p) > 0][:5]

            if best_matches:
                lines = []
                for idx, item in enumerate(best_matches, 1):
                    live_balance = item.get('quantity', 0)
                    product_id = item.get('product_id')
                    if product_id:
                        balance_result = scraper.fetch_product_balance(product_id)
                        if "error" not in balance_result:
                            live_balance = balance_result.get("balance", live_balance)

                    lines.append(
                        f"{idx}. {item.get('product_name', 'Unknown')} ({item.get('product_code', '')}) - "
                        f"Balance: {live_balance} units [{item.get('category', '')}]"
                    )
                return (
                    "Here are the best product matches and balances:\n\n"
                    + "\n".join(lines)
                )

            # No good match found; provide a helpful preview
            preview = products[:10]
            lines = [
                f"{idx + 1}. {item.get('product_name', 'Unknown')} ({item.get('product_code', '')})"
                for idx, item in enumerate(preview)
            ]
            return (
                "I couldn't find an exact product match. Try a more specific name/code.\n\n"
                "Available examples:\n" + "\n".join(lines)
            )

        lines = []
        for idx, item in enumerate(products[:20], 1):
            name = item.get('product_name', 'Unknown')
            qty = item.get('quantity', 0)
            code = item.get('product_code', '')
            category = item.get('category', '')
            code_str = f" ({code})" if code else ""
            lines.append(f"{idx}. {name}{code_str}: {qty} units [{category}]")

        more_note = f"\n...and {total - 20} more." if total > 20 else ""
        return (
            f"Live inventory from {source_url} (total: {total} products):\n\n"
            + "\n".join(lines) + more_note
        )

    # 2) Fallback: single-product stock-card endpoint
    result = scraper.scrape_inventory("company_website")
    if "error" not in result:
        products = result.get("products", [])
        total = result.get("total_products", len(products))
        source_url = result.get("source_url", "configured source")

        preview = products[:20]
        lines = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(preview)])
        more_note = f"\n...and {total - len(preview)} more products." if total > len(preview) else ""
        return (
            f"Current inventory products from {source_url} (total: {total}):\n\n"
            f"{lines}{more_note}"
        )

    # 3) Final fallback with diagnostics + local sample data
    upstream_error = result.get("error", "Unknown scraping error")
    upstream_status = result.get("status_code")
    upstream_method = result.get("method")
    upstream_url = result.get("url") or result.get("source_url")
    upstream_text = result.get("response_text", "")

    diagnostics = ""
    if upstream_url:
        diagnostics += f"\nUpstream URL: {upstream_url}"
    if upstream_method:
        diagnostics += f"\nMethod: {upstream_method}"
    if upstream_status is not None:
        diagnostics += f"\nStatus: {upstream_status}"
    if upstream_error:
        diagnostics += f"\nError: {upstream_error}"
    if upstream_text:
        diagnostics += f"\nResponse: {upstream_text[:220]}"

    company_data = load_company_data()
    if company_data and 'inventory' in company_data:
        inventory_items = company_data['inventory']
        total = len(inventory_items)
        company_name = company_data.get('company_name', 'Company Data')
        last_updated = company_data.get('last_updated', 'N/A')

        lines = []
        for idx, item in enumerate(inventory_items[:20], 1):
            product = item.get('product_name', 'Unknown')
            qty = item.get('quantity', 0)
            unit = item.get('unit', 'units')
            location = item.get('location', 'N/A')
            status = item.get('status', '')
            lines.append(f"{idx}. {product}: {qty} {unit} @ {location} [{status}]")

        more_note = f"\n...and {total - 20} more items." if total > 20 else ""
        return (
            f"Current inventory from {company_name} (Last updated: {last_updated}):\n"
            f"Total products: {total}\n\n"
            + "\n".join(lines) + more_note
            + "\n\n⚠️ Web scraping failed. Using fallback data from company_data.json."
            + "\nIf diagnostics show 401 Invalid token, reconnect account and ensure browser session token/cookie is provided."
            + (f"\n\nDiagnostics:{diagnostics}" if diagnostics else "")
        )

    attempted = result.get("attempted_urls", [])
    attempted_preview = "\n".join([f"- {url}" for url in attempted[:5]]) if attempted else "- (no URLs attempted)"
    return (
        "I couldn't find inventory products from the configured Stock Card/SC pages. "
        "Please update `config/scraper_config.json` with your real company base URL and SC/inventory paths.\n\n"
        f"Attempted URLs:\n{attempted_preview}"
        + (f"\n\nDiagnostics:{diagnostics}" if diagnostics else "")
    )


def is_affirmation(user_input):
    """
    Detect if user input is an affirmative response (yes, sure, ok, please, etc.)
    """
    affirmation_patterns = [
        r"\b(yes|yeah|yep|yup|sure|ok|okay|please|absolutely|definitely|of course|go ahead)\b",
        r"^(that would be|that sounds|i'd like|i'd love|please)$",
        r"\b(generate|show|create|make|display|show me)\b.*(chart|graph|visual)",
    ]
    normalized = user_input.lower().strip()
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in affirmation_patterns)


def handle_chart_request(user_input, auth_context=None):
    """Fetch live chart/graph data from clone.ulap.biz stock card movement history."""
    normalized_input = normalize_text(user_input)
    chart_triggers = [
        "chart",
        "graph",
        "movement",
        "history", 
        "trend",
        "visualization",
        "visual"
    ]
    
    has_trigger = any(trigger in normalized_input for trigger in chart_triggers)
    if not has_trigger:
        return None
    
    if not SCRAPER_AVAILABLE:
        return "Chart visualization requires web scraping. Please install: pip install requests beautifulsoup4"
    
    try:
        # Load chart config from scraper_config.json
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")
        chart_config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                chart_config = full_config.get('chart_data', {})
        
        if not chart_config:
            return "Chart data configuration not found in config/scraper_config.json"
        
        # Create scraper with chart config
        resolved_auth_context = auth_context if isinstance(auth_context, dict) else None
        scraper = get_company_scraper(auth_context=resolved_auth_context)
        
        # Override config for this request
        scraper.config = chart_config

        selected_product = None

        # Try to resolve product name from query for dynamic product charts
        products_result = scraper.fetch_all_products_with_stock()
        if "error" not in products_result:
            products = products_result.get("products", [])
            if products:
                query_tokens = set(tokenize(normalized_input))
                stop_tokens = {
                    "show", "me", "a", "an", "the", "for", "of", "with",
                    "chart", "graph", "history", "historical", "trend", "trends",
                    "balance", "inventory", "stock", "in", "out", "movement", "movements"
                }
                target_tokens = [t for t in query_tokens if t not in stop_tokens and len(t) > 1]

                def product_score(item):
                    name = normalize_text(str(item.get("product_name", "")))
                    code = normalize_text(str(item.get("product_code", "")))
                    category = normalize_text(str(item.get("category", "")))
                    text = f"{name} {code} {category}"
                    return sum(1 for t in target_tokens if t in text)

                if target_tokens:
                    ranked = sorted(products, key=product_score, reverse=True)
                    if ranked and product_score(ranked[0]) > 0:
                        selected_product = ranked[0]
        
        # Fetch JSON data from graph endpoint
        url = chart_config.get('url')
        method = chart_config.get('api_method', 'POST')

        # Build payload dynamically (defaults + matched product id)
        payload = dict(chart_config.get('api_default_body', {}))

        # Dynamic date range from user query
        parsed_dt1, parsed_dt2 = parse_chart_date_range(
            user_input,
            default_dt1=payload.get("dt1"),
            default_dt2=payload.get("dt2")
        )
        if parsed_dt1:
            payload["dt1"] = parsed_dt1
        if parsed_dt2:
            payload["dt2"] = parsed_dt2

        if selected_product and selected_product.get("product_id"):
            payload["ixProd"] = int(selected_product.get("product_id"))

        graph_data = scraper.fetch_json_api(url, method=method, payload=payload)
        
        if "error" in graph_data:
            return f"Failed to fetch chart data: {graph_data.get('error')}"
        
        # Format chart data for response
        begin_qty = graph_data.get('begQty', 0)
        end_qty = graph_data.get('endQty', 0)
        items = graph_data.get('items', [])

        labels = []
        balances = []
        qty_in_series = []
        qty_out_series = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            label = item.get('YrMo') or item.get('YrWk') or f"Point {idx + 1}"
            labels.append(str(label))
            balances.append(float(item.get('runBal', 0) or 0))
            qty_in_series.append(float(item.get('tIN', 0) or 0))
            qty_out_series.append(float(item.get('tOUT', 0) or 0))

        product_label = "Selected product"
        if selected_product:
            product_label = f"{selected_product.get('product_name', 'Selected product')} ({selected_product.get('product_code', '')})"
        
        summary = f"Stock movement history for {product_label}:\n"
        summary += f"- Beginning quantity: {begin_qty}\n"
        summary += f"- Ending quantity: {end_qty}\n"
        summary += f"- Date range: {payload.get('dt1')} to {payload.get('dt2')}\n"
        summary += f"- Total movements: {len(items)}\n"
        
        if items:
            summary += f"\nRecent movements:\n"
            for idx, item in enumerate(items[:5], 1):
                yr_mo = item.get('YrMo', 'N/A')
                run_bal = item.get('runBal', 'N/A')
                qty_in = item.get('tIN', 0)
                qty_out = item.get('tOUT', 0)
                summary += f"{idx}. {yr_mo}: Balance {run_bal} (IN: {qty_in}, OUT: {qty_out})\n"
            
            if len(items) > 5:
                summary += f"...and {len(items) - 5} more records"
        
        return {
            'type': 'chart',
            'chartType': 'line',
            'title': f"Inventory Movement - {product_label}",
            'chartData': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Running Balance',
                        'data': balances
                    },
                    {
                        'label': 'IN',
                        'data': qty_in_series
                    },
                    {
                        'label': 'OUT',
                        'data': qty_out_series
                    }
                ]
            },
            'summary': summary,
            'data': graph_data,
            'source': url,
            'product': selected_product
        }
    
    except Exception as e:
        print(f"Error fetching chart data: {e}")
        return f"Error generating chart: {str(e)}"


def handle_chart_from_balance_context():
    """
    Generate a General Ledger balance chart from GL sample data.
    Used when user confirms they want to see the balance evolution chart.
    """
    try:
        if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                gl_data = json.load(f)
            
            if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
                trend_data = gl_data['samples']['annual_trend']
                rep = trend_data.get('rep', [])
                
                if rep and len(rep) > 0:
                    # Extract data for line chart visualization
                    labels = [item['YrMo'] for item in rep]
                    balance_data = [item['runBal'] for item in rep]
                    
                    chart_data = {
                        'type': 'chart',
                        'chartType': 'line',
                        'title': "General Ledger - Running Balance",
                        'chartData': {
                            'labels': labels,
                            'datasets': [
                                {
                                    'label': 'Running Balance',
                                    'data': balance_data,
                                    'borderColor': 'rgba(255, 140, 0, 1)',
                                    'backgroundColor': 'rgba(255, 140, 0, 0.1)',
                                    'tension': 0.4
                                }
                            ]
                        }
                    }
                    
                    # Return as JSON so frontend can render it
                    return json.dumps(chart_data)
    except Exception as e:
        print(f"Error generating chart from balance context: {e}")
    
    return None


def detect_chart_type_preference(user_input):
    """
    Detect if user is requesting a specific chart type.
    Returns the requested chart type or None if no preference.
    """
    normalized = user_input.lower()
    
    # Check for specific chart type requests
    line_patterns = [
        r"line\s+(chart|graph)",
        r"(chart|graph).*line",
        r"historical.*graph",
        r"historical.*chart",
        r"evolution",
        r"over time",
        r"not.*bar",
        r"instead of bar",
        r"time.*series",
    ]
    
    pie_patterns = [
        r"pie\s+(chart|graph)",
        r"(chart|graph).*pie",
        r"donut\s+(chart|graph)",
    ]
    
    bar_patterns = [
        r"bar\s+(chart|graph)",
        r"(chart|graph).*bar",
    ]
    
    # Check in order of specificity
    if any(re.search(pattern, normalized) for pattern in line_patterns):
        return 'line'
    elif any(re.search(pattern, normalized) for pattern in pie_patterns):
        return 'pie'
    elif any(re.search(pattern, normalized) for pattern in bar_patterns):
        return 'bar'
    
    return None


def handle_balance_request(user_input, auth_context=None):
    """
    Handle balance inquiry requests dynamically by loading data and generating responses.
    Supports General Ledger balance queries and is extensible for future data types.
    """
    global conversation_history, balance_context
    normalized_input = user_input.lower()
    
    # Check for credit/debit chart requests
    credit_debit_patterns = [
        r"(credit|debit).*(chart|graph|debit|credit)",
        r"(chart|graph).*(credit|debit)",
        r"show.*(credit|debit)",
        r"give me.*(credit|debit)",
    ]
    
    is_credit_debit_request = any(re.search(pattern, normalized_input) for pattern in credit_debit_patterns)
    
    # Also check if user is asking for a different format of the last chart WITHOUT explicitly naming it
    # This handles cases like "show me as a line chart" or "give me a historical graph of it"
    is_chart_type_change_request = (
        detect_chart_type_preference(user_input) is not None and
        any(word in normalized_input for word in ['it', 'that', 'this chart', 'this graph', 'that chart', 'that graph', 'the chart', 'the graph'])
    )
    
    # If user is asking for a chart type change of a previous credit/debit chart, regenerate with new type
    if is_chart_type_change_request and conversation_history and len(conversation_history) > 0:
        last_response = conversation_history[-1]['ai']
        is_last_credit_debit = False
        
        # Check if the last response was a credit/debit chart
        if isinstance(last_response, dict) and last_response.get('title') == "General Ledger - Debits vs Credits":
            is_last_credit_debit = True
        elif isinstance(last_response, str) and "Debits vs Credits" in last_response:
            is_last_credit_debit = True
        
        if is_last_credit_debit:
            is_credit_debit_request = True  # Treat as credit/debit request with type change
    
    if is_credit_debit_request:
        if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                    gl_data = json.load(f)
                
                if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
                    trend_data = gl_data['samples']['annual_trend']
                    rep = trend_data.get('rep', [])
                    
                    if rep and len(rep) > 0:
                        # Detect if user wants a different chart type
                        preferred_chart_type = detect_chart_type_preference(user_input)
                        chart_type = preferred_chart_type or 'bar'  # Default to bar for credit/debit
                        
                        # Extract data for visualization
                        labels = [item['YrMo'] for item in rep]
                        debit_data = [item['tDr'] for item in rep]
                        credit_data = [abs(item['tCr']) for item in rep]
                        
                        # Build chart based on preferred type
                        if chart_type == 'line':
                            datasets = [
                                {
                                    'label': 'Debits',
                                    'data': debit_data,
                                    'borderColor': 'rgba(102, 126, 234, 1)',
                                    'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                                    'tension': 0.4
                                },
                                {
                                    'label': 'Credits',
                                    'data': credit_data,
                                    'borderColor': 'rgba(237, 100, 166, 1)',
                                    'backgroundColor': 'rgba(237, 100, 166, 0.1)',
                                    'tension': 0.4
                                }
                            ]
                        elif chart_type == 'pie':
                            # For pie, sum the totals
                            total_debits = sum(debit_data)
                            total_credits = sum(credit_data)
                            datasets = [
                                {
                                    'label': 'Total Debits vs Credits',
                                    'data': [total_debits, total_credits],
                                    'backgroundColor': [
                                        'rgba(102, 126, 234, 0.8)',
                                        'rgba(237, 100, 166, 0.8)'
                                    ]
                                }
                            ]
                            labels = ['Debits', 'Credits']
                        else:  # bar (default)
                            datasets = [
                                {
                                    'label': 'Debits',
                                    'data': debit_data,
                                    'backgroundColor': 'rgba(102, 126, 234, 0.8)'
                                },
                                {
                                    'label': 'Credits',
                                    'data': credit_data,
                                    'backgroundColor': 'rgba(237, 100, 166, 0.8)'
                                }
                            ]
                        
                        chart_data = {
                            'type': 'chart',
                            'chartType': chart_type,
                            'title': "General Ledger - Debits vs Credits",
                            'chartData': {
                                'labels': labels,
                                'datasets': datasets
                            }
                        }
                        
                        # Return as JSON so frontend can render it
                        return json.dumps(chart_data)
            except Exception as e:
                print(f"Error generating credit/debit chart: {e}")
                return None
    
    # Check for direct balance chart/graph requests
    balance_chart_patterns = [
        r"(graph|chart).*(balance.*evolved|balance.*over time|balance.*time)",
        r"(balance.*evolved|balance.*over time|balance.*time).*(graph|chart)",
        r"show\s+(me\s+)*(balance|gl|ledger).*(chart|graph)",
        r"give\s+me.*(balance|gl|ledger).*(chart|graph|visual)",
        r"show.*(chart|graph).*(balance|gl|ledger).*(evolved|over time)",
        r"how.*balance.*evolved",
        r"balance.*over time",
    ]
    
    is_balance_chart_request = any(re.search(pattern, normalized_input) for pattern in balance_chart_patterns)
    
    # If user is requesting the chart directly, generate it
    if is_balance_chart_request:
        if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                    gl_data = json.load(f)
                
                if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
                    trend_data = gl_data['samples']['annual_trend']
                    rep = trend_data.get('rep', [])
                    
                    if rep and len(rep) > 0:
                        # Detect if user wants a specific chart type
                        preferred_chart_type = detect_chart_type_preference(user_input)
                        chart_type = preferred_chart_type or 'line'  # Default to line for balance
                        
                        # Extract data for visualization
                        labels = [item['YrMo'] for item in rep]
                        balance_data = [item['runBal'] for item in rep]
                        
                        # Build chart based on preferred type
                        if chart_type == 'bar':
                            datasets = [
                                {
                                    'label': 'Running Balance',
                                    'data': balance_data,
                                    'backgroundColor': 'rgba(255, 140, 0, 0.8)'
                                }
                            ]
                        elif chart_type == 'pie':
                            # For pie, show final balance as proportion
                            final_balance = balance_data[-1]
                            datasets = [
                                {
                                    'label': 'Final Balance',
                                    'data': [final_balance],
                                    'backgroundColor': ['rgba(255, 140, 0, 0.8)']
                                }
                            ]
                            labels = ['Running Balance']
                        else:  # line (default)
                            datasets = [
                                {
                                    'label': 'Running Balance',
                                    'data': balance_data,
                                    'borderColor': 'rgba(255, 140, 0, 1)',
                                    'backgroundColor': 'rgba(255, 140, 0, 0.1)',
                                    'tension': 0.4
                                }
                            ]
                        
                        chart_data = {
                            'type': 'chart',
                            'chartType': chart_type,
                            'title': "General Ledger - Running Balance",
                            'chartData': {
                                'labels': labels,
                                'datasets': datasets
                            }
                        }
                        
                        # Return as JSON so frontend can render it
                        return json.dumps(chart_data)
            except Exception as e:
                print(f"Error generating balance chart: {e}")
                return None
    
    # Check if this is a balance-related query
    balance_patterns = [
        r"\b(balance|running balance)\b.*\b(general ledger|gl|ledger)\b",
        r"\b(general ledger|gl|ledger)\b.*\b(balance|running balance)\b",
        r"what is the balance",
        r"tell me the balance",
        r"can you.*balance",
        r"what.*balance",
    ]

    # Direct data requests should also be handled here (not just balance wording).
    gl_data_patterns = [
        r"(give|show|list|provide|fetch).*(data|details|entries|accounts).*(general ledger|gl|ledger)",
        r"(general ledger|gl|ledger).*(data|details|entries|accounts)",
        r"can you give me.*general ledger",
        r"what.*in.*general ledger",
    ]

    is_balance_query = any(re.search(pattern, normalized_input) for pattern in balance_patterns)
    is_gl_query = any(term in normalized_input for term in ['general ledger', 'gl', 'ledger'])
    is_stock_query = any(term in normalized_input for term in ['stock card', 'stock', 'inventory'])
    is_gl_data_query = is_gl_query and any(re.search(pattern, normalized_input) for pattern in gl_data_patterns)

    if not is_balance_query and not is_gl_data_query:
        return None

    # Handle explicit GL data/account listing requests.
    if is_gl_data_query:
        try:
            # Use the dedicated /api/lib/acc source first.
            scraper = get_company_scraper(auth_context=auth_context)
            gl_result = scraper.fetch_general_ledger_accounts()

            if "error" not in gl_result:
                accounts = gl_result.get("accounts", [])
                total_accounts = gl_result.get("total_accounts", len(accounts))
                source_url = gl_result.get("source_url", "https://clone.ulap.biz/api/lib/acc")

                if isinstance(accounts, list) and total_accounts > 0:
                    preview = accounts[:12]
                    lines = []
                    for idx, account in enumerate(preview, 1):
                        if isinstance(account, dict):
                            acc_code = (
                                account.get("AccCd")
                                or account.get("acctCd")
                                or account.get("code")
                                or account.get("acc")
                                or ""
                            )
                            acc_name = (
                                account.get("sAcc")
                                or account.get("account")
                                or account.get("name")
                                or account.get("title")
                                or "Unknown Account"
                            )
                            if acc_code:
                                lines.append(f"{idx}. {acc_code} - {acc_name}")
                            else:
                                lines.append(f"{idx}. {acc_name}")
                        else:
                            lines.append(f"{idx}. {str(account)}")

                    more_note = ""
                    if total_accounts > len(preview):
                        more_note = f"\n...and {total_accounts - len(preview)} more accounts."

                    return (
                        f"General Ledger data retrieved from {source_url}.\n"
                        f"Total accounts: {total_accounts}\n\n"
                        + "\n".join(lines)
                        + more_note
                    )

            # Fallback path for GL intent when live API call fails
            live_gl = get_live_gl_data(force_refresh=False)
            if live_gl:
                source = live_gl.get("source", "live source")
                return (
                    f"I recognized this as a General Ledger data request, but detailed account rows were unavailable right now. "
                    f"Current GL source: {source}."
                )
        except Exception as e:
            print(f"Error handling GL data request: {e}")

        return (
            "I recognized this as a General Ledger data request, but I could not fetch account rows right now. "
            "Please verify the site token/cookie and try again."
        )
    
    # Handle General Ledger balance queries
    if is_gl_query or (not is_stock_query and is_balance_query):
        # Try web scraping first, then fallback to gl_sample_data.json, then company_data.json as last resort
        if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                    gl_data = json.load(f)
                
                if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
                    trend_data = gl_data['samples']['annual_trend']
                    rep = trend_data.get('rep', [])
                    
                    if rep:
                        # Get the latest balance
                        latest_balance = rep[-1]['runBal']
                        first_date = rep[0]['YrMo']
                        last_date = rep[-1]['YrMo']
                        num_periods = len(rep)
                        
                        # Format balance for readability
                        if latest_balance >= 1_000_000:
                            balance_str = f"{latest_balance / 1_000_000:.1f} million"
                        else:
                            balance_str = f"{latest_balance:,.2f}"
                        
                        # Generate dynamic response
                        response = (
                            f"The current General Ledger running balance is {balance_str}. "
                            f"This is based on our sample data spanning {first_date} to {last_date} "
                            f"across {num_periods} transaction periods. "
                            f"Would you like me to generate a chart showing how this balance has evolved over time?"
                        )
                        
                        # Set context for subsequent chart generation
                        balance_context = {
                            'data_source': 'general_ledger',
                            'balance': latest_balance,
                            'date_range': f"{first_date} to {last_date}",
                            'periods': num_periods
                        }
                        
                        return response
            except Exception as e:
                print(f"Error loading GL balance data: {e}")
                return None
    
    # Handle stock card balance queries
    if is_stock_query:
        return (
            "Stock card balance queries are not yet available. "
            "I'm currently configured to work with General Ledger data. "
            "Stock card data integration is planned for future updates."
        )
    
    # Generic balance query without specific data source
    if is_balance_query and not is_gl_query and not is_stock_query:
        return (
            "I can help you with balance information! Please specify which data source you'd like "
            "(e.g., General Ledger, Stock Card, or another data type). "
            "Currently, I have General Ledger sample data available."
        )
    
    return None


def handle_graph_request(user_input):
    """Handle graph generation requests"""
    global last_chart_context

    if not GRAPH_AVAILABLE:
        return "Graph generation is not available. Please install required packages: pip install matplotlib pandas numpy"

    normalized_input = normalize_text(user_input)

    # If user is asking ABOUT a graph, explain instead of generating a new one
    explanation_patterns = [
        "what is the graph based off",
        "what is this graph based off",
        "what is this chart based off",
        "what is the chart based off",
        "what is this graph based on",
        "what is this chart based on",
        "what does this graph show",
        "what does this chart show",
        "where did this graph come from",
        "where did this chart come from"
    ]
    if any(pattern in normalized_input for pattern in explanation_patterns):
        if last_chart_context:
            source = last_chart_context.get("source", "example data")
            title = last_chart_context.get("title", "chart")
            points = last_chart_context.get("data_points", 0)
            return f"This {title.lower()} is based on {source}. It contains {points} data point(s)."
        return "I don't have a previous chart context to explain yet. Ask me to generate a chart first, then I can explain what it's based on."

    # Only generate charts for explicit action requests, not general questions mentioning graph/chart
    request_patterns = [
        r"\b(show|generate|create|make|draw|plot|visualize)\b.*\b(graph|chart|plot)\b",
        r"\b(graph|chart|plot)\b.*\b(for|of|from)\b",
        r"\bvisualization\b"
    ]
    if not any(re.search(pattern, normalized_input) for pattern in request_patterns):
        return None
    
    # Determine chart type
    chart_type = 'line'  # default to line chart for GL data
    if 'bar' in user_input.lower():
        chart_type = 'bar'
    elif 'pie' in user_input.lower():
        chart_type = 'pie'
    elif 'scatter' in user_input.lower():
        chart_type = 'scatter'
    elif 'histogram' in user_input.lower():
        chart_type = 'histogram'
    
    # Check for general ledger data first (highest priority)
    if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json')):
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gl_sample_data.json'), 'r') as f:
                gl_data = json.load(f)
            
            # Use the annual_trend data which has monthly/weekly breakdown
            if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
                trend_data = gl_data['samples']['annual_trend']
                rep = trend_data.get('rep', [])
                
                if rep and len(rep) > 0:
                    # Extract data for visualization
                    labels = [item['YrMo'] for item in rep]
                    debit_data = [item['tDr'] for item in rep]
                    credit_data = [abs(item['tCr']) for item in rep]
                    balance_data = [item['runBal'] for item in rep]
                    
                    if chart_type == 'line':
                        datasets = [
                            {
                                'label': 'Running Balance',
                                'data': balance_data,
                                'borderColor': 'rgba(102, 126, 234, 1)',
                                'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                                'tension': 0.4,
                                'yAxisID': 'y'
                            }
                        ]
                        title = "General Ledger - Running Balance"
                    elif chart_type == 'bar':
                        datasets = [
                            {
                                'label': 'Debits',
                                'data': debit_data,
                                'backgroundColor': 'rgba(102, 126, 234, 0.8)'
                            },
                            {
                                'label': 'Credits',
                                'data': credit_data,
                                'backgroundColor': 'rgba(237, 100, 166, 0.8)'
                            }
                        ]
                        title = "General Ledger - Debits vs Credits"
                    else:
                        # Default to line chart for GL data
                        chart_type = 'line'
                        datasets = [
                            {
                                'label': 'Running Balance',
                                'data': balance_data,
                                'borderColor': 'rgba(102, 126, 234, 1)',
                                'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                                'tension': 0.4
                            }
                        ]
                        title = "General Ledger - Running Balance"
                    
                    last_chart_context = {
                        'title': title,
                        'source': 'General Ledger sample data (gl_sample_data.json)',
                        'data_points': len(labels)
                    }
                    
                    return {
                        'type': 'chart',
                        'chartType': chart_type,
                        'title': title,
                        'chartData': {
                            'labels': labels,
                            'datasets': datasets
                        }
                    }
        except Exception as e:
            print(f"Error loading GL data: {e}")
            pass
    
    # Check if we have scraped data to visualize
    if os.path.exists('scraped_data_temp.json'):
        try:
            with open('scraped_data_temp.json', 'r') as f:
                scraped_data = json.load(f)
            
            # Try to extract numerical data from scraped content
            if scraped_data.get('content') and len(scraped_data['content']) > 0:
                word_counts = [len(item.split()) for item in scraped_data['content'][:5]]
                labels = [f"Item {i+1}" for i in range(len(word_counts))]
                
                last_chart_context = {
                    'title': 'Word Count Analysis',
                    'source': 'recently scraped website content (word counts of top items)',
                    'data_points': len(word_counts)
                }
                return {
                    'type': 'chart',
                    'chartType': chart_type,
                    'title': 'Word Count Analysis',
                    'chartData': {
                        'labels': labels,
                        'datasets': [{
                            'label': 'Word Count',
                            'data': word_counts,
                            'backgroundColor': ['rgba(102, 126, 234, 0.8)', 'rgba(118, 75, 162, 0.8)', 'rgba(237, 100, 166, 0.8)', 'rgba(255, 154, 158, 0.8)', 'rgba(255, 127, 80, 0.8)']
                        }]
                    }
                }
        except Exception as e:
            pass
    
    # Generate example chart data
    if chart_type == 'bar':
        labels = ["Q1", "Q2", "Q3", "Q4"]
        datasets = [{
            'label': 'Quarterly Performance',
            'data': [100, 150, 130, 180],
            'backgroundColor': ['rgba(102, 126, 234, 0.8)', 'rgba(118, 75, 162, 0.8)', 'rgba(237, 100, 166, 0.8)', 'rgba(255, 154, 158, 0.8)']
        }]
        title = "Quarterly Performance"
        data_points = len(labels)
    elif chart_type == 'line':
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        datasets = [
            {
                'label': 'Series A',
                'data': [10, 15, 13, 17, 20, 22],
                'borderColor': 'rgba(102, 126, 234, 1)',
                'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Series B',
                'data': [12, 11, 14, 16, 19, 21],
                'borderColor': 'rgba(118, 75, 162, 1)',
                'backgroundColor': 'rgba(118, 75, 162, 0.1)',
                'tension': 0.4
            }
        ]
        title = "Trend Analysis"
        data_points = len(labels) * len(datasets)
    elif chart_type == 'pie':
        labels = ["Category A", "Category B", "Category C", "Category D"]
        datasets = [{
            'label': 'Distribution',
            'data': [30, 25, 20, 25],
            'backgroundColor': ['rgba(102, 126, 234, 0.8)', 'rgba(118, 75, 162, 0.8)', 'rgba(237, 100, 166, 0.8)', 'rgba(255, 154, 158, 0.8)']
        }]
        title = "Distribution"
        data_points = len(labels)
    else:
        return "Please provide data for the graph or scrape a website first."
    
    last_chart_context = {
        'title': title,
        'source': 'built-in sample dataset',
        'data_points': data_points
    }

    return {
        'type': 'chart',
        'chartType': chart_type,
        'title': title,
        'chartData': {
            'labels': labels,
            'datasets': datasets
        }
    }


def build_system_prompt(live_context=""):
    """Build the Ollama system prompt from the company knowledge base + optional live data."""
    from datetime import datetime as _dt
    today = _dt.now().strftime("%B %d, %Y")
    knowledge_text = ""
    try:
        data = load_knowledge()
        entries = data.get("knowledge", [])
        lines = []
        # Limit to 10 entries instead of 40 for faster response time
        for item in entries[:10]:
            lines.append("Q: " + item['pattern'] + "\nA: " + item['response'])
        knowledge_text = "\n\n".join(lines)
    except Exception:
        pass
    # Simplified system prompt for faster inference
    system = (
        "You are a helpful AI assistant for a company's business system.\n"
        "Be concise, fast, and accurate. Today: " + today + ".\n"
        "Answer about inventory, financials, and system data using provided context.\n"
    )
    if knowledge_text:
        system += "Knowledge base:\n" + knowledge_text
    if live_context:
        system += "\n\nCurrent data:\n" + live_context[:OLLAMA_LIVE_CONTEXT_MAX_CHARS]
    return system


def should_fetch_live_context(user_input):
    """Avoid expensive live-data calls for generic conversation."""
    normalized = normalize_text(user_input)
    fast_skip = ["hello", "hi", "hey", "thanks", "thank you", "ok", "sure", "bye"]
    if any(term == normalized for term in fast_skip):
        return False

    live_markers = [
        "inventory", "stock", "product", "balance", "ledger", "account", "receivable",
        "report", "current", "latest", "available", "on hand", "branch", "warehouse",
    ]
    return any(marker in normalized for marker in live_markers)


def get_connection_status_response(user_input):
    """Provide a fast direct answer for account/session status questions."""
    normalized = normalize_text(user_input)
    patterns = [
        r"are\s+there\s+any\s+accounts?\s+logged\s+in",
        r"are\s+there\s+any\s+accounts?\s+currently\s+logged\s+in",
        r"accounts?\s+logged\s+in",
        r"who\s+is\s+logged\s+in",
    ]
    if not any(re.search(p, normalized) for p in patterns):
        return None

    has_saved_creds = bool((os.getenv("SITE_USERNAME") or "").strip() and (os.getenv("SITE_PASSWORD") or "").strip())
    has_token = False
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
            for section in cfg.values():
                if isinstance(section, dict) and str(section.get("api_fixed_auth_token", "")).strip():
                    has_token = True
                    break
    except Exception:
        has_token = False

    if has_saved_creds and has_token:
        user = (os.getenv("SITE_USERNAME") or "saved credentials").strip()
        return (
            f"A company account is connected ({user}), but I cannot list active website user sessions from this endpoint."
        )
    return "No connected company account is currently stored."


def fetch_relevant_live_data(user_input, auth_context=None):
    """Detect intent and pre-fetch live API data to pass as context to Ollama."""
    if not SCRAPER_AVAILABLE:
        return ""
    normalized = normalize_text(user_input)
    context_parts = []

    # Inventory / product intent
    inventory_triggers = ["inventory", "stock card", "stock", "product", "on hand"]
    if any(t in normalized for t in inventory_triggers) and not any(w in normalized for w in ["chart", "graph"]):
        try:
            scraper = get_company_scraper(auth_context)
            result = scraper.fetch_all_products_with_stock()
            if "error" not in result:
                products = result.get("products", [])
                total = len(products)
                preview = products[:12]
                lines = []
                for p in preview:
                    lines.append(
                        "- " + str(p.get('product_name', 'Unknown')) +
                        " (" + str(p.get('product_code', '')) + "): " +
                        str(p.get('quantity', 0)) + " units [" + str(p.get('category', '')) + "]"
                    )
                more = "\n...and " + str(total - len(preview)) + " more." if total > len(preview) else ""
                context_parts.append("INVENTORY (" + str(total) + " total products):\n" + "\n".join(lines) + more)
        except Exception as e:
            print("[live data] inventory fetch error: " + str(e))

    # General Ledger intent
    gl_triggers = ["general ledger", " gl ", "ledger", "balance", "accounts"]
    if any(t in normalized for t in gl_triggers) and "receivable" not in normalized:
        try:
            scraper = get_company_scraper(auth_context)
            result = scraper.fetch_general_ledger_accounts()
            if "error" not in result:
                accounts = result.get("accounts", [])[:12]
                lines = []
                for acc in accounts:
                    code = acc.get("AccCd") or acc.get("acctCd") or acc.get("code") or ""
                    name = acc.get("sAcc") or acc.get("account") or acc.get("name") or "Unknown"
                    lines.append("- " + code + ": " + name if code else "- " + name)
                context_parts.append("GENERAL LEDGER ACCOUNTS:\n" + "\n".join(lines))
        except Exception as e:
            print("[live data] GL fetch error: " + str(e))

    # Accounts Receivable intent
    ar_triggers = ["receivable", "customers with debt", "customer debt", "outstanding", "ar report", "accounts receivable"]
    if any(t in normalized for t in ar_triggers):
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "scraper_config.json")
            with open(config_path) as f:
                full_config = json.load(f)
            ar_config = full_config.get("accounts_receivable", {})
            if ar_config:
                ar_scraper = WebScraper(
                    proxy=None,
                    auth_token=ar_config.get("api_fixed_auth_token"),
                    auth_header_name=ar_config.get("api_fixed_auth_header", "x-access-tokens"),
                    config=ar_config,
                )
                result = ar_scraper.fetch_json_api(
                    ar_config.get("url"),
                    method=ar_config.get("api_method", "POST"),
                    payload=ar_config.get("api_default_body", {}),
                )
                if "error" not in result:
                    context_parts.append(
                        "ACCOUNTS RECEIVABLE DATA:\n" + json.dumps(result, indent=2)[:1000]
                    )
                else:
                    context_parts.append(
                        "ACCOUNTS RECEIVABLE: Could not fetch live data - " +
                        str(result.get('error', 'unknown error')) +
                        ". The AR endpoint may need configuration at clone.ulap.biz."
                    )
        except Exception as e:
            print("[live data] AR fetch error: " + str(e))

    return "\n\n".join(context_parts)


def ollama_respond(user_input, live_context="", history=None):
    """Send user input to the local Ollama model and return the response."""
    if not OLLAMA_AVAILABLE or _ollama_lib is None:
        return None
    system_prompt = build_system_prompt(live_context)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for exchange in history[-3:]:
            messages.append({"role": "user", "content": exchange.get("user", "")})
            ai_resp = exchange.get("ai", "")
            if isinstance(ai_resp, dict) or (isinstance(ai_resp, str) and ai_resp.strip().startswith("{")):
                ai_resp = "[A chart or structured data visualization was shown to the user]"
            messages.append({"role": "assistant", "content": str(ai_resp)})
    messages.append({"role": "user", "content": user_input})
    options = {
        "num_ctx": OLLAMA_NUM_CTX,
        "num_predict": OLLAMA_NUM_PREDICT,
        "temperature": OLLAMA_TEMPERATURE,
    }
    model_candidates = OLLAMA_FALLBACK_MODELS if OLLAMA_FALLBACK_MODELS else [OLLAMA_MODEL]
    for model_name in model_candidates:
        try:
            chat_kwargs = {
                "model": model_name,
                "messages": messages,
                "options": options,
                "keep_alive": OLLAMA_KEEP_ALIVE,
            }
            if str(OLLAMA_THINK).strip().lower() not in {"", "none", "off", "false", "0"}:
                chat_kwargs["think"] = OLLAMA_THINK

            response = _ollama_lib.chat(**chat_kwargs)
            content = response.get("message", {}).get("content", "")
            if content:
                return content.strip()
        except Exception as e:
            print("[Ollama] model " + model_name + " error: " + str(e))
            continue
    return None


def respond(user_input, site_context=None, auth_context=None):
    global balance_context, conversation_history, extracted_context

    load_conversation_store()
    extract_context_from_input(user_input)

    normalized = normalize_text(user_input)

    connection_status = get_connection_status_response(user_input)
    if connection_status:
        return connection_status

    # Charts/graphs always use the structured handler - frontend needs the data format
    is_chart_request = any(w in normalized for w in ["chart", "graph", "visual", "movement history"])
    if is_chart_request:
        if is_affirmation(user_input) and conversation_history:
            last_ai_raw = conversation_history[-1]['ai']
            last_ai_str = str(last_ai_raw).lower() if isinstance(last_ai_raw, dict) else last_ai_raw.lower()
            if any(p in last_ai_str for p in [
                "would you like me to generate a chart",
                "would you like to see a chart",
                "want me to show you a chart",
            ]):
                chart = handle_chart_from_balance_context()
                if chart:
                    return chart
        live_chart = handle_chart_request(user_input)
        if live_chart:
            return live_chart
        graph = handle_graph_request(user_input)
        if graph:
            return graph

    # Branches returns a structured signal - frontend depends on this format
    branches = handle_branches_request(user_input)
    if branches:
        return branches

    # --- Primary path: Ollama AI ---
    if OLLAMA_AVAILABLE:
        live_context = ""
        if should_fetch_live_context(user_input):
            live_context = fetch_relevant_live_data(user_input, auth_context=auth_context)
        ollama_answer = ollama_respond(user_input, live_context=live_context, history=conversation_history)
        if ollama_answer:
            return ollama_answer

    # --- Fallback: original rule-based system (used when Ollama is not running) ---
    if is_affirmation(user_input) and conversation_history:
        last_ai_raw = conversation_history[-1]['ai'] if conversation_history else ""
        last_ai = str(last_ai_raw).lower() if isinstance(last_ai_raw, dict) else last_ai_raw.lower()
        if any(phrase in last_ai for phrase in [
            "would you like me to generate a chart",
            "would you like to see a chart",
            "want me to show you a chart",
            "balance.*evolved"
        ]):
            chart_response = handle_chart_from_balance_context()
            if chart_response:
                return chart_response

    greeting_response = handle_greeting_request(user_input)
    if greeting_response:
        return greeting_response

    inventory_response = handle_inventory_request(user_input, site_context=site_context)
    if inventory_response:
        return inventory_response

    scrape_response = handle_scrape_request(user_input)
    if scrape_response:
        return scrape_response

    balance_response = handle_balance_request(user_input)
    if balance_response:
        return balance_response

    math_answer = try_math(user_input)
    if math_answer:
        return math_answer

    live_site_response = answer_from_live_site(user_input, site_context=site_context)
    if live_site_response:
        return live_site_response

    stored_response, context_matches = check_knowledge(user_input)
    if stored_response:
        return stored_response

    relevant_articles = search_articles(user_input, max_results=3)
    if relevant_articles:
        query_tokens = set(tokenize(user_input))
        context_parts = []
        for article in relevant_articles[:2]:
            relevant_text = extract_relevant_text(article['content'], query_tokens, max_length=400)
            if relevant_text and len(relevant_text) > 50:
                context_parts.append(relevant_text)
        if context_parts:
            return format_natural_response(context_parts, user_input)

    if context_matches:
        best_match = max(context_matches, key=lambda x: combined_similarity(user_input, x['pattern']))
        return best_match['response']

    return None

def main():
    print("AI Assistant Started")
    print("Using tokenized Wikipedia corpus with natural language formatting")
    print("Type 'exit' to quit.\n")
    
    # Preload articles database
    load_articles_db()

    while True:
        user_input = input("You: ")

        if user_input.lower() == "exit":
            break

        # Show loading animation while thinking
        loader = LoadingAnimation()
        loader.start()
        
        try:
            answer = respond(user_input)
        finally:
            loader.stop()

        if answer:
            print("AI:", answer)
        else:
            print("AI: I don't know the answer.")
            add_choice = input("Add knowledge? (y/n): ").strip().lower()
            
            if add_choice == 'y':
                new_answer = input("What should I answer? ")
                add_knowledge(user_input, new_answer)
            else:
                print("Skipped learning this response.")


if __name__ == "__main__":
    main()