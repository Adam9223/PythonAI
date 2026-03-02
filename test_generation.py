#!/usr/bin/env python3
"""Quick test of text generation"""

print("Testing transformer model...")

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    
    model_name = "distilgpt2"
    print(f"Loading {model_name}...")
    
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    print("✓ Model loaded!\n")
    
    # Test generation
    context = "Mathematics is the study of numbers, shapes, and patterns."
    query = "what is mathematics"
    prompt = f"Context: {context}\n\nQuestion: {query}\nAnswer:"
    
    print(f"Prompt: {prompt}\n")
    print("Generating...")
    
    inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=200, truncation=True)
    
    with torch.no_grad():
        outputs = model.generate(
            inputs,
            max_new_tokens=50,
            num_return_sequences=1,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"\nGenerated text:\n{response}\n")
    
    print("✓ Text generation working!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
