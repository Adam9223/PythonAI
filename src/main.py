import json
import os
import re
import sys
import time
import threading
from datetime import datetime
from difflib import SequenceMatcher

# Import new modules for web scraping and graph generation
try:
    from .web_scraper import WebScraper
    from .graph_generator import GraphGenerator
    SCRAPER_AVAILABLE = True
    GRAPH_AVAILABLE = True
except ImportError:
    # Fallback for direct script execution
    try:
        from web_scraper import WebScraper
        from graph_generator import GraphGenerator
        SCRAPER_AVAILABLE = True
        GRAPH_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: Some features unavailable - {e}")
        SCRAPER_AVAILABLE = False
        GRAPH_AVAILABLE = False

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


def get_company_scraper(auth_token=None):
    """Create scraper with optional auth token from frontend."""
    return WebScraper(proxy=None, auth_token=auth_token)


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
        # Try to get live site data
        live_data = get_live_company_data(force_refresh)
        
        # If we have GL-related fields in the live data, use them
        if live_data and "error" not in live_data:
            # Check for GL data in scraped content
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
    if not SCRAPER_AVAILABLE:
        return "Web scraping is not available. Please install required packages: pip install requests beautifulsoup4"
    
    # Check if user is asking to scrape a website
    scrape_keywords = ['scrape', 'fetch', 'get data from', 'extract from', 'pull data from']
    if not any(keyword in user_input.lower() for keyword in scrape_keywords):
        return None
    
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


def handle_inventory_request(user_input, site_context=None, auth_token=None):
    """Handle inventory/product lookup requests from stock card (SC) or inventory pages."""
    normalized_input = normalize_text(user_input)
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
    intent_words = ["what", "list", "show", "get", "current", "available"]
    has_trigger = any(trigger in normalized_input for trigger in inventory_triggers)
    has_intent = any(word in normalized_input for word in intent_words)

    if not (has_trigger and has_intent):
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

    scraper = get_company_scraper(auth_token=auth_token)
    result = scraper.scrape_inventory("company_website")

    if "error" in result:
        # Fallback to company_data.json if web scraping fails
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
                + "\n".join(lines) + more_note +
                "\n\n⚠️ Web scraping failed. Using fallback data from company_data.json. Please update config/scraper_config.json."
            )
        
        attempted = result.get("attempted_urls", [])
        attempted_preview = "\n".join([f"- {url}" for url in attempted[:5]]) if attempted else "- (no URLs attempted)"
        return (
            "I couldn't find inventory products from the configured Stock Card/SC pages. "
            "Please update `config/scraper_config.json` with your real company base URL and SC/inventory paths.\n\n"
            f"Attempted URLs:\n{attempted_preview}"
        )

    products = result.get("products", [])
    total = result.get("total_products", len(products))
    source_url = result.get("source_url", "configured source")

    preview = products[:20]
    lines = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(preview)])
    more_note = ""
    if total > len(preview):
        more_note = f"\n...and {total - len(preview)} more products."

    return (
        f"Current inventory products from {source_url} (total: {total}):\n\n"
        f"{lines}{more_note}"
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


def handle_balance_request(user_input):
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
    
    is_balance_query = any(re.search(pattern, normalized_input) for pattern in balance_patterns)
    if not is_balance_query:
        return None
    
    # Check for specific data source mentions
    is_gl_query = any(term in normalized_input for term in ['general ledger', 'gl', 'ledger'])
    is_stock_query = any(term in normalized_input for term in ['stock card', 'stock', 'inventory'])
    
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


def respond(user_input, site_context=None):
    global balance_context, conversation_history, extracted_context
    
    # Load conversation history from persistent store
    load_conversation_store()
    
    # Extract context from current input
    extract_context_from_input(user_input)
    
    # Check conversation history for relevant context
    relevant_history = get_relevant_history(user_input, max_results=3)
    
    # Check if user is confirming a chart generation offer
    # by looking at conversation history
    if is_affirmation(user_input) and conversation_history:
        # Check if the last AI response asked about generating a chart
        last_ai_response_raw = conversation_history[-1]['ai'] if conversation_history else ""
        # Handle AI response that might be a dict (chart data) or string
        if isinstance(last_ai_response_raw, dict):
            last_ai_response = str(last_ai_response_raw).lower()
        else:
            last_ai_response = last_ai_response_raw.lower()
        
        if any(phrase in last_ai_response for phrase in [
            "would you like me to generate a chart",
            "would you like to see a chart",
            "want me to show you a chart",
            "want to see this visualized",
            "balance.*evolved"
        ]):
            # User is confirming the chart offer from previous response
            chart_response = handle_chart_from_balance_context()
            if chart_response:
                return chart_response
    
    # Check if user is referring to something from past conversation
    # (words like "that", "it", "the", "this" without clear subject)
    reference_words = ['that', 'it', 'the one', 'that one', 'this', 'what you mentioned']
    is_referencing = any(word in user_input.lower() for word in reference_words)
    
    if is_referencing and relevant_history:
        # User is likely referring to something we discussed before
        past_context = relevant_history[0]
        # Continue using the same context from previous interaction
        balance_context = balance_context or {
            'referenced_exchange': past_context['user'],
            'previous_response': past_context['ai']
        }

    # Handle greetings/chitchat with a deterministic response
    greeting_response = handle_greeting_request(user_input)
    if greeting_response:
        return greeting_response
    
    # Check for inventory/stock card requests
    inventory_response = handle_inventory_request(user_input, site_context=site_context)
    if inventory_response:
        return inventory_response

    # Check for web scraping requests
    scrape_response = handle_scrape_request(user_input)
    if scrape_response:
        return scrape_response
    
    # Check for balance inquiries (dynamic generation)
    balance_response = handle_balance_request(user_input)
    if balance_response:
        return balance_response
    
    # Check for graph generation requests
    graph_response = handle_graph_request(user_input)
    if graph_response:
        return graph_response
    
    # Try math first
    math_answer = try_math(user_input)
    if math_answer:
        return math_answer

    # Auto-ground factual questions from proxied company website when relevant
    live_site_response = answer_from_live_site(user_input, site_context=site_context)
    if live_site_response:
        return live_site_response

    # Check knowledge base first (for greetings and saved knowledge)
    stored_response, context_matches = check_knowledge(user_input)
    if stored_response:
        return stored_response

    # Search Wikipedia articles database for relevant context
    relevant_articles = search_articles(user_input, max_results=3)
    
    if relevant_articles:
        # Verify we have strong matches before using them
        query_tokens = set(tokenize(user_input))
        
        # Extract relevant text from top articles
        context_parts = []
        for article in relevant_articles[:2]:  # Use top 2 articles
            relevant_text = extract_relevant_text(article['content'], query_tokens, max_length=400)
            if relevant_text and len(relevant_text) > 50:  # Only use non-empty, substantial responses
                context_parts.append(relevant_text)
        
        if context_parts:
            # Format into a natural, conversational response
            natural_response = format_natural_response(context_parts, user_input)
            return natural_response
    
    # If we have context matches from knowledge base, use them
    if context_matches:
        # Return best matching response from knowledge base
        best_match = max(context_matches, key=lambda x: combined_similarity(user_input, x['pattern']))
        return best_match['response']
    
    # No relevant context found
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