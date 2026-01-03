import os
from firebase_admin import storage
import datetime
import io
from xml.etree import ElementTree as ET


def _parse_transcript_title_and_snippet(transcript_text: str):
    """Extracts a SUMMARY or TITLE line by searching lines, skipping leading filler."""
    lines = transcript_text.splitlines()
    title = None
    body_lines = []
    found_title = False

    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
            
        # If we haven't found a title yet, check if this line is one
        if not found_title:
            lower_line = clean_line.lower()
            if lower_line.startswith("summary:") or lower_line.startswith("title:"):
                title = clean_line.split(":", 1)[1].strip()
                found_title = True
                continue
            # If it's not a title line and not dialogue, it might be filler. 
            # We don't add to body until we see dialogue or have passed the title.
            if clean_line.startswith(("John:", "Rebecca:")):
                body_lines.append(clean_line)
                found_title = True # Stop looking for title if we hit dialogue first
        else:
            # Once title is handled, everything else is body
            body_lines.append(clean_line)

    body = "\n".join(body_lines).strip()
    snippet = body[:200] + "..." if len(body) > 200 else body
    return title, snippet


def _episode_title_from_description(description: str, timestamp: str, provided_title: str = None) -> str:
    """Prioritize the provided summary/title; fallback to deriving from snippet."""
    if provided_title:
        # Some cleanup if the model still included the label
        clean_title = provided_title.replace("SUMMARY:", "").replace("TITLE:", "").strip()
        trimmed = clean_title[:120].rstrip()
        if trimmed:
            return trimmed

    if description:
        first_line = description.strip().split('\n', 1)[0].strip()
        if first_line:
            trimmed = first_line[:120].rstrip()
            return trimmed if trimmed else f"News Podcast - {timestamp}"
        
    return f"News Podcast - {timestamp}"

def upload_podcast_artifacts(uid: str, user_name: str, timestamp: str, transcript: str, audio_io: io.BytesIO, topics: list = None, ext: str = "m4a"):
    """
    Uploads transcript and audio to user folders with public access.
    Updates RSS feed automatically.
    Path: users/{uid}/podcasts/{timestamp}/
    """
    bucket = storage.bucket()
    base_path = f"users/{uid}/podcasts/{timestamp}"
    
    # Upload Transcript
    transcript_blob = bucket.blob(f"{base_path}/transcript.txt")
    transcript_blob.upload_from_string(transcript, content_type="text/plain")
    transcript_blob.make_public()
    
    # Upload Audio
    audio_filename = f"podcast.{ext.strip('.')}"
    content_type = f"audio/{ext.strip('.')}"
    if ext.strip('.') == "m4a":
        content_type = "audio/x-m4a"
        
    audio_blob = bucket.blob(f"{base_path}/{audio_filename}")
    audio_blob.upload_from_file(audio_io, content_type=content_type)
    audio_blob.make_public()
    
    # Get file size for RSS
    audio_blob.reload()  # Refresh metadata
    audio_size = audio_blob.size
    
    # Update RSS feed
    rss_url = update_rss_feed(uid, user_name, timestamp, audio_blob.public_url, transcript[:200], topics or [], audio_size)
    
    return {
        "transcript_path": transcript_blob.name,
        "audio_path": audio_blob.name,
        "audio_url": audio_blob.public_url,
        "transcript_url": transcript_blob.public_url,
        "rss_url": rss_url
    }

