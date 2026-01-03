import requests
import json
import time

# Production Details
WEB_API_KEY = "AIzaSyARwa2-gSUmn-3pZDs72omTrPrmUQyie3k"
PROD_URL = "https://us-central1-swiss-knife-c662b.cloudfunctions.net/generate_podcast_adhoc"

def get_prod_id_token(email="test_commute@example.com", password="password123"):
    """Exchanges email/password for a Firebase ID Token via REST API."""
    # Try sign-in first
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        return response.json().get("idToken")
    
    # If sign-in fails, try sign-up
    print("Sign-in failed, attempting sign-up...")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={WEB_API_KEY}"
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        return response.json().get("idToken")
    else:
        print(f"Error: {response.text}")
        return None

def test_prod_generate_podcast():
    token = get_prod_id_token()
    if not token:
        print("Failed to get ID token. Testing aborted.")
        return

    print("Successfully obtained ID token.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "duration_mins": 2,
        "topics": ["Technology", "Space"],
        "voice_provider": "gemini"
    }
    
    print(f"Calling production API: {PROD_URL}...")
    try:
        response = requests.post(PROD_URL, json=data, headers=headers, timeout=150)
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error calling production API: {e}")

if __name__ == "__main__":
    test_prod_generate_podcast()
