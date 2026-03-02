#!/usr/bin/env python3
"""
Test the transformer-based response generation with tokenized corpus
"""
from main import search_articles, tokenize, model
import sys

def test_query(query):
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    # Tokenize query
    tokens = tokenize(query)
    print(f"Query tokens: {tokens}\n")
    
    # Search for relevant articles
    print("Searching tokenized corpus...")
    articles = search_articles(query, max_results=2)
    
    if not articles:
        print("❌ No relevant articles found\n")
        return
    
    print(f"✓ Found {len(articles)} relevant articles\n")
    
    # Build context from articles (like transformer RAG)
    context_text = "Relevant information from knowledge base:\n\n"
    for article in articles:
        title = article['title']
        content = article['content'][:600]  # First 600 chars
        context_text += f"Topic: {title}\n{content}\n\n"
    
    print("Context retrieved:")
    print("-" * 60)
    print(context_text[:400] + "...\n")
    print("-" * 60)
    
    # Generate response using transformer
    print("\nGenerating response with LLM transformer...\n")
    try:
        prompt = f"{context_text}\nBased on the above information, please answer this question: {query}\n\nProvide a clear, concise answer."
        response = model.invoke(prompt)
        print(f"AI Response:\n{response.strip()}\n")
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        print("\nFallback - showing raw context from corpus:")
        print(articles[0]['content'][:500])

# Test queries
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        test_query(query)
    else:
        test_query("what is mathematics")
        test_query("tell me about numbers")
