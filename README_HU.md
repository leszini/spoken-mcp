# claude-voice-mcp

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![ElevenLabs](https://img.shields.io/badge/TTS%2FSTT-ElevenLabs-orange)
![MCP](https://img.shields.io/badge/Protocol-MCP-purple)

Teljes hangvezérlés a [Claude Desktop](https://claude.ai/download) alkalmazáshoz. Beszélj Claude-hoz és hallgasd meg a válaszait hangosan — rendszergazdai jogok nélkül.

> **English version:** [README.md](README.md)

---

## Mit csinál?

A **claude-voice-mcp** hangasszisztenssé alakítja a Claude Desktop alkalmazást. Beszélsz a mikrofonba, a rendszer átírja szöveggé és elküldi Claude-nak, Claude válasza pedig hangosan felolvasódik — mindezt automatikusan.

A rendszer két komponensből áll, amelyek a Claude Desktop mellett futnak:

- **MCP TTS szerver** (`tts_server.py`) — Egy MCP szerver, amelyet Claude a `speak` eszközön keresztül hív meg. Claude válaszának szövegét elküldi az ElevenLabs Text-to-Speech API-nak, és lejátssza a hangot a hangszóródon.
- **STT Companion** (`stt_companion.py`) — Egy háttérben futó alkalmazás rendszertálca ikonnal. Figyeli a mikrofont, átírja a beszédet szöveggé az ElevenLabs Speech-to-Text (Scribe v1) segítségével, és automatikusan beilleszti az átírást a Claude Desktop beviteli mezőjébe.

### Megjegyzés a késleltetésről

Ez a projekt **a válasz és a hang minőségét részesíti előnyben a sebességgel szemben**. Claude teljes szöveges válasza előbb elkészül, majd utána alakul át kiváló minőségű hanggá (MP3, 44.1 kHz). Ez azt jelenti, hogy érzékelhető késleltetés van a kérdésed és a hangos válasz között — jellemzően néhány másodperc, a válasz hosszától függően. Ez tudatos tervezési döntés: a természetes hangzású, magas minőségű hangkimenetet választottuk az alacsonyabb késleltetésű, de gyengébb minőségű alternatívák helyett.

---

## Architektúra

```
┌─────────────────────────────────────────────────────┐
│                 Claude Desktop App                   │
│                                                      │
│   [Felhasználó ír vagy STT beilleszt] → Claude válasz│
│                                          ↓           │
│                                    tool hívás: speak │
│                                          ↓           │
│                              ┌───────────────────┐   │
│                              │  MCP TTS szerver  │   │
│                              │  (ElevenLabs)     │   │
│                              └───────────────────┘   │
└─────────────────────────────────────────────────────┘
                ↑ auto-beillesztés
┌─────────────────────────────────────────────────────┐
│          STT Companion (háttérfolyamat)               │
│                                                      │
│   Gomb / VAD → mikrofon felvétel                     │
│   Beszéd észlelve → ElevenLabs STT → beillesztés     │
│                                                      │
│   Tálca: szürke = idle, zöld = figyel,              │
│          piros = felvétel                            │
└─────────────────────────────────────────────────────┘
```

---

## Beviteli módok

Az STT Companion három módot támogat (a `config.json` fájlban állítható):

| Mód | Config érték | Működés |
|---|---|---|
| **Nyomva tartás** | `"push_to_talk"` | Tartsd nyomva a gombot a felvételhez, engedd el az átíráshoz |
| **VAD kapcsoló** | `"vad"` | Nyomd meg a gombot egyszer a figyelés indításához. A VAD észleli a beszédet és a csendet, automatikusan elküldi, majd leáll |
| **VAD folyamatos** | `"vad_always"` | Folyamatosan figyel. Egy beállítható némítás gombbal (pl. F4) kapcsolhatod ki/be a mikrofont |

### Rendszertálca ikon

| Szín | Jelentés |
|---|---|
| Szürke | Idle — nem figyel |
| Zöld | Figyel — beszédre vár (VAD aktív) |
| Piros | Felvétel — beszéd észlelve, hang rögzítése folyamatban |

Jobb klikk a tálca ikonra: menü megmutatja az aktuális módot, a billentyűket és a kilépés lehetőséget.

---

## Előfeltételek

Mielőtt kezdenél, győződj meg róla, hogy megvan:

1. **Windows 10 vagy 11**
2. **Python 3.11 vagy újabb** — Letöltés: [python.org](https://www.python.org/downloads/). Telepítéskor pipáld ki az "Add Python to PATH" opciót!
3. **Claude Desktop alkalmazás** — Letöltés: [claude.ai/download](https://claude.ai/download)
4. **ElevenLabs fiók API hozzáféréssel** — Regisztráció: [elevenlabs.io](https://elevenlabs.io). **Fizetős csomag ajánlott** — az ingyenes csomag korlátozott karakterszámot tartalmaz havonta, és az STT (Scribe) API fizetős előfizetést igényelhet. Szükséged lesz:
   - Az **API kulcsodra** (Profil → API Keys menüpont)
   - Egy **Voice ID**-ra a TTS-hez (Voices → válassz egy hangot → Voice ID)

---

## Telepítési útmutató

### 1. lépés: Projekt letöltése

**A opció — Git használatával:**
```bash
git clone https://github.com/LeszkovszkiAnita/claude-voice-mcp.git
cd claude-voice-mcp
```

**B opció — Kézi letöltés:**
Töltsd le a ZIP fájlt a GitHubról, csomagold ki egy mappába (pl. `C:\Users\Neved\Desktop\claude-voice-mcp`).

### 2. lépés: Python függőségek telepítése

Nyiss egy terminált (Parancssor vagy PowerShell) a projekt mappájában és futtasd:

```bash
pip install -r requirements.txt
```

> **Megjegyzés:** Ha a `webrtcvad` telepítése sikertelen, próbáld: `pip install webrtcvad-wheels` — ez előre lefordított Windows binárisokat tartalmaz.

### 3. lépés: Konfigurációs fájl létrehozása

1. A projekt mappában keresd meg a `config.example.json` fájlt
2. **Másold le** és nevezd át a másolatot `config.json`-ra
3. Nyisd meg a `config.json`-t bármilyen szövegszerkesztővel (a Jegyzettömb is jó)
4. Töltsd ki a beállításokat:

```json
{
  "elevenlabs_api_key": "illeszd-be-az-api-kulcsodat",
  "tts": {
    "voice_id": "illeszd-be-a-voice-id-t",
    "model_id": "eleven_v3",
    "language_code": "hu"
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
    "silence_timeout": 3.0,
    "speech_threshold": 3,
    "volume_threshold": 800,
    "min_duration": 0.5
  },
  "auto_paste": true,
  "auto_enter": false
}
```

**Hol találod az ElevenLabs adatokat:**
- **API kulcs:** Jelentkezz be az [elevenlabs.io](https://elevenlabs.io) oldalon → kattints a profil ikonra (jobb felső sarok) → Profile + API key → másold ki a kulcsot
- **Voice ID:** Menj a Voices menübe → válassz egy tetszőleges hangot → kattints rá → másold ki a Voice ID-t

**Fontos beállítások:**
- `language_code` — Állítsd be a nyelvedre (pl. `"hu"` magyar, `"en"` angol, `"de"` német). Állítsd be a `tts` **és** az `stt` szekcióban is!
- `mode` — Válaszd ki a preferált beviteli módot (lásd [Beviteli módok](#beviteli-módok))
- `mute_key` — A mikrofon némítás/visszakapcsolás gombja `vad_always` módban. Támogatott gombok: `f1`–`f12`, `caps lock`, `scroll lock`, `pause`, `insert`, `num lock`
- `auto_enter` — Állítsd `true`-ra, ha azt szeretnéd, hogy az átírás automatikusan elküldődjön (kihangosított mód). Állítsd `false`-ra, ha előbb át akarod nézni a szöveget.
- `vad.volume_threshold` — Minimális hangerő, ami beszédnek számít. Növeld, ha a háttérzaj hamis átírásokat okoz. Állítsd `0`-ra a kikapcsoláshoz (és használd helyette a némítás gombot).

> **Fontos:** A `config.json` tartalmazza az API kulcsodat, és szerepel a `.gitignore`-ban — sosem kerül fel a GitHubra.

### 4. lépés: MCP szerver regisztrálása a Claude Desktop-ban

Ez mondja meg a Claude Desktop-nak, hogy létezik a `speak` eszköz és használhatja.

1. Nyisd meg a Claude Desktop-ot
2. Menj a **Settings** (fogaskerék ikon) → **Developer** → **Edit Config** menübe
3. Megnyílik a `claude_desktop_config.json` fájl. Add hozzá a következőt:

```json
{
  "mcpServers": {
    "claude-voice-mcp": {
      "command": "python",
      "args": ["C:\\teljes\\elérési\\út\\claude-voice-mcp\\tts_server.py"]
    }
  }
}
```

**Fontos:** Cseréld ki a `C:\\teljes\\elérési\\út\\claude-voice-mcp\\tts_server.py` részt a tényleges fájl elérési útra a gépeden. Használj **dupla backslash-t** (`\\`) az útvonalban!

Például, ha az Asztalra tetted a projektet:
```json
"args": ["C:\\Users\\Neved\\Desktop\\claude-voice-mcp\\tts_server.py"]
```

> **Tipp:** Ha a `python` parancs nem működik, használd a teljes Python útvonalat, pl. `"command": "C:\\Python312\\python.exe"`. A sajátodat megtalálod a `where python` paranccsal a terminálban.

4. **Mentsd el a fájlt** és **indítsd újra a Claude Desktop-ot** teljesen (zárd be és nyisd meg újra).

### 5. lépés: STT Companion indítása

Terminálban futtasd:

```bash
python stt_companion.py
```

Egy rendszertálca ikon jelenik meg az óra mellett (lehet, hogy a `^` nyílra kell kattintanod, hogy lásd). A companion mostantól a háttérben fut.

### 6. lépés: Tesztelés!

1. Nyisd meg a Claude Desktop-ot és indíts egy beszélgetést
2. Beszélj a mikrofonba — a beszéded átíródik szöveggé és beillesztődik a beviteli mezőbe
3. Claude válaszol szövegben ÉS hangosan felolvassa a választ

### Opcionális: Asztali parancsikon készítése

Készíthetsz egy parancsikont az Asztalra, amivel egyetlen dupla kattintással indíthatod a companion-t — konzolablak nélkül, indítás/leállítás/újraindítás gombokkal.

1. Jobb klikk az Asztalon → **Új** → **Szöveges dokumentum**
2. Nevezd el `Voice Bridge.vbs`-nek (figyelj, hogy a kiterjesztés `.vbs` legyen, ne `.vbs.txt` — ehhez szükség lehet a "Fájlnévkiterjesztések megjelenítése" bekapcsolására a Windows Intézőben)
3. Jobb klikk a fájlon → **Szerkesztés** (vagy megnyitás Jegyzettömbbel)
4. Illeszd be az alábbi tartalmat, cseréld ki az útvonalakat a sajátjaidra:

```vbs
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pythonExe = "C:\Python312\python.exe"
scriptPath = "C:\Users\Neved\Desktop\claude-voice-mcp\stt_companion.py"

' Ellenorizzuk, fut-e mar a companion
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set processes = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%stt_companion.py%' AND Name = 'python.exe'")

alreadyRunning = (processes.Count > 0)

If alreadyRunning Then
    msg = "Voice Bridge mar fut!" & vbCrLf & vbCrLf & _
          "STOP = Abort gomb" & vbCrLf & _
          "RESTART = Retry gomb" & vbCrLf & _
          "FUT TOVABB = Ignore gomb"
    result = MsgBox(msg, vbAbortRetryIgnore + vbQuestion, "Voice Bridge")

    If result = vbAbort Then
        ' STOP
        For Each proc In processes
            proc.Terminate()
        Next
        MsgBox "Voice Bridge leallitva.", vbInformation, "Voice Bridge"
    ElseIf result = vbRetry Then
        ' RESTART
        For Each proc In processes
            proc.Terminate()
        Next
        WScript.Sleep 1000
        WshShell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
        MsgBox "Voice Bridge ujrainditva!", vbInformation, "Voice Bridge"
    End If
Else
    WshShell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
    MsgBox "Voice Bridge elinditva!" & vbCrLf & vbCrLf & _
           "A talcan (ora mellett) talald az ikont." & vbCrLf & _
           "Kattints ujra erre az ikonra a leallitashoz.", _
           vbInformation, "Voice Bridge"
End If
```

5. Mentsd el és zárd be. Dupla kattintás a `Voice Bridge.vbs`-re az indításhoz!

**Hogyan működik a parancsikon:**
- **Első indítás:** Elindítja a companion-t a háttérben (konzolablak nélkül) és megjelenít egy megerősítést
- **Ha már fut:** Megjelenik egy párbeszédablak három gombbal:
  - **Abort** = Leállítás
  - **Retry** = Újraindítás
  - **Ignore** = Fut tovább (nem csinál semmit)

---

## Konfigurációs referencia

| Kulcs | Leírás | Alapértelmezett |
|---|---|---|
| `elevenlabs_api_key` | ElevenLabs API kulcsod | *(kötelező)* |
| `tts.voice_id` | ElevenLabs voice ID a hangkimenethez | *(kötelező)* |
| `tts.model_id` | TTS modell | `eleven_v3` |
| `tts.language_code` | TTS nyelve | `hu` |
| `stt.model_id` | STT modell | `scribe_v1` |
| `stt.language_code` | Nyelvi segítség az átíráshoz | `hu` |
| `audio.sample_rate` | Mikrofon mintavételezési frekvencia (Hz) | `16000` |
| `audio.channels` | Hangcsatornák (1 = mono) | `1` |
| `hotkey` | Gomb a push-to-talk vagy VAD kapcsoláshoz | `caps lock` |
| `mute_key` | Mikrofon némítás gomb `vad_always` módban | `f4` |
| `mode` | Beviteli mód: `push_to_talk`, `vad`, vagy `vad_always` | `vad_always` |
| `vad.aggressiveness` | WebRTC VAD érzékenysége: 0 (legkevésbé) – 3 (leginkább agresszív) | `2` |
| `vad.silence_timeout` | Csend másodpercben a felvétel befejezéséig | `3.0` |
| `vad.speech_threshold` | Minimum egymást követő beszédkeretek a felvétel indításához | `3` |
| `vad.volume_threshold` | Minimális hangerő szint beszédnek (0 = kikapcsolva) | `800` |
| `vad.min_duration` | Minimális felvételi hossz másodpercben (kiszűri a köhögést, lélegzést) | `0.5` |
| `auto_paste` | Átírás automatikus beillesztése az aktív ablakba | `true` |
| `auto_enter` | Enter automatikus megnyomása beillesztés után (kihangosított mód) | `false` |

---

## Fájlstruktúra

```
claude-voice-mcp/
├── README.md              — Dokumentáció (angol)
├── README_HU.md           — Ez a fájl (magyar)
├── LICENSE                 — MIT Licensz
├── config.json            — Konfiguráció API kulccsal (gitignored)
├── config.example.json    — Sablonkonfiguráció titkok nélkül
├── requirements.txt       — Python függőségek
├── tts_server.py          — MCP TTS szerver (Claude ezt hívja)
├── stt_companion.py       — STT companion alkalmazás rendszertálca ikonnal
├── icons/
│   ├── mic_idle.png       — Tálca ikon: idle (szürke)
│   ├── mic_listening.png  — Tálca ikon: figyel (zöld)
│   └── mic_active.png     — Tálca ikon: felvétel (piros)
└── .gitignore
```

---

## Technológiai stack

| Komponens | Technológia |
|---|---|
| MCP szerver | [`mcp`](https://pypi.org/project/mcp/) SDK, stdio transport |
| Text-to-Speech | ElevenLabs API (eleven_v3), MP3 44.1 kHz |
| Speech-to-Text | ElevenLabs API (Scribe v1) |
| Hanglejátszás | `pygame.mixer` (egyszeri inicializálás, pattogásmentes) |
| Mikrofon bemenet | `sounddevice` |
| Hangaktivitás-észlelés | `webrtcvad` |
| Billentyűzetfigyelés | `pynput` (nem kell rendszergazdai jog) |
| Rendszertálca | `pystray` + `Pillow` |
| Vágólap / beillesztés | `pyperclip` + Win32 `keybd_event` |

---

## Hibaelhárítás

| Probléma | Megoldás |
|---|---|
| `speak` eszköz nem elérhető Claude-ban | Ellenőrizd a `tts_server.py` útvonalat a `claude_desktop_config.json`-ban és indítsd újra a Claude Desktop-ot |
| Nincs hang | Ellenőrizd a hangszóróidat/fejhallgatódat. Teszteld: `python -c "import pygame; pygame.mixer.init(); print('OK')"` |
| STT nem ír át | Ellenőrizd, hogy a mikrofon működik és nincs némítva a Windows Hangbeállításokban |
| VAD reagál a háttérzajra | Növeld a `vad.volume_threshold` értéket, vagy használd a némítás gombot |
| Átírás zajleírásokat tartalmaz, pl. "(zene)" | Ez automatikusan szűrve van. Ha mégis előfordul, növeld a `vad.aggressiveness` értéket 3-ra |
| Több példány fut egyszerre | A companion beépített egypéldány-védelemmel rendelkezik. Zárd be az összes `python.exe` folyamatot és indítsd újra |
| `webrtcvad` telepítés sikertelen | Használd helyette: `pip install webrtcvad-wheels` |

---

## Készítők

A teljes kódbázist — mindkét Python szkriptet, a konfigurációt, a dokumentációt és a projekt architektúrát — Claude tervezte és írta a [Claude Code](https://claude.ai/claude-code) segítségével, ami az Anthropic ágens kódolási eszköze.

---

## Licensz

MIT — részletek a [LICENSE](LICENSE) fájlban.
