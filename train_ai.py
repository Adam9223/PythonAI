from datasets import load_dataset
import json
import random

# Load the dataset
print("Loading dataset from Hugging Face...")
dataset = load_dataset("Roman1111111/gemini-3-pro-10000x-hard-high-reasoning", split="train")

print(f"Dataset loaded: {len(dataset)} rows")

# Load existing knowledge
with open("knowledge.json", "r") as f:
    knowledge_data = json.load(f)

existing_count = len(knowledge_data["knowledge"])
print(f"Existing knowledge entries: {existing_count}")

# Extract Q&A pairs - take a sample for lightweight training
# For dev-interns, we'll use 100 samples to keep it light
sample_size = 100
sample_indices = random.sample(range(len(dataset)), min(sample_size, len(dataset)))

print(f"\nExtracting {len(sample_indices)} training pairs...")

new_entries = []
for idx in sample_indices:
    item = dataset[idx]
    
    # Extract question from original_data
    question = item['original_data']['text'].strip()
    
    # Extract answer from model_response
    answer = item['model_response'].strip()
    
    # Truncate very long responses for lightweight model
    if len(answer) > 500:
        # Take first 500 chars and add continuation indicator
        answer = answer[:497] + "..."
    
    # Create knowledge entry
    entry = {
        "pattern": question[:200],  # Limit question length too
        "response": answer
    }
    
    new_entries.append(entry)

# Add new entries to knowledge
knowledge_data["knowledge"].extend(new_entries)

# Save updated knowledge
with open("knowledge.json", "w") as f:
    json.dump(knowledge_data, f, indent=2)

print(f"\n✓ Training complete!")
print(f"  Previous entries: {existing_count}")
print(f"  New entries: {len(new_entries)}")
print(f"  Total entries: {len(knowledge_data['knowledge'])}")
print(f"\nKnowledge base saved to knowledge.json")
