import requests
import os

# Your Firebase Web API Key (Found in Firebase Project Settings)
# Only needed for direct REST API testing. 
# Normally this is handled by the Firebase SDK in your app.
API_KEY = "dummy-key" # User will need to replace this if using this script for prod

def get_id_token(email, password):
    """Exchanges email/password for a Firebase ID Token via REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("idToken")
    else:
        print(f"Error: {response.text}")
        return None

if __name__ == "__main__":
    print("This script is a template. For production, the Firebase Client SDK is recommended.")
    # Example usage:
    # token = get_id_token("test@example.com", "password123")
    # print(f"ID Token: {token}")
