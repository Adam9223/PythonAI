import json
import os
import re
from difflib import SequenceMatcher
from langchain_ollama import OllamaLLM

FILE_NAME = "knowledge.json"

# Load Ollama model
model = OllamaLLM(model="llama3:latest")


def normalize_text(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", text.lower())).strip()

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
        return None

    for item in data["knowledge"]:
        if normalize_text(item["pattern"]) == normalized_input:
            return item["response"]

    best_match = None
    highest_score = 0

    for item in data["knowledge"]:
        pattern = normalize_text(item["pattern"])
        score = similar(normalized_input, pattern)

        if score > highest_score:
            highest_score = score
            best_match = item

    if highest_score > 0.88:
        return best_match["response"]

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

def respond(user_input):

     
    math_answer = try_math(user_input)
    if math_answer:
        return math_answer

     
    stored = check_knowledge(user_input)
    if stored:
        return stored

   
    try:
        ai_response = model.invoke(user_input)
        return ai_response.strip()
    except:
        return None


 

def main():
    print("Memory AI Started")
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