import os
import contextlib
import wave
import io
import datetime
from google import genai
from google.genai import types
from abc import ABC, abstractmethod

class VoiceProvider(ABC):
    @abstractmethod
    def synthesize(self, transcript: str) -> bytes:
        pass

class GeminiVoiceProvider(VoiceProvider):
    def __init__(self, client: genai.Client, model_id: str = "gemini-2.5-flash-preview-tts"):
        self.client = client
        self.model_id = model_id

    def synthesize(self, transcript: str) -> bytes:
        # Clean transcript: keep only lines starting with "John: " or "Rebecca: "
        # This prevents the "Model tried to generate text" error caused by headers or metadata.
        lines = transcript.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # Remove markdown bolding if present
            line = line.replace('**', '')
            if line.startswith(("John:", "Rebecca:")):
                cleaned_lines.append(line)
        
        if not cleaned_lines:
             # Fallback: if cleaning failed or model outputted weird format, try original but stripped
             cleaned_lines = [transcript.strip()]

        # Split into chunks of ~1000 words (approx 6-7 mins of audio)
        # to avoid Gemini API timeouts or length limits.
        chunks = []
        current_chunk = []
        current_word_count = 0
        word_limit = 1000 

        for line in cleaned_lines:
            words = line.split()
            if current_word_count + len(words) > word_limit and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_word_count = len(words)
            else:
                current_chunk.append(line)
                current_word_count += len(words)
        
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        all_audio_bytes = bytearray()
        
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker='John',
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Schedar',  # Male voice
                                )
                            )
                        ),
                        types.SpeakerVoiceConfig(
                            speaker='Rebecca',
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Sulafat',  # Female voice
                                )
                            )
                        ),
                    ]
                )
            )
        )

        print(f"OBSERVABILITY: Starting chunked audio synthesis in {len(chunks)} chunks...")
        import time
        start_audio = time.time()
        
        for i, chunk_text in enumerate(chunks):
            t_chunk = time.time()
            print(f"   - Synthesizing chunk {i+1}/{len(chunks)}...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=chunk_text,
                config=config,
            )
            all_audio_bytes.extend(response.candidates[0].content.parts[0].inline_data.data)
            print(f"   - Chunk {i+1} took {time.time() - t_chunk:.2f}s")
        
        print(f"OBSERVABILITY: Total audio synthesis took {time.time() - start_audio:.2f}s")
        return bytes(all_audio_bytes)

