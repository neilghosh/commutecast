import os
import sys
import datetime
import argparse
from pathlib import Path

# Add functions directory to path so we can import engine
sys.path.append(str(Path(__file__).parent / "functions"))

from engine import PodcastEngine

def generate_local_podcast(api_key, topics, duration_mins, output_name, generate_audio=False, format="m4a"):
    print(f"--- CommuteCast Local Generator ---")
    print(f"Topics: {topics}")
    print(f"Duration Target: {duration_mins} mins")
    
    engine = PodcastEngine(api_key=api_key)
    
    # 1. Generate Transcript using centralized shared engine logic
    print(f"\n[1/2] Generating Transcript...")
    transcript = engine.generate_transcript(topics, duration_mins)

    os.makedirs("test_outputs", exist_ok=True)
    base_path = os.path.join("test_outputs", output_name)
    transcript_file = f"{base_path}.txt"
    # Pure dialogue cleanup
    lines = transcript.split('\n')
    cleaned = []
    for l in lines:
        l = l.strip().replace('**', '')
        if l.startswith(("John:", "Rebecca:", "TITLE:")):
            cleaned.append(l)
    
    final_transcript = "\n".join(cleaned)
    with open(transcript_file, "w") as f:
        f.write(final_transcript)
    
    word_count = len(final_transcript.split())
    est_mins = word_count / 160
    print(f"✓ Transcript saved to {transcript_file}")
    print(f"   - Real word count: {word_count}")
    print(f"   - Estimated duration: {est_mins:.1f} minutes")

    if not generate_audio:
        print(f"\n[!] Audio generation skipped. Run with --audio to generate.")
        return

    print(f"\n[2/2] Generating Audio ({format.upper()})...")
    try:
        provider = engine.get_provider("gemini")
        audio_bytes = provider.synthesize(final_transcript)
        wav_io = engine.save_to_wav(audio_bytes)
        
        temp_wav = f"{base_path}_temp.wav"
        with open(temp_wav, "wb") as f:
            f.write(wav_io.getbuffer())
        
        final_audio_file = f"{base_path}.{format}"
        success = engine.optimize_audio(temp_wav, final_audio_file)
        
        if success:
            os.remove(temp_wav) # Clean up large WAV
            print(f"✓ Optimized audio saved to {final_audio_file}")
        else:
            print(f"✓ Original WAV kept as {temp_wav}")
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        return

    print(f"\nSuccess! Process complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a CommuteCast podcast locally.")
    parser.add_argument("--api_key", help="Gemini API Key")
    parser.add_argument("--topics", nargs="+", default=["Technology", "Global Economy", "Space Exploration"], help="List of topics")
    parser.add_argument("--duration", type=int, default=5, help="Target duration in minutes")
    parser.add_argument("--output", default="podcast_test", help="Base name for output files")
    parser.add_argument("--audio", action="store_true", help="Generate audio after transcript")
    parser.add_argument("--format", default="m4a", choices=["m4a", "mp3", "wav"], help="Audio format (m4a, mp3, wav)")
    
    args = parser.parse_args()
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No API key provided.")
        sys.exit(1)
        
    generate_local_podcast(api_key, args.topics, args.duration, args.output, generate_audio=args.audio, format=args.format)
