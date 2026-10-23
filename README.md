# Screenplay-to-Storyboard Generator

Convert a screenplay into a character-consistent storyboard in one pipeline.
Upload text, PDF, image, or voice → parse into shots → define characters → generate panels → export.

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Architecture overview](#architecture-overview)
3. [Screenplay template format](#screenplay-template-format)
4. [Project structure](#project-structure)
5. [Requirements](#requirements)
6. [Environment variables](#environment-variables)
7. [Installation](#installation)
   - [Python dependencies](#python-dependencies)
   - [Tesseract with Tamil language pack](#tesseract-with-tamil-language-pack)
8. [Running locally](#running-locally)
9. [Using the app](#using-the-app)
10. [API reference](#api-reference)
11. [Stubbed / credential-gated features](#stubbed--credential-gated-features)
12. [Troubleshooting](#troubleshooting)

---

## What it does

```
Screenplay text / PDF / image / voice
        ↓
  OCR or speech-to-text
        ↓
  LLM parses into structured shot list
        ↓
  Character references stored (upload / generate / built-in sketch)
        ↓
  SD 1.5 + IP-Adapter generates each panel, reusing character embedding
        ↓
  OpenCLIP scores visual consistency across panels
        ↓
  Export as PDF (one panel per page) or PPTX (four panels per slide)
        ↓
  Share via a plain URL
```

---

## Architecture overview

```
Browser (plain HTML / CSS / JS)
  │  REST + multipart/form-data over HTTP
  ▼
FastAPI  (main.py + backend/api.py)
  │
  ├─ OCR         backend/ocr.py          Tesseract (tam+eng) · PaddleOCR (fallback)
  ├─ Voice       backend/voice.py        Sarvam AI speech-to-text
  ├─ Parser      backend/parser.py       Groq LLM → structured JSON shot list
  ├─ Character   backend/character.py    Reference storage · embedding management
  ├─ ImageGen    backend/imagegen.py     SD 1.5 fp16 · attention-sliced · CLIP embedding
  ├─ Consistency backend/consistency.py  OpenCLIP cosine similarity across panels
  ├─ Assembly    backend/assembly.py     PIL composite storyboard sheet
  ├─ Export      backend/export.py       ReportLab PDF · python-pptx PPTX
  └─ Database    backend/database.py     SQLite via SQLAlchemy
```

---

## Screenplay template format

The parser accepts freeform text but works best when the input already follows
this plain-text template.  The LLM validates and fills gaps automatically.

```
SCENE: <number> - <INT/EXT>. <LOCATION> - <DAY/NIGHT>
DESCRIPTION: <one-line scene description>

SHOT: <number>
TYPE: <wide|medium|close-up|extreme-close-up|over-the-shoulder|point-of-view>
ANGLE: <eye-level|high-angle|low-angle|bird's-eye|worm's-eye|dutch-angle>
CHAR: <CHARACTER NAME 1>, <CHARACTER NAME 2>
ACTION: <what happens in this shot>
MOOD: <happy|sad|tense|dramatic|peaceful|action|romantic|mysterious>
```

**Example**

```
SCENE: 1 - INT. COFFEE SHOP - DAY
DESCRIPTION: Two friends reunite after years apart.

SHOT: 1
TYPE: wide
ANGLE: eye-level
CHAR: MAYA, RAHUL
ACTION: Maya enters and spots Rahul at the corner table
MOOD: peaceful

SHOT: 2
TYPE: close-up
ANGLE: eye-level
CHAR: MAYA
ACTION: Maya's face lights up with joy
MOOD: happy
```

Unstructured screenplays are accepted too — the LLM will infer shot breaks,
types, and moods.  Inferred fields are not flagged separately in the current
MVP but can be reviewed via the **Edit** button on each panel.

---

## Project structure

```
capstone/
├── main.py                   FastAPI entry point
├── requirements.txt
├── .env.example              Template for all environment variables
├── .gitignore
├── README.md
│
├── backend/
│   ├── __init__.py
│   ├── api.py                All REST endpoints
│   ├── assembly.py           Storyboard sheet compositor
│   ├── character.py          Character reference management
│   ├── config.py             Pydantic-settings config loader
│   ├── consistency.py        OpenCLIP consistency scoring
│   ├── database.py           SQLAlchemy models + SQLite
│   ├── export.py             PDF (ReportLab) + PPTX (python-pptx)
│   ├── imagegen.py           SD 1.5 + IP-Adapter image generation
│   ├── ocr.py                Tesseract + PaddleOCR
│   ├── parser.py             Groq LLM script parser
│   ├── session.py            Cookie-based session / project ID
│   └── voice.py              Sarvam AI speech-to-text
│
├── static/
│   ├── index.html            Single-page frontend
│   ├── styles.css            Glassmorphic light-mode styles
│   ├── app.js                Vanilla JS application logic
│   ├── placeholder.png       Fallback image for ungenerated panels
│   └── sketches/             Auto-generated default character sketches
│
├── uploads/                  Created at runtime — uploaded files
└── outputs/                  Created at runtime — generated panels + exports
```

---

## Requirements

| Component | Minimum |
|-----------|---------|
| Python | 3.10+ |
| GPU (for image generation) | 4 GB VRAM (CUDA). CPU works but is very slow. |
| Tesseract | 4.x or 5.x |
| Tamil language pack | `tessdata` — `tam.traineddata` |
| Disk space | ~10 GB (SD 1.5 model weights + CLIP) |
| RAM | 8 GB |

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values.

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | **Yes** | Groq API key — get one free at https://console.groq.com |
| `SARVAM_API_KEY` | For voice input | Sarvam AI key — https://dashboard.sarvam.ai |
| `OCR_BACKEND` | No | `tesseract` (default) or `paddleocr` |
| `TESSERACT_LANGUAGES` | No | Default `tam+eng` |
| `GROQ_MODEL` | No | Default `llama-3.1-70b-versatile` |
| `SD_MODEL` | No | Default `runwayml/stable-diffusion-v1-5` |
| `USE_FP16` | No | `true` (default) — keeps VRAM usage low |
| `ENABLE_ATTENTION_SLICING` | No | `true` (default) |
| `DATABASE_URL` | No | Default `sqlite:///./storyboard.db` |
| `HOST` | No | Default `0.0.0.0` |
| `PORT` | No | Default `8000` |

### Where to get API keys

**Groq**
1. Sign up at https://console.groq.com
2. Go to **API Keys** → **Create API Key**
3. Copy the key into `GROQ_API_KEY`
4. The default model `llama-3.1-70b-versatile` is available on the free tier.
   Other supported models: `llama-3.1-8b-instant`, `mixtral-8x7b-32768`,
   `qwen-qwq-32b`.

**Sarvam AI**
1. Sign up at https://dashboard.sarvam.ai
2. Go to **API Keys** → create a new key
3. Copy into `SARVAM_API_KEY`
4. Supported language codes: `hi-IN`, `ta-IN`, `en-IN`, `bn-IN`, `te-IN`, `mr-IN`

---

## Installation

### Python dependencies

```bash
# 1. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 2. Upgrade pip
pip install --upgrade pip

# 3. Install all dependencies
pip install -r requirements.txt
```

> **PyTorch note** — the `requirements.txt` pins CPU-compatible wheels.
> For CUDA 11.8 replace the torch lines with:
> ```
> pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu118
> ```
> For CUDA 12.1 use `cu121` instead.

### Tesseract with Tamil language pack

**Windows**

1. Download the installer from https:// github.com/UB-Mannheim/tesseract/wiki
2. During installation check **Additional language data** → **Tamil**
3. Add the Tesseract install directory to your `PATH`
   (typically `C:\Program Files\Tesseract-OCR`)
4. Verify:
   ```powershell
   tesseract --version
   tesseract --list-langs   # should include "tam"
   ```

**Ubuntu / Debian**

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-tam tesseract-ocr-eng
```

**macOS (Homebrew)**

```bash
brew install tesseract
# Language packs live in /usr/local/share/tessdata (Intel) or
# /opt/homebrew/share/tessdata (Apple Silicon)
# Download tam.traineddata from:
# https://github.com/tesseract-ocr/tessdata/raw/main/tam.traineddata
# and place it in the tessdata directory above.
```

**Verify both languages work**

```bash
tesseract --list-langs
# Expected output includes:  eng  tam
```

---

## Running locally

```bash
# Make sure your .env is filled in
cp .env.example .env
# edit .env with your keys

# Run the server
python main.py
```

Or with Uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000 in your browser.

The first run downloads the SD 1.5 and CLIP model weights from Hugging Face
(~4–5 GB total). Subsequent runs use the local cache.

---

## Using the app

### Step-by-step workflow

1. **Landing page** — read the overview and see example storyboards.
   Click **Get Started**.

2. **Upload** (sidebar → Upload)
   - *Text tab* — paste your screenplay or click an example to load it.
   - *File tab* — drag-and-drop a PDF, image, or `.txt` file.
     Scanned images are processed with Tesseract (Tamil + English).
   - *Voice tab* — choose an audio file (WAV/MP3) and a language,
     then click **Transcribe & Upload** (requires `SARVAM_API_KEY`).
   - Click **Parse Screenplay →** at the bottom.

3. **Character Development** (sidebar → Characters)
   The parser extracts character names automatically.  For each character:
   - **Upload Image** — use a photo or illustration as the reference.
   - **Describe Appearance** — type a description; SD generates a reference.
   - **Default Sketch** — pick from the 6 built-in placeholder sketches.
   Click **Save Reference** for each character, then **Generate Storyboard**.

4. **Storyboard** (sidebar → Storyboard)
   - Panels appear in shot order with metadata labels.
   - **Edit** — change the action text, shot type, camera angle, or mood,
     then click **Regenerate Shot** to re-render only that panel.
   - **Alternatives** — asks the AI for 1–2 alternative angles/moods;
     click **Apply & Regenerate** to try one.
   - **Consistency** — scores how visually consistent each character is
     across all panels they appear in (0–100 %).
   - **Assemble Sheet** — composites all panels into one labelled PNG.
   - **Export PDF** — one panel per page, with metadata captions.
   - **Export PPTX** — four panels per slide (2 × 2 grid).
   - **Share** — copies a plain shareable URL to the clipboard.

---

## API reference

All endpoints are under `/api`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/template` | Screenplay template format |
| GET | `/api/default-sketches` | Built-in character sketch library |
| GET | `/api/project` | Get/create current project |
| POST | `/api/upload/text` | Upload screenplay as text |
| POST | `/api/upload/file` | Upload screenplay as file (OCR if image/PDF) |
| POST | `/api/upload/voice` | Upload and transcribe voice recording |
| POST | `/api/parse` | Parse screenplay into shots |
| POST | `/api/characters` | Create/update character reference |
| POST | `/api/generate` | Generate all storyboard panels |
| POST | `/api/shots/{n}/regenerate` | Regenerate a single shot |
| GET | `/api/shots/{n}/alternatives` | Get alternative angle suggestions |
| POST | `/api/assemble` | Assemble panels into storyboard sheet |
| GET | `/api/consistency` | Evaluate character consistency |
| POST | `/api/export/pdf` | Export storyboard as PDF |
| POST | `/api/export/pptx` | Export storyboard as PPTX |
| GET | `/api/export/{id}/download` | Download an exported file |
| POST | `/api/share` | Create shareable link |
| GET | `/api/share/{project_id}` | View a shared project |

Interactive docs: http://localhost:8000/docs

---

## Stubbed / credential-gated features

The following features run but require external credentials or hardware
that may not be present in every environment.

| Feature | Status | What happens without it |
|---------|--------|--------------------------|
| Groq LLM parsing | **Requires `GROQ_API_KEY`** | `/api/parse` returns HTTP 400 with a clear message |
| Sarvam voice input | **Requires `SARVAM_API_KEY`** | `/api/upload/voice` returns HTTP 400 with a clear message |
| SD 1.5 image generation | **Requires CUDA GPU (≥4 GB VRAM) or ~10 GB disk + patience on CPU** | Returns HTTP 500 with "Insufficient GPU memory…" if VRAM is too low; CPU fallback works but is very slow |
| Tesseract OCR | **Requires Tesseract + `tam.traineddata`** | Falls back to PaddleOCR if installed; returns HTTP 400 if both fail |
| PaddleOCR | Optional fallback | Only used if Tesseract fails or `OCR_BACKEND=paddleocr` |
| OpenCLIP consistency | Auto-downloaded on first use (~350 MB) | `/api/consistency` returns empty results if download fails |
| IP-Adapter conditioning | **Simplified implementation** | Full IP-Adapter requires additional projection weight files not included. The current implementation uses CLIP embeddings to augment the text prompt; a production build should load the official `h94/IP-Adapter` weights from Hugging Face |

### Running without a GPU (CPU-only mode)

Set `USE_FP16=false` in `.env` — float32 is required on CPU.
Image generation will be very slow (~10–30 min per panel on a modern CPU).
Everything else (OCR, parsing, export) works at normal speed.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'pytesseract'`**
→ Run `pip install -r requirements.txt` inside your virtual environment.

**`tesseract is not installed or it's not in your PATH`**
→ Install Tesseract and add it to PATH (see [Installation](#installation)).

**`Groq API key not configured`**
→ Copy `.env.example` to `.env` and set `GROQ_API_KEY`.

**`CUDA out of memory`**
→ Close other GPU applications, set `ENABLE_ATTENTION_SLICING=true`, or switch
to CPU by setting `USE_FP16=false` and restarting.

**PaddleOCR install errors on Windows**
→ Install Visual C++ Redistributable and run:
`pip install paddlepaddle paddleocr --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple`

**Empty text after OCR**
→ Ensure the image has sufficient resolution (≥300 DPI recommended) and that
the Tamil language pack is installed (`tesseract --list-langs` shows `tam`).

**Port 8000 already in use**
→ Set `PORT=8001` (or any free port) in `.env` and restart.
