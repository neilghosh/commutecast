from google import genai
import os

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Listing models...")
for model in client.models.list():
    # Print name and whatever else looks interesting
    print(f"Name: {model.name}")
    # print(model) # Let's see the full object if it's small/readable
