"""
MCP TTS Server — Claude Desktop voice bridge
with ElevenLabs Text-to-Speech integration.

Claude sends text here via the 'speak' tool,
and the server reads it aloud through ElevenLabs.
"""

import json
import sys
import os
import io
import tempfile
import threading
import time
from pathlib import Path

# TTS playback queue — only one voice can play at a time
_tts_lock = threading.Lock()

from mcp.server.fastmcp import FastMCP

# --- Load configuration ---

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> dict:
    """Loads the config.json file."""
    if not CONFIG_PATH.exists():
        print("ERROR: config.json not found! Copy config.example.json as config.json and fill it in.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

# --- Initialize ElevenLabs client ---

from elevenlabs import ElevenLabs

elevenlabs_client = ElevenLabs(api_key=config["elevenlabs_api_key"])

# --- Create MCP server ---

# --- Initialize pygame mixer once (avoids popping sounds) ---

import pygame
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)

# --- Create MCP server ---

mcp = FastMCP(name="voice-bridge")


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Reads text aloud using ElevenLabs TTS.

    Args:
        text: The text to read aloud
        voice: Optional voice ID (if not provided, uses the one from config.json)

    Returns:
        Status message
    """
    try:
        # Voice ID: from parameter or config
        voice_id = voice or config["tts"]["voice_id"]
        model_id = config["tts"].get("model_id", "eleven_multilingual_v2")
        language_code = config["tts"].get("language_code", "hu")

        print(f"TTS: reading aloud '{text[:50]}...' ({voice_id})", file=sys.stderr)

        # Start TTS in a background thread — the tool returns IMMEDIATELY to Claude
        # This way Claude doesn't wait for playback to finish, the text response appears right away
        def _tts_background():
            with _tts_lock:  # Queues the calls — two voices won't overlap
                try:
                    # MP3 format — better audio quality
                    audio_stream = elevenlabs_client.text_to_speech.convert(
                        text=text,
                        voice_id=voice_id,
                        model_id=model_id,
                        language_code=language_code,
                        output_format="mp3_44100_128",
                    )

                    # Collect audio
                    audio_bytes = b""
                    for chunk in audio_stream:
                        if isinstance(chunk, bytes):
                            audio_bytes += chunk

                    if audio_bytes:
                        _play_audio_mp3(audio_bytes)
                    else:
                        print("TTS: empty audio received from API!", file=sys.stderr)
                except Exception as e:
                    print(f"TTS background error: {e}", file=sys.stderr)

        threading.Thread(target=_tts_background, daemon=True).start()

        return f"Read aloud: {text[:100]}{'...' if len(text) > 100 else ''}"

    except Exception as e:
        error_msg = f"TTS error: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg


def _play_audio_mp3(audio_bytes: bytes):
    """Plays MP3 audio using pygame."""
    import tempfile

    # Save the MP3 to a temp file
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"Playback error: {e}", file=sys.stderr)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# --- Start server ---

if __name__ == "__main__":
    print("Voice Bridge MCP server starting...", file=sys.stderr)
    mcp.run(transport="stdio")
