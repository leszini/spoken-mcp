"""
STT Companion — Background speech recognition script
with ElevenLabs Speech-to-Text integration.

Three modes:
  1. Push-to-talk (hold Caps Lock) — config: "mode": "push_to_talk"
  2. VAD toggle (Caps Lock toggle + automatic speech detection) — config: "mode": "vad"
     Caps Lock once → listening ON (green icon)
     Speak → recording (red icon) → silence → sends → listening OFF (grey)
  3. VAD always-on — config: "mode": "vad_always" (not recommended in noisy environments)

System tray icon indicates state:
  - Grey = idle (not listening)
  - Green = listening (VAD active, waiting for speech)
  - Red = recording (speech detected / recording in progress)
"""

import json
import sys
import os
import io
import time
import threading
import wave
import ctypes
import numpy as np
from pathlib import Path

import sounddevice as sd
import webrtcvad
from pynput import keyboard as pynput_kb
import pyperclip
import pyautogui
from PIL import Image
import pystray

from elevenlabs import ElevenLabs

# --- Single-instance protection (Windows named mutex) ---
# If an instance is already running, the new one exits automatically.
_mutex_name = "Global\\VoiceBridgeSTTCompanion"
_mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _mutex_name)
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    print("Voice Bridge is already running! Only one instance allowed.", file=sys.stderr)
    ctypes.windll.kernel32.CloseHandle(_mutex_handle)
    sys.exit(0)

# --- Load configuration ---

CONFIG_PATH = Path(__file__).parent / "config.json"
ICONS_DIR = Path(__file__).parent / "icons"


def load_config() -> dict:
    """Loads the config.json file."""
    if not CONFIG_PATH.exists():
        print("ERROR: config.json not found!")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


config = load_config()

# --- ElevenLabs client ---

elevenlabs_client = ElevenLabs(api_key=config["elevenlabs_api_key"])

# --- Global state ---

is_recording = False
vad_listening = False  # VAD toggle: True = listening, False = muted
mic_muted = False  # Caps Lock mute: True = microphone muted
transcribing = False  # True = transcription in progress, don't start new one
audio_frames = []
sample_rate = config["audio"].get("sample_rate", 16000)
channels = config["audio"].get("channels", 1)
tray_icon = None


# --- Load icon ---

def load_icon(state: str) -> Image.Image:
    """Loads the appropriate tray icon (idle or active).
    If the file is not found, generates a simple icon.
    """
    icon_file = ICONS_DIR / f"mic_{state}.png"
    if icon_file.exists():
        return Image.open(icon_file)

    # Fallback: generate a simple colored circle
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    if state == "active":
        color = (220, 50, 50, 255)  # Red = recording
    elif state == "listening":
        color = (50, 180, 50, 255)  # Green = VAD listening, waiting for speech
    else:
        color = (128, 128, 128, 255)  # Grey = idle
    # Draw circle
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Microphone indicator (simple white rectangle in center)
    mic_w, mic_h = 12, 24
    mic_x = (size - mic_w) // 2
    mic_y = (size - mic_h) // 2 - 4
    draw.rounded_rectangle([mic_x, mic_y, mic_x + mic_w, mic_y + mic_h],
                           radius=4, fill=(255, 255, 255, 255))
    # Microphone base
    draw.arc([mic_x - 6, mic_y + 8, mic_x + mic_w + 6, mic_y + mic_h + 8],
             start=0, end=180, fill=(255, 255, 255, 255), width=2)
    draw.line([size // 2, mic_y + mic_h + 8, size // 2, mic_y + mic_h + 16],
              fill=(255, 255, 255, 255), width=2)

    return img


# --- Recording management ---

def start_recording():
    """Starts audio recording."""
    global is_recording, audio_frames
    if is_recording:
        return

    is_recording = True
    audio_frames = []

    # Update tray icon to red
    if tray_icon:
        tray_icon.icon = load_icon("active")
        tray_icon.title = "Voice Bridge — Recording..."

    print("🎙️ Recording started...", file=sys.stderr)

    # Start recording in background thread
    def record_loop():
        """Continuously records audio while is_recording is True."""
        try:
            with sd.InputStream(samplerate=sample_rate, channels=channels,
                                dtype="int16") as stream:
                while is_recording:
                    data, _ = stream.read(int(sample_rate * 0.1))  # 100ms chunks
                    audio_frames.append(data.copy())
        except Exception as e:
            print(f"Recording error: {e}", file=sys.stderr)

    threading.Thread(target=record_loop, daemon=True).start()


def stop_recording():
    """Stops recording and sends audio to ElevenLabs STT."""
    global is_recording
    if not is_recording:
        return

    is_recording = False
    print("⏹️ Recording stopped, transcribing...", file=sys.stderr)

    # Reset tray icon to grey
    if tray_icon:
        tray_icon.icon = load_icon("idle")
        tray_icon.title = "Voice Bridge — Transcribing..."

    # Concatenate audio frames
    if not audio_frames:
        print("No audio recorded.", file=sys.stderr)
        if tray_icon:
            tray_icon.title = "Voice Bridge — Ready"
        return

    audio_data = np.concatenate(audio_frames, axis=0)

    # Convert to WAV format in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 = 2 byte
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())

    wav_buffer.seek(0)

    # Send to STT in background thread (don't block hotkey listener)
    threading.Thread(target=_transcribe_and_paste, args=(wav_buffer,), daemon=True).start()


