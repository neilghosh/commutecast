import os
import contextlib
import wave
import io
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

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=transcript,
            config=config,
        )
        return response.candidates[0].content.parts[0].inline_data.data

class PodcastEngine:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.transcript_model = "gemini-2.0-flash"

    def get_provider(self, provider_type: str = "gemini") -> VoiceProvider:
        if provider_type == "gemini":
            return GeminiVoiceProvider(self.client)
        raise ValueError(f"Unknown provider type: {provider_type}")

    def generate_transcript(self, prompt: str) -> str:
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        generate_content_config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )

        response = self.client.models.generate_content(
            model=self.transcript_model,
            contents=prompt,
            config=generate_content_config
        )
        return response.text

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
