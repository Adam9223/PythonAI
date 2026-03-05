#!/usr/bin/env python3
"""
Simple API wrapper for the AI chatbot.
Can be called from Node.js or used standalone.
"""

import sys
import json
import os
from io import StringIO

# Suppress stdout during imports
old_stdout = sys.stdout
sys.stdout = StringIO()

try:
    from main import respond
finally:
    sys.stdout = old_stdout

def main():
    if len(sys.argv) > 1:
        # Called with message argument from Node.js
        user_message = ' '.join(sys.argv[1:])
        output_json = True
    else:
        # Interactive mode
        user_message = input("You: ")
        output_json = False
    
    # Get response from the chatbot
    response = respond(user_message)
    
    if response:
        result = response
    else:
        result = "I don't know how to answer that. Feel free to teach me!"
    
    if output_json:
        # Output as JSON for Node.js parsing
        print(json.dumps({"success": True, "response": result}))
    else:
        # Interactive mode output
        print(result)

if __name__ == "__main__":
    main()