def _transcribe_and_paste(wav_buffer: io.BytesIO):
    """Sends audio to ElevenLabs STT and pastes the transcribed text."""
    global transcribing
    transcribing = True
    try:
        stt_config = config.get("stt", {})
        model_id = stt_config.get("model_id", "scribe_v1")
        language_code = stt_config.get("language_code", "hu")

        # ElevenLabs STT call (filename + MIME type is more reliable)
        result = elevenlabs_client.speech_to_text.convert(
            file=("recording.wav", wav_buffer, "audio/wav"),
            model_id=model_id,
            language_code=language_code,
        )

        text = result.text.strip() if result.text else ""

        if not text:
            print("Could not recognize any text.", file=sys.stderr)
            if tray_icon:
                tray_icon.title = "Voice Bridge — Could not understand"
            return

        # Filter out parenthesized "sound descriptions" — e.g. "(ominous music)", "(rock music)"
        # Scribe outputs these when it hears background noise instead of speech
        import re
        filtered = re.sub(r'\([^)]*\)', '', text).strip()
        if not filtered:
            print(f"⏭️ Background noise description only, skipped: {text}", file=sys.stderr)
            if tray_icon:
                tray_icon.title = "Voice Bridge — Background noise filtered"
            return
        text = filtered

        print(f"📝 Recognized text: {text}", file=sys.stderr)

        # Paste text via clipboard
        if config.get("auto_paste", True):
            # Save original clipboard content
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                original_clipboard = ""

            # Copy recognized text to clipboard
            pyperclip.copy(text)
            time.sleep(0.3)  # Wait to ensure clipboard is updated

            # Ctrl+V paste — more reliable via win32 API
            import ctypes
            # Simulate Ctrl+V key combination at low level
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)  # Ctrl down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)        # V down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)  # V up
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)  # Ctrl up
            time.sleep(0.3)

            # If auto_enter is enabled, also press Enter
            if config.get("auto_enter", False):
                pyautogui.press("enter")

            # Restore original clipboard content
            time.sleep(0.5)
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

        if tray_icon:
            tray_icon.title = "Voice Bridge — Ready"

    except Exception as e:
        print(f"STT error: {e}", file=sys.stderr)
        if tray_icon:
            tray_icon.title = f"Voice Bridge — Error: {str(e)[:30]}"
    finally:
        transcribing = False


# --- Key handling (pynput — no admin rights needed!) ---

# Known key virtual key codes (Windows)
KEY_NAME_TO_VK = {
    "caps lock": 20, "capslock": 20,
    "f1": 112, "f2": 113, "f3": 114, "f4": 115, "f5": 116, "f6": 117,
    "f7": 118, "f8": 119, "f9": 120, "f10": 121, "f11": 122, "f12": 123,
    "scroll lock": 145, "scrolllock": 145,
    "pause": 19, "insert": 45,
    "num lock": 144, "numlock": 144,
}

def get_key_vk(key_name: str) -> int:
    """Key name -> virtual key code. Converts config key name to VK code."""
    return KEY_NAME_TO_VK.get(key_name.lower().strip(), 20)  # Default: Caps Lock

def key_matches(key, target_vk: int) -> bool:
    """Checks whether the pressed key matches the target key."""
    vk = getattr(key, "vk", None)
    if vk is None and hasattr(key, "value"):
        vk = getattr(key.value, "vk", None)
    return vk == target_vk

def setup_hotkey():
    """Sets up the push-to-talk hotkey with pynput."""
    hotkey_vk = get_key_vk(config.get("hotkey", "caps lock"))
    hotkey_name = config.get("hotkey", "caps lock")

    def on_press(key):
        try:
            if key_matches(key, hotkey_vk):
                start_recording()
        except Exception:
            pass

    def on_release(key):
        try:
            if key_matches(key, hotkey_vk):
                stop_recording()
        except Exception:
            pass

    listener = pynput_kb.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()
    print(f"🎤 Push-to-talk hotkey: {hotkey_name}", file=sys.stderr)


