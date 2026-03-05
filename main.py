import json
import os
import re
import sys
import time
import threading
from difflib import SequenceMatcher

# Import new modules for web scraping and graph generation
try:
    from web_scraper import WebScraper
    from graph_generator import GraphGenerator
    SCRAPER_AVAILABLE = True
    GRAPH_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some features unavailable - {e}")
    SCRAPER_AVAILABLE = False
    GRAPH_AVAILABLE = False

FILE_NAME = "knowledge.json"
ARTICLES_DB = "articles_db.json"

# Global cache for articles database
articles_cache = None
last_chart_context = None
live_site_cache = None
live_site_cache_timestamp = 0
LIVE_SITE_CACHE_SECONDS = 90

print("AI Assistant - Retrieval-Augmented Generation System")
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


def get_company_scraper():
    """Create scraper without backend proxy; frontend should handle proxying/access."""
    return WebScraper(proxy=None)


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
            return f"Please configure the company website in scraper_config.json first."
        
        return f"Scraped company website: {data['total_items']} items found"
    
    return None


def handle_inventory_request(user_input, site_context=None):
    """Handle inventory/product lookup requests from stock card (SC) or inventory pages."""
    if not SCRAPER_AVAILABLE:
        return "Inventory lookup is not available. Please install required packages: pip install requests beautifulsoup4"

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

    scraper = get_company_scraper()
    result = scraper.scrape_inventory("company_website")

    if "error" in result:
        attempted = result.get("attempted_urls", [])
        attempted_preview = "\n".join([f"- {url}" for url in attempted[:5]]) if attempted else "- (no URLs attempted)"
        return (
            "I couldn't find inventory products from the configured Stock Card/SC pages yet. "
            "Please update `PythonAI/scraper_config.json` with your real company base URL and SC/inventory paths.\n\n"
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
    chart_type = 'bar'  # default
    if 'line' in user_input.lower():
        chart_type = 'line'
    elif 'pie' in user_input.lower():
        chart_type = 'pie'
    elif 'scatter' in user_input.lower():
        chart_type = 'scatter'
    elif 'histogram' in user_input.lower():
        chart_type = 'histogram'
    
    # Check if we have scraped data to visualize
    if os.path.exists('scraped_data_temp.json'):
        try:
            with open('scraped_data_temp.json', 'r') as f:
                scraped_data = json.load(f)
            
            # Try to extract numerical data from scraped content
            if chart_type == 'bar':
                data = {f"Item {i+1}": len(item.split()) for i, item in enumerate(scraped_data['content'][:5])}
                last_chart_context = {
                    'title': 'Word Count Analysis',
                    'source': 'recently scraped website content (word counts of top items)',
                    'data_points': len(data)
                }
                return {
                    'type': 'chart',
                    'chartType': chart_type,
                    'title': 'Word Count Analysis',
                    'data': data
                }
        except Exception as e:
            pass
    
    # Generate example chart data
    if chart_type == 'bar':
        data = {"Q1": 100, "Q2": 150, "Q3": 130, "Q4": 180}
        title = "Quarterly Performance"
    elif chart_type == 'line':
        data = {"Series A": [10, 15, 13, 17, 20, 22], "Series B": [12, 11, 14, 16, 19, 21]}
        title = "Trend Analysis"
    elif chart_type == 'pie':
        data = {"Category A": 30, "Category B": 25, "Category C": 20, "Category D": 25}
        title = "Distribution"
    else:
        return "Please provide data for the graph or scrape a website first."
    
    # Return structured data for frontend
    data_points = 0
    if isinstance(data, dict):
        if data and all(isinstance(v, list) for v in data.values()):
            data_points = sum(len(v) for v in data.values())
        else:
            data_points = len(data)

    last_chart_context = {
        'title': title,
        'source': 'built-in sample dataset',
        'data_points': data_points
    }

    return {
        'type': 'chart',
        'chartType': chart_type,
        'title': title,
        'data': data
    }


def respond(user_input, site_context=None):
    # Check for inventory/stock card requests
    inventory_response = handle_inventory_request(user_input, site_context=site_context)
    if inventory_response:
        return inventory_response

    # Check for web scraping requests
    scrape_response = handle_scrape_request(user_input)
    if scrape_response:
        return scrape_response
    
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