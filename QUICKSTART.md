# Quick Start Guide - CommuteCast API

## Method 1: Using the Test Script (Easiest)

The simplest way is to use the provided test script:

```bash
cd /Users/neilghosh/dev/commutecast
source functions/venv/bin/activate
python3 tests/test_prod.py
```

This script will:
1. Create/sign in a test user (`test_commute@example.com`)
2. Get a Firebase ID token automatically
3. Call the production API
4. Display the response with audio and transcript URLs

## Method 2: Manual API Call (Step-by-Step)

### Step 1: Get a Firebase ID Token

**Option A - Using Python:**
```python
import requests

WEB_API_KEY = "AIzaSyARwa2-gSUmn-3pZDs72omTrPrmUQyie3k"
email = "your-email@example.com"
password = "your-password"

# Sign in
url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
response = requests.post(url, json={
    "email": email,
    "password": password,
    "returnSecureToken": True
})

id_token = response.json()["idToken"]
print(f"Your ID Token: {id_token}")
```

**Option B - Using curl:**
```bash
curl -X POST \
  "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyARwa2-gSUmn-3pZDs72omTrPrmUQyie3k" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-email@example.com",
    "password": "your-password",
    "returnSecureToken": true
  }'
```

### Step 2: Call the API

**Using Python:**
```python
import requests
import json

# Use the token from Step 1
id_token = "YOUR_ID_TOKEN_HERE"

headers = {
    "Authorization": f"Bearer {id_token}",
    "Content-Type": "application/json"
}

data = {
    "duration_mins": 2,
    "topics": ["Technology", "Space", "Cricket"],
    "voice_provider": "gemini"
}

response = requests.post(
    "https://us-central1-swiss-knife-c662b.cloudfunctions.net/generate_podcast_adhoc",
    json=data,
    headers=headers,
    timeout=150
)

print(f"Status: {response.status_code}")
print(json.dumps(response.json(), indent=2))
```

**Using curl:**
```bash
curl -X POST \
  "https://us-central1-swiss-knife-c662b.cloudfunctions.net/generate_podcast_adhoc" \
  -H "Authorization: Bearer YOUR_ID_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "duration_mins": 2,
    "topics": ["Technology", "Space", "Cricket"],
    "voice_provider": "gemini"
  }'
```

## Method 3: From a Web App

If you're building a web frontend:

```javascript
// 1. Sign in with Firebase
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";

const auth = getAuth();
const userCredential = await signInWithEmailAndPassword(
  auth, 
  "email@example.com", 
  "password"
);

// 2. Get the ID token
const idToken = await userCredential.user.getIdToken();

// 3. Call the API
const response = await fetch(
  "https://us-central1-swiss-knife-c662b.cloudfunctions.net/generate_podcast_adhoc",
  {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${idToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      duration_mins: 2,
      topics: ["Technology", "Space", "Cricket"],
      voice_provider: "gemini"
    })
  }
);

const result = await response.json();
console.log(result);
// Access files: result.audio_url, result.transcript_url
```

## Expected Response

```json
{
  "status": "success",
  "audio_url": "https://storage.cloud.google.com/.../podcast.wav",
  "transcript_url": "https://storage.cloud.google.com/.../transcript.txt"
}
```

## Troubleshooting

- **401 Unauthorized**: Your ID token is invalid or expired. Get a new one.
- **403 Forbidden**: Your user doesn't have permission. Check Firebase Auth rules.
- **500 Error**: Check the Cloud Function logs in Firebase Console.
- **Timeout**: Podcast generation can take 30-60 seconds. Increase your timeout.

## Creating New Users

To create a new user account:

```bash
curl -X POST \
  "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyARwa2-gSUmn-3pZDs72omTrPrmUQyie3k" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepassword123",
    "returnSecureToken": true
  }'
```
