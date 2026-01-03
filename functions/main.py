from firebase_functions import https_fn, scheduler_fn, pubsub_fn
from google.cloud import pubsub_v1
from firebase_admin import firestore, initialize_app, storage
import os
import datetime
import json
import base64

# Top-level imports for flat layout
from auth import authenticated, admin_only
from engine import PodcastEngine
from storage_utils import upload_podcast_artifacts, get_signed_url, regenerate_rss_feed

# Initialize Firebase Admin
try:
    initialize_app()
except ValueError:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

PROJECT_ID = os.environ.get("GCLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "swiss-knife-c662b"
TOPIC_ID = "generate-podcast"

@https_fn.on_request(timeout_sec=60, memory=256)
@authenticated
def generate_podcast_adhoc(req: https_fn.Request) -> https_fn.Response:
    """HTTP endpoint for ad-hoc podcast generation."""
    # Set CORS headers for the preflight request
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*"}

    if req.method != "POST":
        return https_fn.Response("Method Not Allowed", status=405, headers=headers)
    
    try:
        data = req.get_json()
        duration_mins = data.get("duration_mins", 5)
        topics = data.get("topics", ["Technology", "Space", "Sports"])
        provider_type = data.get("voice_provider", "gemini")
        uid = req.auth["uid"]
        user_name = req.auth.get("name", "User")  # Get name from auth token
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Publish message to Pub/Sub
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
        
        message_json = json.dumps({
            "uid": uid,
            "user_name": user_name,
            "timestamp": timestamp,
            "duration_mins": duration_mins,
            "topics": topics,
            "provider_type": provider_type
        })
        
        publisher.publish(topic_path, message_json.encode("utf-8"))

        # Calculate RSS feed URL
        bucket_name = storage.bucket().name
        rss_url = f"https://storage.googleapis.com/{bucket_name}/users/{uid}/rss.xml"
        
        return https_fn.Response(
            json.dumps({
                "status": "queued", 
                "job_id": timestamp,
                "rss_url": rss_url,
                "message": "Podcast generation started. Subscribe to your RSS feed to get updates!"
            }),
            status=202,
            mimetype="application/json",
            headers=headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, mimetype="application/json", headers=headers)

@pubsub_fn.on_message_published(topic=TOPIC_ID, timeout_sec=540, memory=1024, secrets=["GEMINI_API_KEY"])
def generate_podcast_worker(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]) -> None:
    """Background worker to generate podcast."""
    message_data = base64.b64decode(event.data.message.data).decode('utf-8')
    data = json.loads(message_data)
    
    uid = data["uid"]
    user_name = data.get("user_name", "User")
    timestamp = data["timestamp"]
    duration_mins = data["duration_mins"]
    topics = data["topics"]
    provider_type = data["provider_type"]

    print(f"Starting podcast generation for user {uid}, topics: {topics}")

    try:
        engine = PodcastEngine(api_key=GEMINI_API_KEY)
 
        # 1. Generate Transcript
        transcript = engine.generate_transcript(topics, duration_mins)
        print(f"Generated transcript for {uid}")
        
        # 2. Generate Audio
        provider = engine.get_provider(provider_type)
        audio_blob = provider.synthesize(transcript)
        wav_io = engine.save_to_wav(audio_blob)
        
        # 3. Optimize Audio (WAV -> M4A)
        import io
        temp_wav = f"/tmp/{uid}_{timestamp}.wav"
        temp_m4a = f"/tmp/{uid}_{timestamp}.m4a"
        
        with open(temp_wav, "wb") as f:
            f.write(wav_io.getbuffer())
        
        success = engine.optimize_audio(temp_wav, temp_m4a)
        
        if success:
            with open(temp_m4a, "rb") as f:
                final_audio_io = io.BytesIO(f.read())
            extension = "m4a"
            # Cleanup
            if os.path.exists(temp_m4a): os.remove(temp_m4a)
        else:
            final_audio_io = wav_io
            extension = "wav"
            
        if os.path.exists(temp_wav): os.remove(temp_wav)

        # 4. Store and update RSS
        paths = upload_podcast_artifacts(uid, user_name, timestamp, transcript, final_audio_io, topics, ext=extension)
        
        print(f"Completed podcast generation for {uid}")
        print(f"RSS feed available at: {paths['rss_url']}")

    except Exception as e:
        print(f"Error generating podcast: {e}")

@https_fn.on_request(secrets=["GEMINI_API_KEY"])
@admin_only
def update_schedule(req: https_fn.Request) -> https_fn.Response:
    # Set CORS headers for the preflight request
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*"}

    if req.method != "POST":
        return https_fn.Response("Method Not Allowed", status=405, headers=headers)

    try:
        data = req.get_json()
        db = firestore.client()
        uid = req.auth["uid"]
        db.collection("configs").document(uid).set(data, merge=True)
        return https_fn.Response(json.dumps({"status": "updated"}), status=200, mimetype="application/json", headers=headers)
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, mimetype="application/json", headers=headers)

@scheduler_fn.on_schedule(schedule="every day 08:00", secrets=["GEMINI_API_KEY"])
def generate_podcast_scheduled(event: scheduler_fn.ScheduledEvent) -> None:
    """Enqueue podcast generation for all enabled users (same path as ad-hoc)."""
    db = firestore.client()
    configs_ref = db.collection("configs").stream()

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    for config_doc in configs_ref:
        config = config_doc.to_dict()
        if not config.get("enabled", False):
            continue

        uid = config_doc.id
        user_name = config.get("user_name", "User")
        topics = config.get("topics", ["general news"])
        duration_mins = config.get("duration_mins", 5)
        provider_type = config.get("provider_type", "gemini")

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            message_json = json.dumps({
                "uid": uid,
                "user_name": user_name,
                "timestamp": timestamp,
                "duration_mins": duration_mins,
                "topics": topics,
                "provider_type": provider_type,
            })

            publisher.publish(topic_path, message_json.encode("utf-8"))
            print(f"Scheduled enqueue for {uid} at {timestamp} topics={topics}")

        except Exception as e:
            print(f"Error enqueuing scheduled podcast for {uid}: {e}")

@https_fn.on_request()
@authenticated 
def regenerate_rss(req: https_fn.Request) -> https_fn.Response:
    """Manually regenerate RSS feed from existing episodes."""
    # Set CORS headers for the preflight request
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    headers = {"Access-Control-Allow-Origin": "*"}
    
    if req.method != "POST":
        return https_fn.Response(json.dumps({"error": "Method not allowed"}), status=405, mimetype="application/json", headers=headers)

    try:
        # Get user info
        uid = req.headers.get("X-UID")
        
        # Get user name from request body or use default
        data = req.get_json(silent=True) or {}
        user_name = data.get("user_name", "User")
        
        # Regenerate RSS feed
        rss_url = regenerate_rss_feed(uid, user_name)
        
        if rss_url:
            return https_fn.Response(
                json.dumps({"success": True, "rss_url": rss_url}),
                status=200,
                mimetype="application/json",
                headers=headers
            )
        else:
            return https_fn.Response(
                json.dumps({"error": "No episodes found"}),
                status=404,
                mimetype="application/json",
                headers=headers
            )
            
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype="application/json",
            headers=headers
        )
