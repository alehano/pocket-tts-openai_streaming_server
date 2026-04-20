"""
TTS Service - handles model loading, voice management, and audio generation.
"""

from __future__ import annotations

import inspect
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import torch

from app.config import Config
from app.language_normalize import normalize_language, parse_preload_list
from app.logging_config import get_logger

logger = get_logger('tts')


def _pocket_configs_dir() -> Path:
    try:
        from pocket_tts.utils.config import CONFIGS_DIR

        return Path(CONFIGS_DIR)
    except Exception:
        import pocket_tts

        return Path(pocket_tts.__path__[0]) / "config"


def load_model_for_language(tts_model_cls, canonical_lang: str):
    """
    Load TTSModel for a language id across pocket-tts versions: `language=` when
    available, else `config=<pocket_tts/config/<lang>.yaml>`.

    Some PyPI wheels ship only a single hash-named yaml (e.g. ``b6369a24.yaml``) for
    English; we use that when ``canonical_lang == "english"``.
    """
    sig = inspect.signature(tts_model_cls.load_model)
    if "language" in sig.parameters:
        return tts_model_cls.load_model(language=canonical_lang)

    cfg_dir = _pocket_configs_dir()
    cfg_path = cfg_dir / f"{canonical_lang}.yaml"
    if cfg_path.is_file():
        if "config" in sig.parameters:
            return tts_model_cls.load_model(config=cfg_path)
        raise RuntimeError("pocket-tts TTSModel.load_model has no `config` parameter")

    # Single bundled config (common on older/minimal wheels) — treat as English only.
    yamls = sorted(cfg_dir.glob("*.yaml"))
    if len(yamls) == 1:
        if canonical_lang != "english":
            raise FileNotFoundError(
                f"This pocket-tts install only ships {yamls[0].name} (English). "
                f"Cannot load language {canonical_lang!r}. "
                "Install a current kyutai-labs/pocket-tts (see README) for french_24l, german_24l, etc."
            )
        logger.info(
            "Using single bundled config %s as English (minimal pocket-tts wheel)",
            yamls[0].name,
        )
        if "config" in sig.parameters:
            return tts_model_cls.load_model(config=yamls[0])

    available = sorted(p.stem for p in yamls)
    raise FileNotFoundError(
        f"pocket-tts: no config {cfg_path.name} under {cfg_dir}. "
        f"Available: {', '.join(available) if available else '(none)'}"
    )

# Lazy import pocket_tts to allow for better error handling
TTSModel = None


def _ensure_pocket_tts():
    """Ensure pocket-tts is imported."""
    global TTSModel
    if TTSModel is None:
        try:
            from pocket_tts import TTSModel as _TTSModel

            TTSModel = _TTSModel
        except ImportError as exc:
            raise ImportError('pocket-tts not found. Install with: pip install pocket-tts') from exc


