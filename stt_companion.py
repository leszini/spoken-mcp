"""
STT Companion — Háttérben futó beszédfelismerő script
ElevenLabs Speech-to-Text integrációval.

Három mód:
  1. Push-to-talk (Caps Lock nyomvatartás) — config: "mode": "push_to_talk"
  2. VAD toggle (Caps Lock toggle + automatikus beszédfelismerés) — config: "mode": "vad"
     Caps Lock egyszer → figyelés BE (zöld ikon)
     Beszélsz → felvétel (piros ikon) → csend → elküldi → figyelés KI (szürke)
  3. VAD always-on — config: "mode": "vad_always" (nem ajánlott zajos környezetben)

System tray ikon jelzi az állapotot:
  - Szürke = idle (nem figyel)
  - Zöld = figyelés (VAD aktív, beszédre vár)
  - Piros = recording (beszéd észlelve / felvétel zajlik)
"""

import json
import sys
import os
import io
import time
import threading
import wave
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

# --- Konfiguráció betöltése ---

CONFIG_PATH = Path(__file__).parent / "config.json"
ICONS_DIR = Path(__file__).parent / "icons"


def load_config() -> dict:
    """Betölti a config.json fájlt."""
    if not CONFIG_PATH.exists():
        print("HIBA: config.json nem található!")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


config = load_config()

# --- ElevenLabs kliens ---

elevenlabs_client = ElevenLabs(api_key=config["elevenlabs_api_key"])

# --- Globális állapot ---

is_recording = False
vad_listening = False  # VAD toggle: True = figyel, False = némítva
mic_muted = False  # Caps Lock mute: True = mikrofon némítva
audio_frames = []
sample_rate = config["audio"].get("sample_rate", 16000)
channels = config["audio"].get("channels", 1)
tray_icon = None


# --- Ikon betöltése ---

def load_icon(state: str) -> Image.Image:
    """Betölti a megfelelő tray ikont (idle vagy active).
    Ha nem találja a fájlt, generál egy egyszerű ikont.
    """
    icon_file = ICONS_DIR / f"mic_{state}.png"
    if icon_file.exists():
        return Image.open(icon_file)

    # Fallback: egyszerű színes kör generálása
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    if state == "active":
        color = (220, 50, 50, 255)  # Piros = felvétel
    elif state == "listening":
        color = (50, 180, 50, 255)  # Zöld = VAD figyel, beszédre vár
    else:
        color = (128, 128, 128, 255)  # Szürke = idle
    # Kör rajzolása
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Mikrofon jelzés (egyszerű fehér téglalap középen)
    mic_w, mic_h = 12, 24
    mic_x = (size - mic_w) // 2
    mic_y = (size - mic_h) // 2 - 4
    draw.rounded_rectangle([mic_x, mic_y, mic_x + mic_w, mic_y + mic_h],
                           radius=4, fill=(255, 255, 255, 255))
    # Mikrofon talpa
    draw.arc([mic_x - 6, mic_y + 8, mic_x + mic_w + 6, mic_y + mic_h + 8],
             start=0, end=180, fill=(255, 255, 255, 255), width=2)
    draw.line([size // 2, mic_y + mic_h + 8, size // 2, mic_y + mic_h + 16],
              fill=(255, 255, 255, 255), width=2)

    return img


# --- Felvétel kezelése ---

def start_recording():
    """Elindítja a hangfelvételt."""
    global is_recording, audio_frames
    if is_recording:
        return

    is_recording = True
    audio_frames = []

    # Tray ikon frissítése pirosra
    if tray_icon:
        tray_icon.icon = load_icon("active")
        tray_icon.title = "Voice Bridge — Felvétel..."

    print("🎙️ Felvétel indul...", file=sys.stderr)

    # Háttérszálban indítjuk a felvételt
    def record_loop():
        """Folyamatosan rögzíti a hangot amíg is_recording True."""
        try:
            with sd.InputStream(samplerate=sample_rate, channels=channels,
                                dtype="int16") as stream:
                while is_recording:
                    data, _ = stream.read(int(sample_rate * 0.1))  # 100ms darabok
                    audio_frames.append(data.copy())
        except Exception as e:
            print(f"Felvétel hiba: {e}", file=sys.stderr)

    threading.Thread(target=record_loop, daemon=True).start()


def stop_recording():
    """Megállítja a felvételt és elküldi az ElevenLabs STT-nek."""
    global is_recording
    if not is_recording:
        return

    is_recording = False
    print("⏹️ Felvétel vége, átírás...", file=sys.stderr)

    # Tray ikon visszaállítása szürkére
    if tray_icon:
        tray_icon.icon = load_icon("idle")
        tray_icon.title = "Voice Bridge — Átírás folyamatban..."

    # Összefűzzük az audio frame-eket
    if not audio_frames:
        print("Nincs felvett hang.", file=sys.stderr)
        if tray_icon:
            tray_icon.title = "Voice Bridge — Kész"
        return

    audio_data = np.concatenate(audio_frames, axis=0)

    # WAV formátumba konvertálás memóriában
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 = 2 byte
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())

    wav_buffer.seek(0)

    # Háttérszálban küldjük el az STT-nek (ne blokkoljuk a hotkey figyelést)
    threading.Thread(target=_transcribe_and_paste, args=(wav_buffer,), daemon=True).start()


