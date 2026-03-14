# claude-voice-bridge

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![ElevenLabs](https://img.shields.io/badge/TTS%2FSTT-ElevenLabs-orange)
![MCP](https://img.shields.io/badge/Protocol-MCP-purple)

A fully voice-enabled interface for the [Claude Desktop](https://claude.ai/download) app. Speak to Claude and hear responses spoken aloud — no admin rights required.

> **Magyar verzió / Hungarian version:** [README_HU.md](README_HU.md)

---

## What does it do?

**claude-voice-bridge** turns Claude Desktop into a voice assistant. You speak into your microphone, your speech is transcribed and sent to Claude, and Claude's response is read aloud to you — all automatically.

The system consists of two components that work alongside the Claude Desktop app:

- **MCP TTS Server** (`tts_server.py`) — An MCP server that Claude calls via its `speak` tool. It sends Claude's response text to ElevenLabs Text-to-Speech and plays the audio on your speakers.
- **STT Companion** (`stt_companion.py`) — A background app with a system tray icon. It listens to your microphone, transcribes your speech via ElevenLabs Speech-to-Text (Scribe v1), and automatically pastes the transcription into Claude Desktop's input field.

### A note on latency

This project **prioritizes response quality and voice quality over speed**. Claude's full text response is generated first, then converted to high-quality audio (MP3, 44.1 kHz). This means there is a noticeable delay between your question and hearing the spoken response — typically a few seconds depending on response length. This is a deliberate design choice: we chose natural-sounding, high-fidelity voice output over lower-latency but lower-quality alternatives.

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

The STT Companion supports three modes (set `"mode"` in `config.json`):

| Mode | Config value | How it works |
|---|---|---|
| **Push-to-talk** | `"push_to_talk"` | Hold the hotkey to record, release to transcribe |
| **VAD toggle** | `"vad"` | Press the hotkey once to start listening. VAD detects speech and silence, sends automatically, then stops listening |
| **VAD always-on** | `"vad_always"` | Continuously listens for speech. Use a configurable mute key (e.g., F4) to toggle the microphone on/off |

### System tray icon

| Color | Meaning |
|---|---|
| Grey | Idle — not listening |
| Green | Listening — waiting for speech (VAD active) |
| Red | Recording — speech detected, capturing audio |

Right-click the tray icon for a menu showing the current mode, key bindings, and an exit option.

---

## Prerequisites

Before you start, make sure you have:

1. **Windows 10 or 11**
2. **Python 3.11 or newer** — Download from [python.org](https://www.python.org/downloads/). During installation, check "Add Python to PATH".
3. **Claude Desktop app** — Download from [claude.ai/download](https://claude.ai/download)
4. **An ElevenLabs account with API access** — Sign up at [elevenlabs.io](https://elevenlabs.io). A **paid plan is recommended** — the free tier has limited characters per month, and the STT (Scribe) API may require a paid subscription. You'll need:
   - Your **API key** (found in Profile → API Keys)
   - A **Voice ID** for TTS (found in Voices → click a voice → Voice ID)

---

## Setup Guide

### Step 1: Download the project

**Option A — Using Git:**
```bash
git clone https://github.com/LeszkovszkiAnita/claude-voice-bridge.git
cd claude-voice-bridge
```

**Option B — Manual download:**
Download the ZIP from GitHub, extract it to a folder (e.g., `C:\Users\YourName\Desktop\claude-voice-bridge`).

### Step 2: Install Python dependencies

Open a terminal (Command Prompt or PowerShell) in the project folder and run:

```bash
pip install -r requirements.txt
```

> **Note:** If `webrtcvad` fails to install, try: `pip install webrtcvad-wheels` — this provides pre-built Windows binaries.

### Step 3: Create your configuration file

1. In the project folder, find `config.example.json`
2. **Copy it** and rename the copy to `config.json`
3. Open `config.json` in any text editor (Notepad works fine)
4. Fill in your settings:

```json
{
  "elevenlabs_api_key": "paste-your-api-key-here",
  "tts": {
    "voice_id": "paste-your-voice-id-here",
    "model_id": "eleven_v3",
    "language_code": "en"
  },
  "stt": {
    "model_id": "scribe_v1",
    "language_code": "en"
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
    "silence_timeout": 3.0,
    "speech_threshold": 3,
    "volume_threshold": 800
  },
  "auto_paste": true,
  "auto_enter": false
}
```

**Where to find your ElevenLabs credentials:**
- **API key:** Log in to [elevenlabs.io](https://elevenlabs.io) → click your profile icon (top-right) → Profile + API key → copy the key
- **Voice ID:** Go to Voices → pick a voice you like → click on it → copy the Voice ID from the URL or the details panel

**Key settings to customize:**
- `language_code` — Change `"en"` to your language (e.g., `"hu"` for Hungarian, `"de"` for German, `"es"` for Spanish). Set it in **both** `tts` and `stt` sections.
- `mode` — Choose your preferred input mode (see [Input Modes](#input-modes) above)
- `mute_key` — The key to mute/unmute the microphone in `vad_always` mode. Supported keys: `f1`–`f12`, `caps lock`, `scroll lock`, `pause`, `insert`, `num lock`
- `auto_enter` — Set to `true` if you want transcriptions to be sent automatically (hands-free). Set to `false` to review before sending.
- `vad.volume_threshold` — Minimum audio volume to be considered speech. Increase if background noise triggers false transcriptions. Set to `0` to disable (use the mute key instead).

> **Important:** `config.json` contains your API key and is listed in `.gitignore` — it will never be uploaded to GitHub.

### Step 4: Register the MCP server in Claude Desktop

This tells Claude Desktop about the `speak` tool so Claude can use it.

1. Open Claude Desktop
2. Go to **Settings** (gear icon) → **Developer** → **Edit Config**
3. This opens the file `claude_desktop_config.json`. Add the following inside it:

```json
{
  "mcpServers": {
    "voice-bridge": {
      "command": "python",
      "args": ["C:\\full\\path\\to\\claude-voice-bridge\\tts_server.py"]
    }
  }
}
```

**Important:** Replace `C:\\full\\path\\to\\claude-voice-bridge\\tts_server.py` with the actual path to the file on your computer. Use **double backslashes** (`\\`) in the path.

For example, if you put the project on your Desktop:
```json
"args": ["C:\\Users\\YourName\\Desktop\\claude-voice-bridge\\tts_server.py"]
```

> **Tip:** If the `python` command doesn't work, use the full Python path instead, e.g., `"command": "C:\\Python312\\python.exe"`. You can find yours by running `where python` in a terminal.

4. **Save the file** and **restart Claude Desktop** completely (close and reopen it).

### Step 5: Start the STT Companion

In a terminal, run:

```bash
python stt_companion.py
```

A system tray icon will appear near your clock (you may need to click the `^` arrow to see it). The companion is now running in the background.

### Step 6: Test it!

1. Open Claude Desktop and start a conversation
2. Speak into your microphone — your speech will be transcribed and pasted into the input field
3. Claude will respond in text AND read the response aloud

### Optional: Create a desktop shortcut

You can create a desktop shortcut that launches the companion with a single double-click — no console window, with start/stop/restart buttons.

1. Right-click on your Desktop → **New** → **Text Document**
2. Name it `Voice Bridge.vbs` (make sure the extension is `.vbs`, not `.vbs.txt` — you may need to enable "Show file extensions" in Windows Explorer)
3. Right-click the file → **Edit** (or open with Notepad)
4. Paste the following content, replacing the paths with your actual Python and script locations:

```vbs
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pythonExe = "C:\Python312\python.exe"
scriptPath = "C:\Users\YourName\Desktop\claude-voice-bridge\stt_companion.py"

' Check if companion is already running
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set processes = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%stt_companion.py%' AND Name = 'python.exe'")

alreadyRunning = (processes.Count > 0)

If alreadyRunning Then
    msg = "Voice Bridge is running!" & vbCrLf & vbCrLf & _
          "STOP = Abort button" & vbCrLf & _
          "RESTART = Retry button" & vbCrLf & _
          "KEEP RUNNING = Ignore button"
    result = MsgBox(msg, vbAbortRetryIgnore + vbQuestion, "Voice Bridge")

    If result = vbAbort Then
        ' STOP
        For Each proc In processes
            proc.Terminate()
        Next
        MsgBox "Voice Bridge stopped.", vbInformation, "Voice Bridge"
    ElseIf result = vbRetry Then
        ' RESTART
        For Each proc In processes
            proc.Terminate()
        Next
        WScript.Sleep 1000
        WshShell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
        MsgBox "Voice Bridge restarted!", vbInformation, "Voice Bridge"
    End If
Else
    WshShell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
    MsgBox "Voice Bridge started!" & vbCrLf & vbCrLf & _
           "Look for the icon in the system tray (near the clock)." & vbCrLf & _
           "Double-click this shortcut again to stop or restart.", _
           vbInformation, "Voice Bridge"
End If
```

5. Save and close. Now double-click `Voice Bridge.vbs` to launch!

**How the shortcut works:**
- **First launch:** Starts the companion in the background (no console window) and shows a confirmation
- **If already running:** Shows a dialog with three buttons:
  - **Abort** = Stop the companion
  - **Retry** = Restart the companion
  - **Ignore** = Keep running (do nothing)

---

## Configuration Reference

| Key | Description | Default |
|---|---|---|
| `elevenlabs_api_key` | Your ElevenLabs API key | *(required)* |
| `tts.voice_id` | ElevenLabs voice ID for speech output | *(required)* |
| `tts.model_id` | TTS model | `eleven_v3` |
| `tts.language_code` | Language for TTS output | `hu` |
| `stt.model_id` | STT model | `scribe_v1` |
| `stt.language_code` | Language hint for transcription | `hu` |
| `audio.sample_rate` | Microphone sample rate in Hz | `16000` |
| `audio.channels` | Audio channels (1 = mono) | `1` |
| `hotkey` | Key for push-to-talk or VAD toggle | `caps lock` |
| `mute_key` | Key to toggle mic mute in `vad_always` mode | `f4` |
| `mode` | Input mode: `push_to_talk`, `vad`, or `vad_always` | `vad_always` |
| `vad.aggressiveness` | WebRTC VAD sensitivity: 0 (least) to 3 (most aggressive) | `2` |
| `vad.silence_timeout` | Seconds of silence before ending a recording | `3.0` |
| `vad.speech_threshold` | Minimum consecutive speech frames before recording starts | `3` |
| `vad.volume_threshold` | Minimum volume level to count as speech (0 = disabled) | `800` |
| `auto_paste` | Automatically paste transcription into the active window | `true` |
| `auto_enter` | Automatically press Enter after pasting (hands-free mode) | `false` |

---

## File Structure

```
claude-voice-bridge/
├── README.md              — This file (English)
├── README_HU.md           — Hungarian documentation
├── LICENSE                 — MIT License
├── CLAUDE.md              — Project context for Claude Code
├── config.json            — Your config with API key (gitignored)
├── config.example.json    — Template config without secrets
├── requirements.txt       — Python dependencies
├── tts_server.py          — MCP TTS server (Claude calls this)
├── stt_companion.py       — STT companion app with system tray
├── icons/
│   ├── mic_idle.png       — Tray icon: idle (grey)
│   ├── mic_listening.png  — Tray icon: listening (green)
│   └── mic_active.png     — Tray icon: recording (red)
└── .gitignore
```

---

## Tech Stack

| Component | Technology |
|---|---|
| MCP server | [`mcp`](https://pypi.org/project/mcp/) SDK, stdio transport |
| Text-to-Speech | ElevenLabs API (eleven_v3), MP3 44.1 kHz |
| Speech-to-Text | ElevenLabs API (Scribe v1) |
| Audio playback | `pygame.mixer` (single init, no crackling) |
| Microphone input | `sounddevice` |
| Voice Activity Detection | `webrtcvad` |
| Keyboard hotkeys | `pynput` (no admin rights needed) |
| System tray | `pystray` + `Pillow` |
| Clipboard / paste | `pyperclip` + Win32 `keybd_event` |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `speak` tool not available in Claude | Make sure `tts_server.py` path is correct in `claude_desktop_config.json` and restart Claude Desktop |
| No audio playback | Check your speakers/headphones. Try running `python -c "import pygame; pygame.mixer.init(); print('OK')"` |
| STT not transcribing | Check your microphone is working and not muted in Windows Sound settings |
| VAD picks up background noise | Increase `vad.volume_threshold` or use the mute key to temporarily disable the mic |
| Transcription contains noise descriptions like "(music)" | This is filtered automatically. If it still happens, increase `vad.aggressiveness` to 3 |
| Multiple instances running | The companion has built-in single-instance protection. Kill all `python.exe` processes and restart |
| `webrtcvad` install fails | Use `pip install webrtcvad-wheels` instead |
| `keyboard` library needs admin | This project uses `pynput` instead — no admin rights needed |

---

## Credits

The entire codebase — both Python scripts, configuration, documentation, and project architecture — was designed and written by Claude through [Claude Code](https://claude.ai/claude-code), Anthropic's agentic coding tool.

---

## License

MIT — see [LICENSE](LICENSE) for details.
