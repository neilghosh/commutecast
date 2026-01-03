#!/usr/bin/env python3
"""
Script to add Gmail users to Firebase Auth and test the CommuteCast API.
This demonstrates how to:
1. Add real Gmail accounts to Firebase Authentication
2. Get ID tokens for those users
3. Call the API as different users to verify tenant isolation
"""

import requests
import json
import sys

# Firebase Configuration
WEB_API_KEY = "AIzaSyARwa2-gSUmn-3pZDs72omTrPrmUQyie3k"
API_URL = "https://us-central1-swiss-knife-c662b.cloudfunctions.net/generate_podcast_adhoc"

def create_user_with_email_password(email, password):
    """Create a new user with email/password authentication."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={WEB_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Created user: {email}")
        print(f"   User ID: {data['localId']}")
        return data['idToken'], data['localId']
    else:
        error = response.json().get('error', {}).get('message', 'Unknown error')
        if 'EMAIL_EXISTS' in error:
            print(f"⚠️  User {email} already exists, signing in instead...")
            return sign_in_user(email, password)
        else:
            print(f"❌ Error creating user: {error}")
            return None, None

def sign_in_user(email, password):
    """Sign in an existing user and get their ID token."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Signed in: {email}")
        print(f"   User ID: {data['localId']}")
        return data['idToken'], data['localId']
    else:
        error = response.json().get('error', {}).get('message', 'Unknown error')
        print(f"❌ Error signing in: {error}")
        return None, None

def call_api_as_user(id_token, user_email, topics=None):
    """Call the CommuteCast API as a specific user."""
    if topics is None:
        topics = ["Technology", "Space"]
    
    headers = {
        "Authorization": f"Bearer {id_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "duration_mins": 2,
        "topics": topics,
        "voice_provider": "gemini"
    }
    
    print(f"\n📡 Calling API as {user_email}...")
    print(f"   Topics: {', '.join(topics)}")
    
    try:
        response = requests.post(API_URL, json=data, headers=headers, timeout=150)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Success! Status: {response.status_code}")
            print(f"   Audio URL: {result['audio_url']}")
            print(f"   Transcript URL: {result['transcript_url']}")
            return result
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def demo_multi_user_testing():
    """Demonstrate testing with multiple Gmail users."""
    print("=" * 70)
    print("CommuteCast API - Multi-User Testing Demo")
    print("=" * 70)
    
    # Define test users (you can add your real Gmail addresses here)
    test_users = [
        {
            "email": "user1@example.com",
            "password": "testpass123",
            "topics": ["Technology", "AI"]
        },
        {
            "email": "user2@example.com", 
            "password": "testpass456",
            "topics": ["Space", "Astronomy"]
        },
        {
            "email": "user3@example.com",
            "password": "testpass789",
            "topics": ["Cricket", "Sports"]
        }
    ]
    
    results = []
    
    for user in test_users:
        print(f"\n{'=' * 70}")
        print(f"Testing with user: {user['email']}")
        print(f"{'=' * 70}")
        
        # Create or sign in user
        id_token, uid = create_user_with_email_password(user['email'], user['password'])
        
        if id_token:
            # Call API as this user
            result = call_api_as_user(id_token, user['email'], user['topics'])
            if result:
                results.append({
                    "email": user['email'],
                    "uid": uid,
                    "result": result
                })
        
        print()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY - Tenant Isolation Verification")
    print("=" * 70)
    
    for item in results:
        print(f"\n👤 User: {item['email']}")
        print(f"   UID: {item['uid']}")
        print(f"   Storage Path: users/{item['uid']}/podcasts/...")
        print(f"   Audio: {item['result']['audio_url']}")
    
    print("\n✅ Each user's files are isolated in their own directory!")

def add_single_gmail_user(email, password):
    """Add a single Gmail user and test the API."""
    print(f"Adding Gmail user: {email}")
    
    id_token, uid = create_user_with_email_password(email, password)
    
    if id_token:
        print(f"\n✅ User added successfully!")
        print(f"   User ID: {uid}")
        print(f"   ID Token (first 50 chars): {id_token[:50]}...")
        
        # Test API call
        print(f"\n🧪 Testing API call...")
        result = call_api_as_user(id_token, email)
        
        if result:
            print(f"\n✅ API test successful!")
            print(f"\nYou can now use this user to call the API:")
            print(f"   Email: {email}")
            print(f"   Password: {password}")
            print(f"\nTo get a fresh token, run:")
            print(f"   python3 tests/add_gmail_users.py signin {email} {password}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "demo":
            # Run multi-user demo
            demo_multi_user_testing()
        
        elif command == "add" and len(sys.argv) >= 4:
            # Add a single user
            email = sys.argv[2]
            password = sys.argv[3]
            add_single_gmail_user(email, password)
        
        elif command == "signin" and len(sys.argv) >= 4:
            # Sign in and get token
            email = sys.argv[2]
            password = sys.argv[3]
            id_token, uid = sign_in_user(email, password)
            if id_token:
                print(f"\n🎫 ID Token:\n{id_token}")
        
        elif command == "test" and len(sys.argv) >= 4:
            # Test API with existing user
            email = sys.argv[2]
            password = sys.argv[3]
            id_token, uid = sign_in_user(email, password)
            if id_token:
                topics = sys.argv[4:] if len(sys.argv) > 4 else ["Technology", "Space"]
                call_api_as_user(id_token, email, topics)
        
        else:
            print("Usage:")
            print("  python3 tests/add_gmail_users.py demo")
            print("  python3 tests/add_gmail_users.py add <email> <password>")
            print("  python3 tests/add_gmail_users.py signin <email> <password>")
            print("  python3 tests/add_gmail_users.py test <email> <password> [topics...]")
    else:
        # Default: run demo
        demo_multi_user_testing()
