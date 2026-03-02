import json
import os
import re
import sys
import time
import threading
from difflib import SequenceMatcher

FILE_NAME = "knowledge.json"
ARTICLES_DB = "articles_db.json"

# Global cache for articles database
articles_cache = None

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
        
        if score > 0.1:  # Minimum threshold
            scored_articles.append((article, score))
    
    # Sort by score and return top results
    scored_articles.sort(key=lambda x: x[1], reverse=True)
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

    # Sort by score and get top 3 matches
    best_matches.sort(key=lambda x: x[1], reverse=True)
    top_matches = best_matches[:3]

    # If top match is very strong, return it directly
    if top_matches[0][1] > 0.75:  # Lowered threshold due to tokenization improving accuracy
        return top_matches[0][0]["response"], []

    # Return partial matches as context for LLM (threshold 0.3 for token-based)
    context_matches = [item for item, score in top_matches if score > 0.3]
    return None, context_matches
    context_matches = [item for item, score in top_matches if score > 0.5]
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
    
    # Extract complete, well-formed sentences
    sentences = []
    for s in main_context.split('.'):
        s = s.strip()
        # Only keep sentences that are substantial and start with uppercase
        if len(s) > 40 and s and s[0].isupper():
            sentences.append(s + '.')
    
    if not sentences:
        # Fallback: just clean and truncate the context
        return main_context[:300] + "..." if len(main_context) > 300 else main_context
    
    # Use up to 2 complete sentences for a concise response
    content = ' '.join(sentences[:2])
    
    # If too long, truncate to reasonable length
    if len(content) > 500:
        content = content[:497] + "..."
    
    # Add a natural conversational intro based on query type
    query_lower = query.lower()
    if any(word in query_lower for word in ['what is', 'what are', 'define']):
        # Definitional question
        response = content
    elif any(word in query_lower for word in ['tell me', 'explain', 'describe']):
        # Explanatory question
        response = content
    elif any(word in query_lower for word in ['how', 'why']):
        # Process question
        response = content
    else:
        # General query
        response = content
    
    return response


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


def respond(user_input):
    # Try math first
    math_answer = try_math(user_input)
    if math_answer:
        return math_answer

    # Check knowledge base first (for greetings and saved knowledge)
    stored_response, context_matches = check_knowledge(user_input)
    if stored_response:
        return stored_response

    # Search Wikipedia articles database for relevant context
    relevant_articles = search_articles(user_input, max_results=3)
    
    if relevant_articles:
        query_tokens = set(tokenize(user_input))
        
        # Extract relevant text from top articles
        context_parts = []
        for article in relevant_articles[:2]:  # Use top 2 articles
            relevant_text = extract_relevant_text(article['content'], query_tokens, max_length=400)
            context_parts.append(relevant_text)
        
        # Format into a natural, conversational response
        natural_response = format_natural_response(context_parts, user_input)
        return natural_response
    
    # If we have context matches from knowledge base, use them
    if context_matches:
        context_response = "Based on related knowledge:\n"
        for i, match in enumerate(context_matches[:2], 1):
            context_response += f"\n{i}. {match['response'][:200]}"
            if len(match['response']) > 200:
                context_response += "..."
        return context_response
    
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