def update_rss_feed(uid: str, user_name: str, timestamp: str, audio_url: str, description: str, topics: list, audio_size: int):
    """Rebuilds RSS feed from storage on each publish to avoid drift."""
    bucket = storage.bucket()
    rss_path = f"users/{uid}/rss.xml"
    rss_blob = bucket.blob(rss_path)

    print(f"Updating RSS feed for user {uid}, episode timestamp: {timestamp}")

    # Collect all episodes directly from storage to ensure correctness
    podcast_prefix = f"users/{uid}/podcasts/"
    blobs = bucket.list_blobs(prefix=podcast_prefix)

    episodes = {}
    for blob in blobs:
        # Match any audio file (m4a, mp3, wav)
        if not any(blob.name.endswith(ext) for ext in ['.m4a', '.mp3', '.wav']):
            continue
            
        ext = os.path.splitext(blob.name)[1].strip('.')
        ep_timestamp = blob.name.split('/')[-2]
        blob.reload()

        # Try to read matching transcript for description
        transcript_path = os.path.join(os.path.dirname(blob.name), 'transcript.txt')
        transcript_blob = bucket.blob(transcript_path)
        ep_description = description  # fallback to current description snippet
        ep_title = None
        try:
            if transcript_blob.exists():
                transcript_text = transcript_blob.download_as_text()
                ep_title, ep_description = _parse_transcript_title_and_snippet(transcript_text)
        except Exception as e:
            print(f"Warning: transcript read failed for {transcript_path}: {e}")

        episodes[ep_timestamp] = {
            "audio_url": blob.public_url,
            "audio_size": blob.size,
            "description": ep_description,
            "title": ep_title,
            "ext": ext
        }

    if not episodes:
        print(f"No episodes found for user {uid}; skipping RSS update")
        return None

    # Sort timestamps descending
    sorted_timestamps = sorted(episodes.keys(), reverse=True)

    rss_content = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        f'<title>{user_name}\'s News Podcast</title>',
        f'<description>AI-generated news podcasts for {user_name}</description>',
        '<language>en-us</language>'
    ]

    # Add up to 50 most recent episodes
    for ts in sorted_timestamps[:50]:
        episode = episodes[ts]
        try:
            dt = datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S")
            pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        except Exception:
            pub_date = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')

        # Escape XML entities in description
        safe_desc = episode["description"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        item_title = _episode_title_from_description(episode["description"], ts, episode.get("title"))
        print(f"   - Episode {ts} Title: {item_title}")
        safe_title = item_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Determine correct MIME type
        audio_ext = episode.get("ext", "m4a")
        mime_type = f"audio/{audio_ext}"
        if audio_ext == "m4a":
            mime_type = "audio/x-m4a"

        rss_content.extend([
            '<item>',
            f'<title>{safe_title}</title>',
            f'<description>{safe_desc}</description>',
            f'<pubDate>{pub_date}</pubDate>',
            f'<guid>{episode["audio_url"]}</guid>',
            f'<enclosure url="{episode["audio_url"]}" type="{mime_type}" length="{episode["audio_size"]}" />',
            '</item>'
        ])

    rss_content.extend(['</channel>', '</rss>'])

    final_xml = '\n'.join(rss_content)

    # Set no-cache to avoid stale RSS in clients/CDN
    rss_blob.cache_control = "no-cache, max-age=0"
    rss_blob.upload_from_string(final_xml, content_type='application/rss+xml')
    rss_blob.patch()
    rss_blob.make_public()

    print(f"RSS feed updated successfully. Total episodes: {min(len(sorted_timestamps), 50)}")

    return rss_blob.public_url

def regenerate_rss_feed(uid: str, user_name: str = None):
    """Regenerates RSS feed from all existing episodes in storage."""
    bucket = storage.bucket()
    
    # Get user's podcast folder
    podcast_prefix = f"users/{uid}/podcasts/"
    blobs = bucket.list_blobs(prefix=podcast_prefix)
    
    episodes = {}
    # Collect all audio files and their metadata
    for blob in blobs:
        # Match any audio file (m4a, mp3, wav)
        if not any(blob.name.endswith(ext) for ext in ['.m4a', '.mp3', '.wav']):
            continue

        ext = os.path.splitext(blob.name)[1].strip('.')
        timestamp = blob.name.split('/')[-2]  # Extract timestamp from path
        blob.reload()  # Get metadata including size
        
        # Try to get transcript for description
        transcript_path = os.path.join(os.path.dirname(blob.name), 'transcript.txt')
        transcript_blob = bucket.blob(transcript_path)
        description = "AI-generated news podcast"
        title = None
        try:
            if transcript_blob.exists():
                transcript = transcript_blob.download_as_text()
                title, description = _parse_transcript_title_and_snippet(transcript)
        except Exception as e:
            print(f"Warning: transcript read failed for {transcript_path}: {e}")
            
        episodes[timestamp] = {
            'audio_url': blob.public_url,
            'audio_size': blob.size,
            'description': description,
            'title': title,
            'ext': ext
        }
    
    if not episodes:
        print(f"No episodes found for user {uid}")
        return None
        
    # Sort episodes by timestamp (newest first)
    sorted_timestamps = sorted(episodes.keys(), reverse=True)
    
    # Create RSS feed with proper XML structure
    rss_content = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        f'<title>{user_name or "User"}\'s News Podcast</title>',
        f'<description>AI-generated news podcasts for {user_name or "User"}</description>',
        '<language>en-us</language>'
    ]
    
    # Add episodes (limit to 50 most recent)
    for timestamp in sorted_timestamps[:50]:
        episode = episodes[timestamp]
        
        # Parse timestamp for pubDate
        try:
            dt = datetime.datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
            pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        except:
            pub_date = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Escape XML entities in description
        description = episode['description'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        item_title = _episode_title_from_description(episode['description'], timestamp, episode.get('title'))
        safe_title = item_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Determine correct MIME type
        audio_ext = episode.get("ext", "m4a")
        mime_type = f"audio/{audio_ext}"
        if audio_ext == "m4a":
            mime_type = "audio/x-m4a"

        rss_content.extend([
            '<item>',
            f'<title>{safe_title}</title>',
            f'<description>{description}</description>',
            f'<pubDate>{pub_date}</pubDate>',
            f'<guid>{episode["audio_url"]}</guid>',
            f'<enclosure url="{episode["audio_url"]}" type="{mime_type}" length="{episode["audio_size"]}" />',
            '</item>'
        ])
    
    rss_content.extend([
        '</channel>',
        '</rss>'
    ])
    
    # Join with newlines for proper formatting
    final_xml = '\n'.join(rss_content)
    
    # Upload RSS feed with no-cache headers
    rss_path = f"users/{uid}/rss.xml"
    rss_blob = bucket.blob(rss_path)
    rss_blob.cache_control = "no-cache, max-age=0"
    rss_blob.upload_from_string(final_xml, content_type='application/rss+xml')
    rss_blob.patch()
    rss_blob.make_public()
    
    print(f"Regenerated RSS feed for user {uid} with {len(sorted_timestamps)} episodes")
    return rss_blob.public_url

def get_signed_url(blob_path: str, expires_in_minutes: int = 60):
    """Generates a public URL for a blob."""
    bucket = storage.bucket()
    blob = bucket.blob(blob_path)
    return blob.public_url if blob.exists() else f"https://storage.googleapis.com/{bucket.name}/{blob_path}"