# --- VAD (Voice Activity Detection) mode ---

def toggle_vad_listening():
    """Caps Lock toggle: turn VAD listening on/off."""
    global vad_listening
    vad_listening = not vad_listening

    if vad_listening:
        print("🔊 VAD listening ON — speak!", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("listening")
            tray_icon.title = "Voice Bridge — Listening, speak!"
    else:
        print("🔇 VAD listening OFF", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("idle")
            tray_icon.title = "Voice Bridge — Caps Lock = start listening"


def toggle_mute():
    """Microphone mute on/off toggle."""
    global mic_muted
    mute_key_name = config.get("mute_key", config.get("hotkey", "caps lock"))
    mic_muted = not mic_muted

    if mic_muted:
        print(f"🔇 Microphone MUTED — press {mute_key_name} to unmute", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("idle")
            tray_icon.title = f"Voice Bridge — MUTED ({mute_key_name} = unmute)"
    else:
        print("🔊 Microphone ACTIVE — listening!", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("listening")
            tray_icon.title = f"Voice Bridge — Listening ({mute_key_name} = mute)"


def setup_mute_toggle():
    """Configurable key = microphone mute toggle."""
    mute_key_name = config.get("mute_key", config.get("hotkey", "caps lock"))
    mute_key_vk = get_key_vk(mute_key_name)

    def on_press(key):
        try:
            if key_matches(key, mute_key_vk):
                toggle_mute()
        except Exception:
            pass

    listener = pynput_kb.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    print(f"🎤 {mute_key_name} = microphone mute toggle", file=sys.stderr)


def setup_vad_toggle():
    """Configurable key + VAD listening toggle."""
    hotkey_name = config.get("hotkey", "caps lock")
    hotkey_vk = get_key_vk(hotkey_name)

    def on_press(key):
        try:
            if key_matches(key, hotkey_vk):
                toggle_vad_listening()
        except Exception:
            pass

    listener = pynput_kb.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    print(f"🎤 VAD toggle: {hotkey_name} = listening on/off", file=sys.stderr)


def start_vad_listener(always_on=False):
    """Continuously monitors the microphone and automatically detects speech.

    Behavior:
    - always_on=True: always listening (vad_always mode)
    - always_on=False: only when vad_listening=True (Caps Lock toggle)
    - When speech is detected -> recording starts (icon turns red)
    - When silence lasts X seconds -> recording stops, sends to STT, listening OFF
    """
    global is_recording, audio_frames, vad_listening

    if always_on:
        vad_listening = True

    vad_config = config.get("vad", {})
    aggressiveness = vad_config.get("aggressiveness", 2)
    silence_timeout = vad_config.get("silence_timeout", 1.5)
    speech_threshold = vad_config.get("speech_threshold", 3)
    # Minimum volume threshold — filters out distant sounds (TV, background chatter)
    volume_threshold = vad_config.get("volume_threshold", 800)
    # Minimum recording length in seconds — filters out breathing, coughing, etc.
    min_duration = vad_config.get("min_duration", 0.5)

    vad = webrtcvad.Vad(aggressiveness)

    VAD_SAMPLE_RATE = 16000
    FRAME_DURATION_MS = 30
    FRAME_SIZE = int(VAD_SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
    # min_frames_needed filtering disabled — ElevenLabs STT handles noise

    print(f"🔊 VAD active (sensitivity: {aggressiveness}, silence timeout: {silence_timeout}s, "
          f"volume threshold: {volume_threshold}, min. duration: {min_duration}s)",
          file=sys.stderr)

    def vad_loop():
        global is_recording, audio_frames, vad_listening

        speech_frame_count = 0
        silence_frame_count = 0
        silence_frames_needed = int(silence_timeout * 1000 / FRAME_DURATION_MS)
        recording_started = False

        with sd.InputStream(samplerate=VAD_SAMPLE_RATE, channels=1,
                            dtype="int16", blocksize=FRAME_SIZE) as stream:
            while True:
                try:
                    data, _ = stream.read(FRAME_SIZE)

                    # If listening is off OR muted, skip
                    if not vad_listening or mic_muted:
                        speech_frame_count = 0
                        silence_frame_count = 0
                        if recording_started:
                            recording_started = False
                            is_recording = False
                            audio_frames = []
                        time.sleep(0.01)
                        continue

                    audio_chunk = data[:, 0].tobytes()

                    # Volume check — nearby speech is louder than TV
                    frame_volume = np.abs(data[:, 0]).mean()
                    is_loud_enough = frame_volume >= volume_threshold

                    # Only consider it speech if VAD detects it AND it's loud enough
                    is_speech = (vad.is_speech(audio_chunk, VAD_SAMPLE_RATE)
                                 and is_loud_enough)

                    if is_speech:
                        speech_frame_count += 1
                        silence_frame_count = 0

                        if speech_frame_count >= speech_threshold and not recording_started:
                            recording_started = True
                            is_recording = True
                            audio_frames = []
                            if tray_icon:
                                tray_icon.icon = load_icon("active")
                                tray_icon.title = "Voice Bridge — Speech detected..."
                            print("🎙️ Speech detected, recording...", file=sys.stderr)

                        if recording_started:
                            audio_frames.append(data.copy())

                    else:
                        silence_frame_count += 1

                        if recording_started:
                            audio_frames.append(data.copy())

                        if recording_started and silence_frame_count >= silence_frames_needed:
                            recording_started = False
                            is_recording = False
                            total_speech_frames = speech_frame_count
                            speech_frame_count = 0
                            silence_frame_count = 0

                            # Listening automatically OFF (unless always_on)
                            if not always_on:
                                vad_listening = False

                            # Length filtering disabled — short words pass through too

                            # If transcription is already running, don't start a new one
                            if transcribing:
                                print("⏭️ Transcription already in progress, skipped.", file=sys.stderr)
                                audio_frames = []
                                continue

                            if tray_icon:
                                tray_icon.icon = load_icon("idle")
                                tray_icon.title = "Voice Bridge — Transcribing..."
                            print("⏹️ Silence detected, transcribing...", file=sys.stderr)

                            if audio_frames:
                                audio_data = np.concatenate(audio_frames, axis=0)
                                wav_buffer = io.BytesIO()
                                with wave.open(wav_buffer, "wb") as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(VAD_SAMPLE_RATE)
                                    wf.writeframes(audio_data.tobytes())
                                wav_buffer.seek(0)
                                threading.Thread(
                                    target=_transcribe_and_paste,
                                    args=(wav_buffer,),
                                    daemon=True
                                ).start()
                            audio_frames = []

                        if not recording_started:
                            speech_frame_count = 0

                except Exception as e:
                    print(f"VAD error: {e}", file=sys.stderr)
                    time.sleep(0.1)

    thread = threading.Thread(target=vad_loop, daemon=True)
    thread.start()


# --- System Tray ---

def create_tray():
    """Creates the system tray icon."""
    global tray_icon

    mode = config.get("mode", "push_to_talk")
    mute_key = config.get("mute_key", config.get("hotkey", "caps lock")).upper()

    # Mode description for the menu
    if mode == "vad_always":
        mode_label = "Continuous listening (VAD always-on)"
        key_label = f"{mute_key} = microphone mute"
    elif mode == "vad":
        mode_label = "VAD + toggle mode"
        key_label = f"{mute_key} = listening on/off"
    else:
        hotkey = config.get("hotkey", "caps lock").upper()
        mode_label = "Push-to-talk mode"
        key_label = f"{hotkey} hold = speak"

    icon_image = load_icon("idle")

    menu = pystray.Menu(
        pystray.MenuItem("Voice Bridge — STT Companion", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Mode: {mode_label}", None, enabled=False),
        pystray.MenuItem(f"Key: {key_label}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Grey = idle | Green = listening | Red = recording", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit (right-click here)", on_quit),
    )

    tray_icon = pystray.Icon(
        name="voice-bridge",
        icon=icon_image,
        title=f"Voice Bridge — {key_label}",
        menu=menu,
    )

    return tray_icon


def on_quit(icon, item):
    """Exit the program."""
    print("Exiting...", file=sys.stderr)
    icon.stop()
    os._exit(0)


# --- Main program ---

def main():
    """Starts the STT companion."""
    mode = config.get("mode", "push_to_talk")

    print("=" * 40, file=sys.stderr)
    print("Voice Bridge — STT Companion", file=sys.stderr)
    if mode == "vad":
        print("Mode: VAD + Caps Lock toggle", file=sys.stderr)
        print("Caps Lock -> listening ON -> speak -> silence -> sends -> listening OFF", file=sys.stderr)
    elif mode == "vad_always":
        print("Mode: VAD always-on + Caps Lock mute", file=sys.stderr)
        print("Continuously listening — Caps Lock = microphone mute", file=sys.stderr)
    else:
        print("Mode: Push-to-talk (hold Caps Lock)", file=sys.stderr)
    print("=" * 40, file=sys.stderr)

    # Set up mode
    if mode == "vad":
        setup_vad_toggle()
        start_vad_listener(always_on=False)
    elif mode == "vad_always":
        setup_mute_toggle()
        start_vad_listener(always_on=True)
    else:
        setup_hotkey()

    # System tray icon (this blocks, so we call it last)
    tray = create_tray()
    tray.run()


if __name__ == "__main__":
    main()
