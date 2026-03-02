import json
import os
import re
import sys
import time
import threading
from difflib import SequenceMatcher
from langchain_ollama import OllamaLLM

FILE_NAME = "knowledge.json"

model = OllamaLLM(model="llama3:latest")


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

def respond(user_input):
    # Try math first
    math_answer = try_math(user_input)
    if math_answer:
        return math_answer

    # Check knowledge base
    stored_response, context_matches = check_knowledge(user_input)
    if stored_response:
        return stored_response

    # If we have context matches, try to provide a helpful response
    if context_matches:
        # Show related knowledge to user as a fallback
        context_response = "Based on related knowledge:\n"
        for i, match in enumerate(context_matches[:2], 1):
            context_response += f"\n{i}. {match['response'][:200]}"
            if len(match['response']) > 200:
                context_response += "..."
        
        # Try to generate with LLM using context
        try:
            context_text = "Related knowledge:\n"
            for match in context_matches:
                context_text += f"- Q: {match['pattern'][:80]}\n  A: {match['response'][:150]}\n"
            
            prompt = f"{context_text}\nBased on the above context and your knowledge, answer: {user_input}"
            ai_response = model.invoke(prompt)
            return ai_response.strip()
        except Exception as e:
            # If LLM fails, return the context-based response as fallback
            print(f"[Note: Using knowledge base context, LLM unavailable]")
            return context_response
    
    # Try direct LLM without context as last resort
    try:
        ai_response = model.invoke(user_input)
        return ai_response.strip()
    except Exception as e:
        # Only return None if we truly have nothing
        return None


 

def main():
    print("AI Assistant Started (Trained on 147+ knowledge entries)")
    print("Type 'exit' to quit.\n")

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