class TTSService:
    """
    Service class for Text-to-Speech operations.
    Manages model loading (one pocket-tts model per language by default), voice caching, and audio generation.
    """

    def __init__(self):
        self.models: dict[str, object] = {}
        self.voice_cache: dict[tuple[str, str], dict] = {}
        self.voices_dir: str | None = None
        self._model_loaded = False
        self._single_model_mode = False
        self._default_language = 'english'
        self._load_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        """Check if at least one model is loaded."""
        return self._model_loaded and bool(self.models)

    @property
    def default_language(self) -> str:
        return self._default_language

    @property
    def loaded_languages(self) -> list[str]:
        """Canonical language ids currently in memory (empty in single-config mode)."""
        if self._single_model_mode:
            return []
        return sorted(self.models.keys())

    @property
    def sample_rate(self) -> int:
        """Sample rate from the primary model (default language or single config)."""
        m = self._primary_model()
        if m is not None:
            return m.sample_rate
        return 24000

    @property
    def device(self) -> str:
        m = self._primary_model()
        if m is not None:
            return str(m.device)
        return 'unknown'

    def _primary_model(self):
        if self._single_model_mode:
            return self.models.get('__single__')
        return self.models.get(self._default_language)

    def load_model(self, model_path: str | None = None) -> None:
        """
        Load TTS model(s).

        If `model_path` points to a YAML config, loads that single model (language parameter ignored).
        Otherwise loads pocket-tts per-language checkpoints; see `POCKET_TTS_DEFAULT_LANGUAGE`
        and `POCKET_TTS_PRELOAD_LANGUAGES`.
        """
        _ensure_pocket_tts()

        logger.info('Loading Pocket TTS...')
        t0 = time.time()

        effective_path = model_path
        if not effective_path:
            _, bundle_model = Config.get_bundle_paths()
            if bundle_model and os.path.isfile(bundle_model):
                effective_path = bundle_model
                logger.info(f'Using bundled model: {effective_path}')

        try:
            if effective_path:
                logger.info(f'Single-model mode (config file): {effective_path}')
                self._single_model_mode = True
                self.models['__single__'] = TTSModel.load_model(config=effective_path)
                self._model_loaded = True
                load_time = time.time() - t0
                logger.info(
                    f'Model loaded in {load_time:.2f}s. Device: {self.device}, '
                    f'Sample rate: {self.sample_rate}'
                )
                return

            self._single_model_mode = False
            self._default_language = normalize_language(Config.DEFAULT_LANGUAGE, 'english')

            preload: set[str] = {self._default_language}
            preload.update(parse_preload_list(Config.PRELOAD_LANGUAGES))

            for lang in sorted(preload):
                self._ensure_model_loaded(lang)

            self._model_loaded = True
            load_time = time.time() - t0
            logger.info(
                f'Multi-language mode: loaded {sorted(self.models.keys())} in {load_time:.2f}s. '
                f'Device: {self.device}, Sample rate: {self.sample_rate}'
            )

        except Exception as e:
            logger.error(f'Failed to load model: {e}')
            raise

    def _ensure_model_loaded(self, canonical_lang: str):
        with self._load_lock:
            if canonical_lang in self.models:
                return self.models[canonical_lang]

            logger.info(f'Loading Pocket TTS weights for language={canonical_lang!r}...')
            t0 = time.time()
            model = load_model_for_language(TTSModel, canonical_lang)
            self.models[canonical_lang] = model
            load_time = time.time() - t0
            logger.info(
                f'Language {canonical_lang} ready in {load_time:.2f}s '
                f'(device={model.device}, sample_rate={model.sample_rate})'
            )
            return model

    def model_for_language_key(self, language_key: str):
        """Return the torch model for a canonical language id (or single-config model)."""
        if self._single_model_mode:
            return self.models['__single__']
        return self.models[language_key]

    def set_voices_dir(self, voices_dir: str | None) -> None:
        """
        Set the directory for custom voice files.

        Args:
            voices_dir: Path to directory containing voice files
        """
        if voices_dir and os.path.isdir(voices_dir):
            self.voices_dir = voices_dir
            logger.info(f'Voices directory set to: {voices_dir}')
        elif voices_dir:
            logger.warning(f'Voices directory not found: {voices_dir}')
            self.voices_dir = None
        else:
            self.voices_dir = None

    def get_voice_state(self, voice_id_or_path: str, language: str | None = None) -> tuple[str, dict]:
        """
        Resolve voice ID to a model state with caching.

        Returns:
            (canonical_language_key, voice_state) — use the same language key for generation.
        """
        if self._single_model_mode:
            lang_key = '__single__'
            model = self.models['__single__']
        else:
            lang_key = normalize_language(language, self._default_language)
            model = self._ensure_model_loaded(lang_key)

        resolved_key = self._resolve_voice_path(voice_id_or_path)
        cache_key = (lang_key, resolved_key)

        if cache_key in self.voice_cache:
            logger.debug(f'Using cached voice state for: {cache_key}')
            return lang_key, self.voice_cache[cache_key]

        logger.info(f'Loading voice: {resolved_key} (language={lang_key})')
        t0 = time.time()

        try:
            state = model.get_state_for_audio_prompt(resolved_key)
            self.voice_cache[cache_key] = state
            load_time = time.time() - t0
            logger.info(f'Voice loaded in {load_time:.2f}s: {resolved_key}')
            return lang_key, state

        except Exception as e:
            logger.error(f"Failed to load voice '{voice_id_or_path}': {e}")
            raise ValueError(f"Voice '{voice_id_or_path}' could not be loaded: {e}") from e

    def _resolve_voice_path(self, voice_id_or_path: str) -> str:
        """
        Resolve a voice identifier to its actual path or ID.

        Args:
            voice_id_or_path: Voice identifier

        Returns:
            Resolved path or identifier

        Raises:
            ValueError: If unsafe URL scheme is used
        """
        # Block potentially dangerous URL schemes (SSRF protection)
        if voice_id_or_path.startswith(('http://', 'https://')):
            raise ValueError(
                f'URL scheme not allowed for security reasons: {voice_id_or_path[:50]}. '
                "Use 'hf://' for HuggingFace models or provide a local file path."
            )

        # Allow HuggingFace URLs
        if voice_id_or_path.startswith('hf://'):
            return voice_id_or_path

        # Check if it's a built-in voice
        if voice_id_or_path.lower() in Config.BUILTIN_VOICES:
            return voice_id_or_path.lower()

        # Check voices directory
        if self.voices_dir:
            for ext in Config.VOICE_EXTENSIONS:
                # Try exact match first
                possible_path = os.path.join(self.voices_dir, voice_id_or_path)
                if os.path.exists(possible_path):
                    return os.path.abspath(possible_path)

                # Try with extension
                if not voice_id_or_path.endswith(ext):
                    possible_path = os.path.join(self.voices_dir, voice_id_or_path + ext)
                    if os.path.exists(possible_path):
                        return os.path.abspath(possible_path)

        # Check if it's an absolute path that exists
        if os.path.isabs(voice_id_or_path) and os.path.exists(voice_id_or_path):
            return voice_id_or_path

        # Return as-is, let pocket-tts handle it
        return voice_id_or_path

    def validate_voice(self, voice_id_or_path: str) -> tuple[bool, str]:
        """
        Validate if a voice can be loaded (fast check without full loading).

        Args:
            voice_id_or_path: Voice identifier

        Returns:
            Tuple of (is_valid, message)
        """
        # Block unsafe URL schemes first
        if voice_id_or_path.startswith(('http://', 'https://')):
            return (
                False,
                'HTTP/HTTPS URLs are not allowed for security reasons. Use hf:// for HuggingFace models.',
            )

        try:
            resolved = self._resolve_voice_path(voice_id_or_path)
        except ValueError as e:
            return False, str(e)

        # Built-in voices are always valid
        if resolved.lower() in Config.BUILTIN_VOICES:
            return True, f'Built-in voice: {resolved}'

        # HuggingFace URLs - assume valid
        if resolved.startswith('hf://'):
            return True, f'HuggingFace voice: {resolved}'

        # Local file - check existence
        if os.path.exists(resolved):
            return True, f'Local voice file: {resolved}'

        return False, f'Voice not found: {voice_id_or_path}'

    def generate_audio(self, voice_state: dict, text: str, language_key: str) -> torch.Tensor:
        """
        Generate complete audio for given text.

        Args:
            voice_state: Model state from get_voice_state()
            text: Text to synthesize
            language_key: Canonical language id from get_voice_state(), or '__single__'
        """
        if not self.is_loaded:
            raise RuntimeError('Model not loaded')

        model = self.model_for_language_key(language_key)
        t0 = time.time()
        audio = model.generate_audio(voice_state, text)
        gen_time = time.time() - t0

        logger.info(f'Generated {len(text)} chars in {gen_time:.2f}s')
        return audio

    def generate_audio_stream(
        self, voice_state: dict, text: str, language_key: str
    ) -> Iterator[torch.Tensor]:
        """
        Generate audio in streaming chunks.

        Args:
            voice_state: Model state from get_voice_state()
            text: Text to synthesize
            language_key: Canonical language id from get_voice_state(), or '__single__'
        """
        if not self.is_loaded:
            raise RuntimeError('Model not loaded')

        model = self.model_for_language_key(language_key)
        logger.info(f'Starting streaming generation for {len(text)} chars')
        yield from model.generate_audio_stream(voice_state, text)

    def list_voices(self) -> list[dict]:
        """
        List all available voices.

        Returns:
            List of voice dictionaries with 'id' and 'name' keys
        """
        voices = []

        # Built-in voices (sorted alphabetically)
        builtin_sorted = sorted(Config.BUILTIN_VOICES)
        for voice in builtin_sorted:
            voices.append({'id': voice, 'name': voice.capitalize(), 'type': 'builtin'})

        # Custom voices from directory
        custom_voices = []
        if self.voices_dir and os.path.isdir(self.voices_dir):
            voice_dir = Path(self.voices_dir)

            # Collect all valid files
            voice_files = []
            for ext in Config.VOICE_EXTENSIONS:
                voice_files.extend(voice_dir.glob(f'*{ext}'))

            # Sort alphabetically by filename
            voice_files.sort(key=lambda f: f.name.lower())

            for voice_file in voice_files:
                # Format name: "bobby_mcfern" -> "Bobby Mcfern"
                clean_name = voice_file.stem.replace('_', ' ').replace('-', ' ').title()

                custom_voices.append(
                    {
                        'id': voice_file.name,
                        'name': clean_name,
                        'type': 'custom',
                    }
                )

        voices.extend(custom_voices)
        return voices


# Global service instance
_tts_service: TTSService | None = None


def get_tts_service() -> TTSService:
    """Get the global TTS service instance."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
