# claude-voice-bridge

## Project Goal

Build a voice interface for the Claude Desktop app so the user (Anita) can talk to Claude and hear Claude's responses spoken aloud. The system has two components that work together with the Desktop app:

1. **MCP TTS Server** — Claude calls a `speak` tool after each response, which sends the text to ElevenLabs and plays the audio locally
2. **Companion STT Script** — A background app that listens for Caps Lock (push-to-talk), records speech, transcribes it via ElevenLabs STT, and pastes the text into the Desktop app's input field

The end result: Anita holds Caps Lock → speaks → releases → text appears in Desktop input → she sends it → Claude responds in text AND voice.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Claude Desktop App                   │
│                                                      │
│   [User types or paste from STT] → Claude responds   │
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
│          Companion STT Script (background)           │
│                                                      │
│   Caps Lock held → record mic                        │
│   Caps Lock released → ElevenLabs STT → paste        │
│                                                      │
│   System tray icon: grey = idle, red = recording     │
└─────────────────────────────────────────────────────┘
```

## Components

### 1. MCP TTS Server (`tts_server.py`)

- Python MCP server using the `mcp` SDK (stdio transport)
- Exposes a single tool: `speak(text: str, voice: str | None)`
- Sends text to ElevenLabs Text-to-Speech API
- Uses streaming playback (start playing before full audio is received)
- Default language: Hungarian (`hu`)
- Voice ID configurable via `config.json`
- Audio playback via `sounddevice` + `soundfile`, or `pygame`

Claude Desktop integration (in `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "voice-bridge": {
      "command": "python",
      "args": ["C:\\Users\\leszi\\Desktop\\Claude\\voice_MCP\\tts_server.py"]
    }
  }
}
```

### 2. Companion STT Script (`stt_companion.py`)

- Runs as a background process with a system tray icon (`pystray`)
- Monitors Caps Lock key as push-to-talk trigger
- While Caps Lock is held: records audio from default microphone (`sounddevice`)
- On release: sends audio to ElevenLabs Speech-to-Text API
- Pastes transcription into the active window via clipboard (`pyperclip` + `pyautogui`)
- Caps Lock's original toggle function is suppressed while the script runs
- Tray icon changes color: grey (idle) → red (recording)
- Right-click tray icon → Exit to stop

### 3. Configuration (`config.json`)

```json
{
  "elevenlabs_api_key": "YOUR_API_KEY_HERE",
  "tts": {
    "voice_id": "VOICE_ID_HERE",
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
  "auto_paste": true,
  "auto_enter": false
}
```

> `auto_enter: false` means after transcription, the text is pasted but NOT sent — user can review/edit first. Set to `true` for hands-free mode.

## File Structure

```
voice_MCP/
├── CLAUDE.md              ← this file (project context for Claude Code)
├── config.json            ← runtime config with API keys (GITIGNORED)
├── config.example.json    ← template config without secrets (committed)
├── requirements.txt       ← Python dependencies
├── tts_server.py          ← MCP TTS server
├── stt_companion.py       ← STT background app with system tray
├── icons/
│   ├── mic_idle.png       ← tray icon: idle state
│   └── mic_active.png     ← tray icon: recording state
└── .gitignore
```

## Tech Stack

- **Language:** Python 3.11+
- **MCP SDK:** `mcp` package (stdio transport)
- **TTS:** ElevenLabs API — Text-to-Speech, Eleven v3, streaming
- **STT:** ElevenLabs API — Speech-to-Text (Scribe v1), Hungarian
- **Audio recording:** `sounddevice` (cross-platform microphone access)
- **Audio playback:** `sounddevice` + `soundfile` or `pygame.mixer`
- **System tray:** `pystray` + `Pillow`
- **Hotkey detection:** `keyboard` library
- **Clipboard/paste:** `pyperclip` + `pyautogui`

## Dependencies (`requirements.txt`)

```
mcp>=1.0.0
elevenlabs>=1.0.0
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
pystray>=0.19.5
Pillow>=10.0.0
keyboard>=0.13.5
pyperclip>=1.8.2
pyautogui>=0.9.54
```

## Development Notes

- Anita is a Python learner — write clean, well-commented code with Hungarian comments where helpful
- Test each component independently before combining
- The MCP server should work standalone (test with `mcp dev` or by calling the tool directly)
- The STT companion should work standalone (test by running it and checking clipboard output)
- Config file must NEVER be committed to git (contains API key)
- The user's Desktop app is on Windows, path style: backslashes
- ElevenLabs paid plan is active (no IP blocking issues)

## Build Order

1. First: `config.example.json` + `config.json` + `.gitignore` + `requirements.txt`
2. Second: `tts_server.py` — get MCP tool working, test with hardcoded text
3. Third: Register MCP server in Claude Desktop config, test end-to-end TTS
4. Fourth: `stt_companion.py` — get recording + transcription working standalone
5. Fifth: Add auto-paste functionality, test full voice loop
6. Last: Icons, polish, error handling
