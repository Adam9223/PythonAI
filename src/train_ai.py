from datasets import load_dataset
import json
import re

# Load the wikitext dataset
print("Loading Salesforce wikitext-103-v1 dataset from Hugging Face...")
ds = load_dataset("Salesforce/wikitext", "wikitext-103-v1")

# Use the train split
dataset = ds['train']
print(f"Dataset loaded: {len(dataset)} articles")

# Create articles database
print(f"\nProcessing all {len(dataset)} articles for context database...")
print("This may take a while. Progress will be shown every 50,000 articles.\n")

articles = []
skipped = 0

for idx in range(len(dataset)):
    text = dataset[idx]['text'].strip()
    
    # Progress indicator
    if (idx + 1) % 50000 == 0:
        print(f"Progress: {idx + 1}/{len(dataset)} articles | Stored: {len(articles)} | Skipped: {skipped}")
    
    # Skip empty or very short texts
    if len(text) < 200:
        skipped += 1
        continue
    
    # Extract title (usually appears at start, often with = symbols)
    title_match = re.search(r'= (.+?) =', text)
    title = title_match.group(1).strip() if title_match else None
    
    # Skip if no title found (likely not a proper article)
    if not title or len(title) < 3:
        skipped += 1
        continue
    
    # Clean up the text but keep full content
    cleaned_text = re.sub(r'\n\n+', '\n\n', text)  # Normalize paragraph breaks
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)  # Normalize whitespace
    
    # Store article with title and content
    article = {
        "title": title,
        "content": cleaned_text
    }
    articles.append(article)

print(f"\nProcessing complete!")
print(f"  Total articles stored: {len(articles)}")
print(f"  Articles skipped: {skipped}")

# Save articles database
with open("articles_db.json", "w") as f:
    json.dump({"articles": articles}, f, indent=2)

print(f"\n✓ Articles database saved to articles_db.json")
print(f"  File size: {len(json.dumps(articles)) / (1024*1024):.2f} MB")
print(f"\nThe AI will now use these articles to provide context-based responses!")
