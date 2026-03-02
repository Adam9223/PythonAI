import json
import os
import re
from difflib import SequenceMatcher
from langchain_ollama import OllamaLLM

FILE_NAME = "knowledge.json"

model = OllamaLLM(model="llama3:latest")


def normalize_text(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", text.lower())). strip()

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

    for item in data["knowledge"]:
        if normalize_text(item["pattern"]) == normalized_input:
            return item["response"], []

    best_matches = []
    scores = []

    for item in data["knowledge"]:
        pattern = normalize_text(item["pattern"])
        score = similar(normalized_input, pattern)
        best_matches.append((item, score))
        scores.append(score)

    # Sort by score and get top 3 matches
    best_matches.sort(key=lambda x: x[1], reverse=True)
    top_matches = best_matches[:3]

    if top_matches[0][1] > 0.88:
        return top_matches[0][0]["response"], []

    # Return partial matches as context for LLM
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

        answer = respond(user_input)

        if answer:
            print("AI:", answer)
        else:
            print("AI: I don't know the answer.")
            new_answer = input("What should I answer? ")

            add_knowledge(user_input, new_answer)


if __name__ == "__main__":
    main()