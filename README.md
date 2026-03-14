# claude-voice-bridge

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![ElevenLabs](https://img.shields.io/badge/TTS%2FSTT-ElevenLabs-orange)
![MCP](https://img.shields.io/badge/Protocol-MCP-purple)

A fully voice-enabled interface for the [Claude Desktop](https://claude.ai/download) app. Speak to Claude and hear responses spoken aloud — no admin rights required.

---

## Overview

**claude-voice-bridge** adds a complete voice layer on top of Claude Desktop via two components that run alongside the app:

- **MCP TTS Server** (`tts_server.py`) — Claude calls a `speak` tool after each response. The server sends the text to ElevenLabs Text-to-Speech and plays the audio locally via pygame.
- **STT Companion** (`stt_companion.py`) — A background app with a system tray icon. It listens to your microphone, transcribes speech via ElevenLabs Speech-to-Text (Scribe v1), and pastes the result directly into Claude Desktop's input field.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Claude Desktop App                   │
│                                                      │
│   [User types or pastes from STT] → Claude responds  │
│                                          ↓           │
│                                    tool call: speak  │
│                                          ↓           │
│                              ┌───────────────────┐   │
│                              │  MCP TTS Server   │   │
│                              │  (ElevenLabs)     │   │
│                              └───────────────────┘   │
└─────────────────────────────────────────────────────┘
                ↑ auto-paste
┌─────────────────────────────────────────────────────┐
│          STT Companion (background process)          │
│                                                      │
│   Hotkey / VAD → record mic                          │
│   Speech detected → ElevenLabs STT → paste           │
│                                                      │
│   System tray: grey = idle, green = listening,       │
│                red = recording                       │
└─────────────────────────────────────────────────────┘
```

---

## Input Modes

The STT Companion supports three modes, configurable in `config.json`:

| Mode | `"mode"` value | How it works |
|---|---|---|
| Push-to-talk | `"push_to_talk"` | Hold the hotkey to record, release to transcribe |
| VAD toggle | `"vad"` | Press hotkey to start; VAD detects speech/silence and sends automatically, then turns off |
| VAD always-on | `"vad_always"` | Always listening; use a configurable mute key (e.g. F4) to toggle the mic |

### System tray icon states

- **Grey** — idle
- **Green** — listening / VAD active
- **Red** — actively recording speech

---

## Requirements

- Windows (tested on Windows 10/11)
- Python 3.11+
- An [ElevenLabs](https://elevenlabs.io) account with API access (paid plan recommended for STT)
- Claude Desktop app

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/claude-voice-bridge.git
cd claude-voice-bridge
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

> `webrtcvad` requires a separate install due to Windows binary availability:

```bash
pip install webrtcvad-wheels
```

### 3. Configure

Copy the example config and fill in your credentials:

```bash
copy config.example.json config.json
```

Edit `config.json` and set your `elevenlabs_api_key` and `tts.voice_id`. See the [Configuration](#configuration) section for all options.

> `config.json` is listed in `.gitignore` and will never be committed — it contains your API key.

### 4. Register the MCP server in Claude Desktop

Open Claude Desktop → Settings → Developer → Edit Config, and add the `mcpServers` block:

```json
{
  "mcpServers": {
    "voice-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\claude-voice-bridge\\tts_server.py"]
    }
  }
}
```

Replace the path with the actual location of `tts_server.py` on your system.

### 5. Start the STT Companion

```bash
python stt_companion.py
```

A system tray icon will appear. The companion runs in the background and auto-pastes transcriptions into whichever window is active (Claude Desktop).

### 6. Restart Claude Desktop

After adding the MCP server entry, restart Claude Desktop for it to register the `speak` tool.

---

## Configuration

Full `config.json` reference:

```json
{
  "elevenlabs_api_key": "YOUR_API_KEY",
  "tts": {
    "voice_id": "YOUR_VOICE_ID",
    "model_id": "eleven_v3",
    "language_code": "hu",
    "streaming": true
  },
  "stt": {
    "model_id": "scribe_v1",
    "language_code": "hu"
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1
  },
  "hotkey": "caps lock",
  "mute_key": "f4",
  "mode": "vad_always",
  "vad": {
    "aggressiveness": 2,
    "silence_timeout": 1.5,
    "speech_threshold": 3,
    "volume_threshold": 0
  },
  "auto_paste": true,
  "auto_enter": true
}
```

| Key | Description |
|---|---|
| `elevenlabs_api_key` | Your ElevenLabs API key |
| `tts.voice_id` | ElevenLabs voice ID to use for speech output |
| `tts.model_id` | TTS model (default: `eleven_v3`) |
| `tts.language_code` | Language for TTS (default: `hu` for Hungarian) |
| `tts.streaming` | Stream audio while generating (lower latency) |
| `stt.model_id` | STT model (default: `scribe_v1`) |
| `stt.language_code` | Language hint for transcription |
| `audio.sample_rate` | Microphone sample rate in Hz |
| `hotkey` | Key used for push-to-talk or VAD toggle |
| `mute_key` | Key to toggle mic in `vad_always` mode |
| `mode` | Input mode: `push_to_talk`, `vad`, or `vad_always` |
| `vad.aggressiveness` | WebRTC VAD aggressiveness: 0 (least) to 3 (most) |
| `vad.silence_timeout` | Seconds of silence before ending a recording |
| `vad.speech_threshold` | Minimum speech frames before recording is accepted |
| `vad.volume_threshold` | Minimum volume level to consider as speech (0 = off) |
| `auto_paste` | Automatically paste transcription into the active window |
| `auto_enter` | Automatically press Enter after pasting (hands-free mode) |

> The language is fully configurable — Hungarian is the default but any ElevenLabs-supported language works.

---

## File Structure

```
claude-voice-bridge/
├── CLAUDE.md              — Project context for Claude Code
├── LICENSE
├── README.md
├── config.json            — Runtime config with secrets (gitignored)
├── config.example.json    — Template config without secrets
├── requirements.txt       — Python dependencies
├── tts_server.py          — MCP TTS server
├── stt_companion.py       — STT background app with system tray
├── icons/
│   ├── mic_idle.png       — Tray icon: idle state
│   ├── mic_listening.png  — Tray icon: VAD listening state
│   └── mic_active.png     — Tray icon: recording state
└── .gitignore
```

---

## Tech Stack

| Component | Technology |
|---|---|
| MCP server | [`mcp`](https://pypi.org/project/mcp/) SDK, stdio transport |
| Text-to-Speech | ElevenLabs API — eleven_v3 model, streaming |
| Speech-to-Text | ElevenLabs API — Scribe v1 model |
| Audio playback | `pygame.mixer` |
| Microphone input | `sounddevice` |
| Voice activity detection | `webrtcvad-wheels` |
| Keyboard hotkeys | `pynput` (no admin rights needed) |
| System tray | `pystray` + `Pillow` |
| Clipboard / paste | `pyperclip` + `pyautogui` |

---

## Dependencies

```
mcp>=1.0.0
elevenlabs>=1.0.0
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
pystray>=0.19.5
Pillow>=10.0.0
pynput>=1.7.6
pyperclip>=1.8.2
pyautogui>=0.9.54
pygame>=2.5.0
webrtcvad-wheels>=2.0.11
```

---

## Notes

- **No admin rights required** — keyboard input is handled by `pynput`, which works without elevated privileges (unlike the `keyboard` library).
- **config.json is gitignored** — your API key stays local.
- **Language is configurable** — set `language_code` in both `tts` and `stt` sections to any ElevenLabs-supported language.
- **auto_enter** — set to `false` if you want to review/edit transcriptions before sending.

---

## Credits

Built by **Anita Leszkovszki** with the assistance of [Claude Code](https://claude.ai/claude-code) (Claude Opus 4.6 by Anthropic).

---

## License

MIT — see [LICENSE](LICENSE) for details.