class PodcastEngine:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.transcript_model = "gemini-2.0-flash"

    def get_provider(self, provider_type: str = "gemini") -> VoiceProvider:
        if provider_type == "gemini":
            return GeminiVoiceProvider(self.client)
        raise ValueError(f"Unknown provider type: {provider_type}")

    def generate_transcript(self, topics: list, duration_mins: int) -> str:
        """Generates a transcript, switching to time-chunked mode for long durations."""
        import time
        start_total = time.time()
        
        if duration_mins <= 10:
            print(f"OBSERVABILITY: Starting single-shot transcript generation for {duration_mins} mins...")
            prompt = self.create_prompt(topics, duration_mins)
            result = self._call_genai(prompt)
            print(f"OBSERVABILITY: Single-shot transcript took {time.time() - start_total:.2f}s")
            return result
        
        print(f"OBSERVABILITY: Starting time-chunked transcript generation for {duration_mins} mins...")
        words_per_minute = 160
        chunk_duration = 5
        num_chunks = max(1, int(duration_mins / chunk_duration))
        
        now = datetime.datetime.now()
        today_date = now.strftime("%A, %B %d, %Y")
        segments = []
        
        # 1. Generate Title and Intro
        t0 = time.time()
        intro_prompt = f"""
        Today is {today_date}. Write the TITLE and a 2-minute INTRO dialogue for 'CommuteCast'.
        Topics to cover: {', '.join(topics)}.
        CRITICAL: Treat these topics as INDEPENDENT news segments. Do NOT merge them (e.g. if topics are Hyderabad and Cricket, intro them as two separate stories).
        Start with TITLE: and respond ONLY with John:/Rebecca: dialogue.
        """
        segments.append(self._call_genai(intro_prompt))
        print(f"   - Intro segment took {time.time() - t0:.2f}s")
        
        # 2. Generate Content Chunks
        for i in range(num_chunks):
            topic_index = i % len(topics)
            current_topic = topics[topic_index]
            t_chunk = time.time()
            
            chunk_prompt = f"""
            Today's Date: {today_date}. This is Part {i+1} of {num_chunks} for a 30-minute 'CommuteCast' episode.
            Current Topic: {current_topic}
            
            STRICT INSTRUCTIONS:
            1. TOPIC INDEPENDENCE: Focus EXCLUSIVELY on {current_topic}. Do NOT limit it to how it relates to other topics in the list.
            2. FACTS ONLY: Use Google Search to find REAL news stories from the last 24 hours regarding {current_topic}.
            3. NO OPINION: Focus on what actually happened.
            4. DEPTH: Provide a detailed 5-minute deep-dive conversation (~800 words). 
            5. FORMAT: Respond ONLY with John:/Rebecca: dialogue.
            """
            segments.append(self._call_genai(chunk_prompt))
            print(f"   - Chunk {i+1}/{num_chunks} ({current_topic}) took {time.time() - t_chunk:.2f}s")
            
        # 3. Generate Outro
        t_outro = time.time()
        outro_prompt = f"Today is {today_date}. Write a final 1-minute wrap-up for 'CommuteCast' for: {', '.join(topics)}. Respond ONLY with John:/Rebecca: dialogue."
        segments.append(self._call_genai(outro_prompt))
        print(f"   - Outro segment took {time.time() - t_outro:.2f}s")
        
        print(f"OBSERVABILITY: Total transcript generation took {time.time() - start_total:.2f}s")
        
        # Final cleanup
        full_text = "\n\n".join(segments)
        cleaned_lines = []
        for line in full_text.split('\n'):
            line = line.strip().replace('**', '')
            if line.startswith(("John:", "Rebecca:", "TITLE:")):
                cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)

    def _call_genai(self, prompt: str) -> str:
        """Internal helper to call Gemini API."""
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        generate_content_config = types.GenerateContentConfig(
            tools=[grounding_tool],
            max_output_tokens=8192,
            temperature=0.7
        )

        response = self.client.models.generate_content(
            model=self.transcript_model,
            contents=prompt,
            config=generate_content_config
        )
        return response.text

    def create_prompt(self, topics: list, duration_mins: int) -> str:
        """Centralized prompt generation logic for single-shot mode."""
        words_per_minute = 160
        target_words = int(duration_mins * words_per_minute)
        now = datetime.datetime.now()
        today_date = now.strftime("%A, %B %d, %Y")
        
        return f"""
        Today: {today_date}. You are producing 'CommuteCast' (target {target_words} words).
        Topics: {', '.join(topics)}
        
        RULES:
        1. TOPIC INDEPENDENCE: Treat each topic as a distinct news segment. Do NOT merge them or limit one to the context of another.
        2. Respond ONLY with John:/Rebecca: dialogue. 
        3. First line: TITLE: <headline>
        4. Freshness: Use Google Search for the last 24 hours.
        5. Depth: Provide detailed analysis to hit the {duration_mins} minute target.
        """

    @staticmethod
    def save_to_wav(audio_data: bytes, sample_rate: int = 24000) -> io.BytesIO:
        """Converts raw audio bytes to a WAV file in memory."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        wav_io.seek(0)
        return wav_io

    @staticmethod
    def optimize_audio(input_file: str, output_file: str):
        """
        Converts WAV to an optimized format (M4A/AAC or MP3).
        Uses afconvert (Mac) or ffmpeg (Linux/GCP) if available.
        """
        import subprocess
        import shutil
        import time
        start_opt = time.time()

        ext = os.path.splitext(output_file)[1].lower()
        print(f"OBSERVABILITY: Starting optimization of {input_file} to {output_file}...")

        # 1. Try Mac's afconvert (Fast & Built-in)
        if shutil.which("afconvert"):
            # M4A (AAC) is very efficient
            if ext == ".m4a":
                cmd = ["afconvert", "-f", "m4af", "-d", "aac ", "-b", "64000", input_file, output_file]
            elif ext == ".mp3":
                cmd = ["afconvert", "-f", ".mp3", "-d", "mp3 ", "-b", "64000", input_file, output_file]
            else:
                # Default fallback
                cmd = ["afconvert", "-f", "m4af", "-d", "aac ", "-b", "64000", input_file, output_file]
            
            try:
                subprocess.run(cmd, check=True)
                print(f"OBSERVABILITY: Optimization took {time.time() - start_opt:.2f}s")
                print(f"✓ Optimized using afconvert ({ext})")
                return True
            except subprocess.CalledProcessError as e:
                print(f"Warning: afconvert failed: {e}")

        # 2. Try FFmpeg (Common on Linux/GCP)
        if shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-i", input_file, "-b:a", "64k", "-y", output_file]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                print(f"OBSERVABILITY: Optimization took {time.time() - start_opt:.2f}s")
                print(f"✓ Optimized using ffmpeg ({ext})")
                return True
            except subprocess.CalledProcessError as e:
                print(f"Warning: ffmpeg failed: {e}")

        print("Error: No audio optimization utility found (afconvert or ffmpeg). Keeping original WAV.")
        return False
