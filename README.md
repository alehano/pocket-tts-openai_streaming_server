# PocketTTS OpenAI-Compatible Server

An OpenAI-compatible Text-to-Speech API server powered by [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts). Drop-in replacement for OpenAI's TTS API with support for streaming, custom voices, and voice cloning.

Tested and working fully with [WingmanAI by Shipbit](https://www.wingman-ai.com/). Due to low resource use, can be used for real time local text to speech even while playing intensive video games (even in VR!) with WingmanAI.

**Key Features:**

- 🎯 **OpenAI API Compatible** - Works with any OpenAI TTS client
- 🚀 **Real-time Streaming** - Low-latency audio generation
- 🎤 **150+ Community Voices** - Ready-to-use voice library included
- 🎭 **Voice Cloning** - Clone any voice from a short audio sample
- 🐳 **Docker Ready** - One-command deployment
- 💻 **Cross-platform** - Runs on Windows, macOS, and Linux
- ⚡ **CPU Optimized** - No GPU required
- 🎤 **Text pre-processing** - Clean text for words and symbols TTS usually has difficulty with, automatically
- 🌍 **Multi-language** - Per-request `language` (Pocket-TTS locales: English, French, German, Portuguese, Italian, Spanish); each locale loads its own model and stays in memory while running

## Installing Pocket-TTS with all languages

If you see an error about only `b6369a24.yaml` (English), your environment has an **old or minimal** `pocket-tts` wheel that does not ship the per-locale YAML files under `pocket_tts/config/`. Install a **current** release so those files exist (then this server can load `french_24l`, `german_24l`, etc.).

**1. Upgrade from PyPI (simplest)** — in the same venv you use for the streaming server:

```bash
source .venv/bin/activate   # or your venv
pip install -U "pocket-tts>=2.0.0"
# pocket-tts 2.x expects torch>=2.5; if pip errors, upgrade torch first:
pip install -U "torch>=2.5.0" "torchaudio>=2.5.0"
pip install -U "pocket-tts>=2.0.0"
```

**2. Check that all configs are present:**

```bash
python -c "import pathlib, pocket_tts; d=pathlib.Path(pocket_tts.__path__[0])/'config'; print(*sorted(p.stem for p in d.glob('*.yaml')))"
```

You should see names like `english`, `french_24l`, `german_24l`, `italian`, `portuguese`, `spanish_24l` (exact set matches the upstream repo).

**3. Install from a local clone** (same result as a full wheel, good for development):

```bash
git clone https://github.com/kyutai-labs/pocket-tts.git
cd pocket-tts
pip install -e .
```

Use that venv when you run `python server.py` or `./start.sh`.

First run for each language may still **download weights** from Hugging Face (~hundreds of MB per locale); ensure disk space and network access.

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/teddybear082/pocket-tts-openai_streaming_server.git
cd pocket-tts-openai_streaming_server

# Start the server
docker compose up -d

# View logs
docker compose logs -f
```

The server will be available at `http://localhost:49112`

**Custom Configuration:**

```bash
# Change port
POCKET_TTS_PORT=8080 docker compose up -d

# Use custom voices directory
POCKET_TTS_VOICES_DIR=/path/to/my/voices docker compose up -d

# Multi-language: default locale + optional extra models loaded at startup
# POCKET_TTS_DEFAULT_LANGUAGE=english
# POCKET_TTS_PRELOAD_LANGUAGES=french_24l,german_24l
```

### Option 2: Python (from source)

```bash
# Clone the repository
git clone https://github.com/teddybear082/pocket-tts-openai_streaming_server.git
cd pocket-tts-openai_streaming_server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
python server.py
```

**Command Line Options:**

```bash
python server.py --help

# Custom port and voices
python server.py --port 8080 --voices-dir ./my_voices

# Enable streaming by default
python server.py --stream

# Enable text preprocessing
python server.py --text-preprocess
```

### Option 3: Windows Executable

1. Download the latest release from [Releases](https://github.com/teddybear082/pocket-tts-openai_streaming_server/releases)
2. Extract the ZIP file
3. Double-click `PocketTTS-Server.exe` to run with defaults
4. Or run `run_pocket_tts_server_exe.bat` for custom configuration

## Web Interface

Open `http://localhost:49112` in your browser to access the built-in web UI:

- Select from available voices
- Enter text to synthesize
- Listen to generated audio directly

## API Usage

### Multi-language behavior

Pocket-TTS loads **one acoustic model per language**. This server keeps each loaded language in memory for the lifetime of the process (voice embeddings are cached per language + voice).

- **Default (no `POCKET_TTS_MODEL_PATH`):** “multi-language” mode. The server loads `POCKET_TTS_DEFAULT_LANGUAGE` (and any `POCKET_TTS_PRELOAD_LANGUAGES`) at startup. Any other language is loaded on first use.
- **Single config (`POCKET_TTS_MODEL_PATH` or bundled YAML):** one fixed model. The `language` field on `POST /v1/audio/speech` is **ignored** (same as upstream OpenAI clients that only send `voice` / `input`).

Supported language identifiers match [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts): canonical ids include `english`, `french_24l`, `german_24l`, `portuguese`, `italian`, `spanish_24l`. The API also accepts **BCP-47 tags** (e.g. `fr-FR`, `en-US`) and short ISO codes (`fr`, `de`, …) and maps them to those ids.

**List supported ids:** `GET /v1/languages`

### Generate Speech

**Endpoint:** `POST /v1/audio/speech`

```bash
curl http://localhost:49112/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "Hello world! This is a test.",
    "voice": "alba"
  }' \
  --output speech.mp3
```

French example (multi-language mode):

```bash
curl http://localhost:49112/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Bonjour le monde.",
    "voice": "alba",
    "language": "fr-FR"
  }' \
  --output speech-fr.mp3
```

### Python Client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:49112/v1",
    api_key="not-needed"  # No authentication required
)

# Generate and save audio
response = client.audio.speech.create(
    model="tts-1",
    voice="alba",
    input="Hello world! This is a test."
)
response.stream_to_file("output.mp3")

# Streaming
with client.audio.speech.with_streaming_response.create(
    model="tts-1",
    voice="alba",
    input="This is streaming audio.",
    response_format="pcm"
) as response:
    for chunk in response.iter_bytes():
        # Process audio chunks in real-time
        pass
```

The official OpenAI Python client does not expose a `language` field for TTS. To pass it, use `httpx`/`requests` against `POST /v1/audio/speech` with a JSON body that includes `"language": "de-DE"` (or a canonical id), or a client that allows extra JSON keys.

### API Reference

| Endpoint            | Method | Description                                      |
| ------------------- | ------ | ------------------------------------------------ |
| `/`                 | GET    | Web interface                                    |
| `/health`           | GET    | Health check; includes `default_language`, `loaded_languages` in multi-language mode |
| `/v1/voices`        | GET    | List available voices                            |
| `/v1/languages`     | GET    | List supported Pocket-TTS language ids             |
| `/v1/audio/speech`  | POST   | Generate speech audio                            |

**Speech Parameters:**

| Parameter         | Type    | Required | Default | Description                                        |
| ----------------- | ------- | -------- | ------- | -------------------------------------------------- |
| `model`           | string  | No       | -       | Ignored (for OpenAI compatibility)                 |
| `input`           | string  | Yes      | -       | Text to synthesize                                 |
| `voice`           | string  | No       | `alba`  | Voice ID (see `/v1/voices`)                        |
| `language`        | string  | No       | -       | Pocket-TTS language id or BCP-47 (multi-language mode only; see above) |
| `response_format` | string  | No       | `mp3`   | Output format: `mp3`, `wav`, `pcm`, `opus`, `flac` |
| `stream`          | boolean | No       | `false` | Enable streaming response                          |

## Custom Voices

### Using Custom Voice Files

1. **Create a voices directory** with your audio files (`.wav`, `.mp3`, `.flac`)
2. **Configure the server** to use your directory:

   **Docker:**

   ```bash
   POCKET_TTS_VOICES_DIR=/path/to/voices docker compose up -d
   ```

   **Python:**

   ```bash
   python server.py --voices-dir /path/to/voices
   ```

   **Windows EXE:**
   Use the batch launcher and specify the voices directory when prompted.

3. **Use your voice** by filename:
   ```json
   { "voice": "my_voice.wav", "input": "Hello!" }
   ```

### Voice File Guidelines

- **Duration:** 3-15 seconds of clear speech works best
- **Quality:** Clean audio without background noise
- **Format:** WAV, MP3, or FLAC
- **Tip:** Use [Adobe Podcast Enhance](https://podcast.adobe.com/enhance) to clean noisy samples

### Built-in Voices

The following voices are available by default:
`alba`, `marius`, `javert`, `jean`, `fantine`, `cosette`, `eponine`, `azelma`

The `voices/` directory includes 150+ community-contributed voices.

## Configuration

### Environment Variables

| Variable                            | Default    | Description                            |
| ------------------------------------| ---------- | -------------------------------------- |
| `POCKET_TTS_HOST`                   | `0.0.0.0`  | Server bind address                    |
| `POCKET_TTS_PORT`                   | `49112`    | Server port                            |
| `POCKET_TTS_VOICES_DIR`             | `./voices` | Custom voices directory                |
| `POCKET_TTS_MODEL_PATH`             | -          | If set, load this YAML only (single-model mode; `language` on requests ignored) |
| `POCKET_TTS_DEFAULT_LANGUAGE`       | `english`  | Default Pocket-TTS language id when `MODEL_PATH` is unset |
| `POCKET_TTS_PRELOAD_LANGUAGES`      | -          | Comma-separated ids to load at startup (e.g. `french_24l,spanish_24l`) |
| `POCKET_TTS_STREAM_DEFAULT`         | `true`     | Enable streaming by default            |
| `POCKET_TTS_TEXT_PREPROCESS_DEFAULT`| `true`     | Enable text preprocessing by default   |
| `POCKET_TTS_LOG_LEVEL`              | `INFO`     | Log level: DEBUG, INFO, WARNING, ERROR |
| `POCKET_TTS_LOG_DIR`                | `./logs`   | Log files directory                    |
| `HF_TOKEN`                          | -          | Hugging Face token (for voice cloning) |

### Docker Compose Options

See [docker-compose.yml](docker-compose.yml) for all available options including:

- Volume mounts for custom voices
- Resource limits
- Health check configuration
- HuggingFace cache persistence

## Project Structure

```
pocket-tts-openai_streaming_server/
├── app/                    # Application modules
│   ├── __init__.py        # Flask app factory
│   ├── config.py          # Configuration management
│   ├── language_normalize.py  # BCP-47 / aliases → Pocket-TTS language ids
│   ├── logging_config.py  # Logging setup
│   ├── routes.py          # API endpoints
│   └── services/          # Business logic
│       ├── audio.py       # Audio conversion
│       ├── preprocess.py  # Text preprocessor
│       └── tts.py         # TTS service (per-language models + voice cache)
├── static/                 # Web UI assets
├── templates/              # HTML templates
├── voices/                 # Voice files
├── server.py              # Main entry point
├── Dockerfile             # Container build
├── docker-compose.yml     # Container orchestration
└── requirements.txt       # Python dependencies
```

## Development

### Dependencies

| File                   | Purpose                                              |
| ---------------------- | ---------------------------------------------------- |
| `requirements.txt`     | Runtime dependencies only (Flask, torch, pocket-tts) |
| `requirements-dev.txt` | Adds dev tools: ruff (linting), pytest (testing)     |

### Running Locally

```bash
# Install runtime dependencies only
pip install -r requirements.txt

# Optional: use a nearby checkout of kyutai-labs/pocket-tts instead of PyPI
# pip install -e ../pocket-tts

# Or install with dev tools (recommended for contributors)
pip install -r requirements-dev.txt

# Run with debug logging
python server.py --log-level DEBUG
```

### Linting

```bash
pip install ruff
ruff check .
ruff format .
```

### Building Windows EXE

```bash
pip install pyinstaller
pyinstaller --onefile --name PocketTTS-Server \
  --add-data "static;static" \
  --add-data "templates;templates" \
  --add-data "voices;voices" \
  --add-data "app;app" \
  server.py
```

## Troubleshooting

### High memory use with multiple languages

Each Pocket-TTS language is a separate model in RAM. Prefer `POCKET_TTS_PRELOAD_LANGUAGES` only for locales you need at startup, or let rarely used languages load on first request and size the container/VM accordingly.

### `TTSModel.load_model() got an unexpected keyword argument 'language'`

Your installed `pocket-tts` is older than the API that accepts `language=`. This server falls back to loading `pocket_tts/config/<language>.yaml` via `config=` automatically (see `load_model_for_language` in `app/services/tts.py`). Upgrade when convenient: `pip install -U "pocket-tts>=1.1.1"`, or install from a [local clone](https://github.com/kyutai-labs/pocket-tts) with `pip install -e /path/to/pocket-tts`.

### `no config english.yaml` but `b6369a24` (or one yaml) is available

Some wheels bundle a **single** hash-named YAML (English only). The server maps **`english`** to that file automatically. Other languages require a full Pocket-TTS install with per-locale configs (`french_24l.yaml`, etc.).

### Model Loading Takes Long

First run downloads the model (~500MB). Subsequent runs use cached model.

**Docker:** Model cache is persisted in a Docker volume.

### Voice Cloning Requires HF Token

For voice cloning, you may need a Hugging Face token:

1. Get token from https://huggingface.co/settings/tokens
2. Set `HF_TOKEN` environment variable

### Port Already in Use

```bash
# Use a different port
python server.py --port 8080

# Or with Docker
POCKET_TTS_PORT=8080 docker compose up -d
```

## Credits

- [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts) by Kyutai Labs
- Community voice contributors (see [voices/credits.txt](voices/credits.txt))

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

Pocket-TTS is subject to its own license terms.