def _transcribe_and_paste(wav_buffer: io.BytesIO):
    """Elküldi a hangot az ElevenLabs STT-nek és beilleszti a szöveget."""
    try:
        stt_config = config.get("stt", {})
        model_id = stt_config.get("model_id", "scribe_v1")
        language_code = stt_config.get("language_code", "hu")

        # ElevenLabs STT hívás (fájlnév + MIME típus a megbízhatóbb)
        result = elevenlabs_client.speech_to_text.convert(
            file=("recording.wav", wav_buffer, "audio/wav"),
            model_id=model_id,
            language_code=language_code,
        )

        text = result.text.strip() if result.text else ""

        if not text:
            print("Nem sikerült szöveget felismerni.", file=sys.stderr)
            if tray_icon:
                tray_icon.title = "Voice Bridge — Nem értettem"
            return

        print(f"📝 Felismert szöveg: {text}", file=sys.stderr)

        # Szöveg beillesztése a vágólapon keresztül
        if config.get("auto_paste", True):
            # Eredeti vágólap tartalom mentése
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                original_clipboard = ""

            # Felismert szöveg a vágólapra
            pyperclip.copy(text)
            time.sleep(0.3)  # Várakozás, hogy a vágólap biztosan frissüljön

            # Ctrl+V beillesztés — win32 API-val megbízhatóbb
            import ctypes
            # Szimuláljuk a Ctrl+V billentyűkombinációt alacsony szinten
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)  # Ctrl le
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)        # V le
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)  # V fel
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)  # Ctrl fel
            time.sleep(0.3)

            # Ha auto_enter be van kapcsolva, Enter-t is nyomunk
            if config.get("auto_enter", False):
                pyautogui.press("enter")

            # Eredeti vágólap tartalom visszaállítása
            time.sleep(0.5)
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

        if tray_icon:
            tray_icon.title = "Voice Bridge — Kész"

    except Exception as e:
        print(f"STT hiba: {e}", file=sys.stderr)
        if tray_icon:
            tray_icon.title = f"Voice Bridge — Hiba: {str(e)[:30]}"


# --- Billentyű kezelés (pynput — nem kell admin jog!) ---

# Ismert billentyűk virtuális kódjai (Windows)
KEY_NAME_TO_VK = {
    "caps lock": 20, "capslock": 20,
    "f1": 112, "f2": 113, "f3": 114, "f4": 115, "f5": 116, "f6": 117,
    "f7": 118, "f8": 119, "f9": 120, "f10": 121, "f11": 122, "f12": 123,
    "scroll lock": 145, "scrolllock": 145,
    "pause": 19, "insert": 45,
    "num lock": 144, "numlock": 144,
}

