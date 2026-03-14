"""
MCP TTS Server — Claude Desktop voice bridge
ElevenLabs Text-to-Speech integrációval.

Claude a 'speak' tool-lal szöveget küld ide,
a szerver pedig ElevenLabs-on keresztül felolvassa.
"""

import json
import sys
import os
import io
import tempfile
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# --- Konfiguráció betöltése ---

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> dict:
    """Betölti a config.json fájlt."""
    if not CONFIG_PATH.exists():
        print("HIBA: config.json nem található! Másold a config.example.json-t config.json-ként és töltsd ki.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

# --- ElevenLabs kliens inicializálása ---

from elevenlabs import ElevenLabs

elevenlabs_client = ElevenLabs(api_key=config["elevenlabs_api_key"])

# --- MCP szerver létrehozása ---

# --- Pygame mixer egyszer inicializálása (elkerüli a pattogást) ---

import pygame
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)

# --- MCP szerver létrehozása ---

mcp = FastMCP(name="voice-bridge")


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Szöveget hangosan felolvas ElevenLabs TTS segítségével.

    Args:
        text: A felolvasandó szöveg
        voice: Opcionális voice ID (ha nem adod meg, a config.json-ból veszi)

    Returns:
        Státusz üzenet
    """
    try:
        # Voice ID: paraméterből vagy configból
        voice_id = voice or config["tts"]["voice_id"]
        model_id = config["tts"].get("model_id", "eleven_multilingual_v2")
        language_code = config["tts"].get("language_code", "hu")

        print(f"TTS: '{text[:50]}...' felolvasása ({voice_id})", file=sys.stderr)

        # Háttérszálban indítjuk a TTS-t — a tool AZONNAL visszatér Claude-nak
        # Így Claude nem vár a lejátszás végére, a szöveges válasz rögtön megjelenik
        def _tts_background():
            try:
                # MP3 formátum — jobb hangminőség
                audio_stream = elevenlabs_client.text_to_speech.convert(
                    text=text,
                    voice_id=voice_id,
                    model_id=model_id,
                    language_code=language_code,
                    output_format="mp3_44100_128",
                )

                # Audio összegyűjtése
                audio_bytes = b""
                for chunk in audio_stream:
                    if isinstance(chunk, bytes):
                        audio_bytes += chunk

                if audio_bytes:
                    _play_audio_mp3(audio_bytes)
            except Exception as e:
                print(f"TTS háttér hiba: {e}", file=sys.stderr)

        threading.Thread(target=_tts_background, daemon=True).start()

        return f"Felolvastam: {text[:100]}{'...' if len(text) > 100 else ''}"

    except Exception as e:
        error_msg = f"TTS hiba: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg


def _play_audio_mp3(audio_bytes: bytes):
    """MP3 audio lejátszása pygame-mel."""
    import tempfile

    # Temp fájlba mentjük az MP3-at
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
        print(f"Lejátszás hiba: {e}", file=sys.stderr)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# --- Szerver indítása ---

if __name__ == "__main__":
    print("Voice Bridge MCP szerver indul...", file=sys.stderr)
    mcp.run(transport="stdio")