def get_key_vk(key_name: str) -> int:
    """Billentyű név → virtuális kód. Config-ból olvasott nevet alakít VK kóddá."""
    return KEY_NAME_TO_VK.get(key_name.lower().strip(), 20)  # Default: Caps Lock

def key_matches(key, target_vk: int) -> bool:
    """Ellenőrzi, hogy a lenyomott billentyű megegyezik-e a célbillentyűvel."""
    vk = getattr(key, "vk", None)
    if vk is None and hasattr(key, "value"):
        vk = getattr(key.value, "vk", None)
    return vk == target_vk

def setup_hotkey():
    """Beállítja a push-to-talk hotkey-t pynput-tal."""
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


# --- VAD (Voice Activity Detection) mód ---

def toggle_vad_listening():
    """Caps Lock toggle: VAD figyelés be/ki kapcsolása."""
    global vad_listening
    vad_listening = not vad_listening

    if vad_listening:
        print("🔊 VAD figyelés BEKAPCSOLVA — beszélj!", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("listening")
            tray_icon.title = "Voice Bridge — Figyelek, beszélj!"
    else:
        print("🔇 VAD figyelés KIKAPCSOLVA", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("idle")
            tray_icon.title = "Voice Bridge — Caps Lock = figyelés be"


def toggle_mute():
    """Mikrofon némítás ki/be toggle."""
    global mic_muted
    mute_key_name = config.get("mute_key", config.get("hotkey", "caps lock"))
    mic_muted = not mic_muted

    if mic_muted:
        print(f"🔇 Mikrofon NÉMÍTVA — {mute_key_name}-gyel kapcsold vissza", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("idle")
            tray_icon.title = f"Voice Bridge — NÉMÍTVA ({mute_key_name} = visszakapcsolás)"
    else:
        print("🔊 Mikrofon AKTÍV — figyelek!", file=sys.stderr)
        if tray_icon:
            tray_icon.icon = load_icon("listening")
            tray_icon.title = f"Voice Bridge — Figyelek ({mute_key_name} = némítás)"


def setup_mute_toggle():
    """Konfiguálható billentyű = mikrofon némítás toggle."""
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
    print(f"🎤 {mute_key_name} = mikrofon némítás toggle", file=sys.stderr)


def setup_vad_toggle():
    """Konfiguálható billentyű + VAD figyelés toggle."""
    mute_key_name = config.get("mute_key", config.get("hotkey", "caps lock"))
    mute_key_vk = get_key_vk(mute_key_name)

    def on_press(key):
        try:
            if key_matches(key, mute_key_vk):
                toggle_vad_listening()
        except Exception:
            pass

    listener = pynput_kb.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    print(f"🎤 VAD toggle: {mute_key_name} = figyelés be/ki", file=sys.stderr)


def start_vad_listener(always_on=False):
    """Folyamatosan figyeli a mikrofont és automatikusan felismeri a beszédet.

    Működés:
    - always_on=True: mindig figyel (vad_always mód)
    - always_on=False: csak ha vad_listening=True (Caps Lock toggle)
    - Ha beszédet észlel → rögzítés indul (ikon piros)
    - Ha csend van X másodpercig → rögzítés leáll, STT-re küldi, figyelés KI
    """
    global is_recording, audio_frames, vad_listening

    if always_on:
        vad_listening = True

    vad_config = config.get("vad", {})
    aggressiveness = vad_config.get("aggressiveness", 2)
    silence_timeout = vad_config.get("silence_timeout", 1.5)
    speech_threshold = vad_config.get("speech_threshold", 3)
    # Minimum hangerő küszöb — kiszűri a távolabbi hangokat (TV, háttérbeszéd)
    # Értéke: 0-32768, tipikusan 500-2000 jó (a te hangod közelről ~2000+)
    volume_threshold = vad_config.get("volume_threshold", 800)

    vad = webrtcvad.Vad(aggressiveness)

    VAD_SAMPLE_RATE = 16000
    FRAME_DURATION_MS = 30
    FRAME_SIZE = int(VAD_SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 sample

    print(f"🔊 VAD aktív (érzékenység: {aggressiveness}, csend timeout: {silence_timeout}s, "
          f"hangerő küszöb: {volume_threshold})",
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

                    # Ha a figyelés ki van kapcsolva VAGY némítva van, skip
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

                    # Hangerő ellenőrzés — a közeli beszéd hangosabb, mint a TV
                    frame_volume = np.abs(data[:, 0]).mean()
                    is_loud_enough = frame_volume >= volume_threshold

                    # Csak akkor tekintjük beszédnek, ha VAD + elég hangos
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
                                tray_icon.title = "Voice Bridge — Beszéd észlelve..."
                            print("🎙️ Beszéd észlelve, felvétel...", file=sys.stderr)

                        if recording_started:
                            audio_frames.append(data.copy())

                    else:
                        silence_frame_count += 1

                        if recording_started:
                            audio_frames.append(data.copy())

                        if recording_started and silence_frame_count >= silence_frames_needed:
                            recording_started = False
                            is_recording = False
                            speech_frame_count = 0
                            silence_frame_count = 0

                            # Figyelés automatikusan KI (hacsak nem always_on)
                            if not always_on:
                                vad_listening = False

                            if tray_icon:
                                tray_icon.icon = load_icon("idle")
                                tray_icon.title = "Voice Bridge — Átírás..."
                            print("⏹️ Csend észlelve, átírás...", file=sys.stderr)

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
                    print(f"VAD hiba: {e}", file=sys.stderr)
                    time.sleep(0.1)

    thread = threading.Thread(target=vad_loop, daemon=True)
    thread.start()


# --- System Tray ---

def create_tray():
    """Létrehozza a system tray ikont."""
    global tray_icon

    icon_image = load_icon("idle")

    menu = pystray.Menu(
        pystray.MenuItem("Voice Bridge — STT Companion", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Kilépés", on_quit),
    )

    tray_icon = pystray.Icon(
        name="voice-bridge",
        icon=icon_image,
        title="Voice Bridge — Kész",
        menu=menu,
    )

    return tray_icon


def on_quit(icon, item):
    """Kilépés a programból."""
    print("Kilépés...", file=sys.stderr)
    icon.stop()
    os._exit(0)


# --- Főprogram ---

def main():
    """Elindítja az STT companion-t."""
    mode = config.get("mode", "push_to_talk")

    print("=" * 40, file=sys.stderr)
    print("Voice Bridge — STT Companion", file=sys.stderr)
    if mode == "vad":
        print("Mód: VAD + Caps Lock toggle", file=sys.stderr)
        print("Caps Lock → figyelés BE → beszélsz → csend → elküldi → figyelés KI", file=sys.stderr)
    elif mode == "vad_always":
        print("Mód: VAD always-on + Caps Lock némítás", file=sys.stderr)
        print("Folyamatosan figyel — Caps Lock = mikrofon némítás", file=sys.stderr)
    else:
        print("Mód: Push-to-talk (Caps Lock nyomvatartás)", file=sys.stderr)
    print("=" * 40, file=sys.stderr)

    # Mód beállítása
    if mode == "vad":
        setup_vad_toggle()
        start_vad_listener(always_on=False)
    elif mode == "vad_always":
        setup_mute_toggle()
        start_vad_listener(always_on=True)
    else:
        setup_hotkey()

    # System tray ikon (ez blokkol, tehát utoljára hívjuk)
    tray = create_tray()
    tray.run()


if __name__ == "__main__":
    main()
