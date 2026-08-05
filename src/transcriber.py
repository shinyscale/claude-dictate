"""
Whisper transcription module for Claude Dictate.

Backend priority:
  1. faster-whisper on CUDA  -- CTranslate2 kernels, ~30x realtime on the RTX PRO 6000
  2. whisper.cpp executable   -- if one is configured/on PATH
  3. openai-whisper (Python)  -- last-resort CPU fallback

The faster-whisper model is cached at module level so a long-lived process
(tray daemon) pays the load cost once and every subsequent hotkey press hits a
model that is already resident in VRAM.
"""

import difflib
import os
import re
import subprocess
import shutil
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

# faster-whisper accepts its own model ids; translate the legacy names the
# config/UI still hand us so old settings files keep working.
_MODEL_ALIASES = {
    "large": "large-v3",
    "large.en": "large-v3",
    "turbo": "large-v3-turbo",
}

DEFAULT_FW_MODEL = "large-v3-turbo"

# (model, device, compute_type) -> WhisperModel. Guarded because the tray
# daemon may transcribe from a worker thread while the UI thread preloads.
_model_cache = {}
_model_lock = threading.Lock()


def build_initial_prompt(terms: Optional[List[str]]) -> str:
    """
    Turn a vocabulary list into a Whisper initial_prompt.

    Whisper conditions the decoder on this text as if it were the transcript
    of the preceding audio, which biases it toward these spellings. It is a
    nudge, not a constraint -- the model can still emit anything -- so the
    prompt reads as a plain sentence rather than a bare word list, which is
    what the decoder was trained on.
    """
    cleaned = [t.strip() for t in (terms or []) if t and t.strip()]
    if not cleaned:
        return ""
    return "Glossary for this recording: " + ", ".join(cleaned) + "."


def apply_corrections(text: str, corrections: Optional[Dict[str, str]]) -> str:
    """
    Deterministic post-decode fix-ups for words Whisper reliably mangles.

    Matched case-insensitively on word boundaries. Longer keys are applied
    first so a two-word phrase wins over a single-word key nested inside it.
    """
    if not text or not corrections:
        return text
    for wrong in sorted(corrections, key=len, reverse=True):
        right = corrections[wrong]
        pattern = r"\b" + re.escape(wrong) + r"\b"
        text = re.sub(pattern, right, text, flags=re.IGNORECASE)
    return text


_PUNCT_WORDS = re.compile(
    r"\b(exclamation\s+(?:point|mark)|question\s+mark)\b", re.IGNORECASE
)

# Stock phrases Whisper emits into dead air. They come from caption-heavy
# training data (YouTube sign-offs, subtitle credits), not from the mic.
_FILLER_HALLUCINATIONS = {
    "thank you", "thank you very much", "thanks for watching",
    "thank you for watching", "please subscribe", "like and subscribe",
    "see you next time", "bye", "bye bye", "goodbye", "you", "okay", "ok",
    "hello", "hello everyone", "hello good morning", "good morning",
    "subtitles by the amara org community", "transcription by castingwords",
    "subs by www zeoranger co uk", "amara org", "music", "applause",
    "foreign", "thanks", "thank you so much",
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation -- for filler and duplicate matching."""
    return re.sub(r"[^\w\s]", "", text).strip().lower()


def _similar(a: str, b: str, ratio: float = 0.92) -> bool:
    """Near-identical normalized text (decoder loops rarely repeat exactly)."""
    return bool(a) and bool(b) and difflib.SequenceMatcher(None, a, b).ratio() > ratio


def filter_segments(
    segments,
    gap_cut: float = 3.0,
    min_logprob: float = -1.0,
    max_no_speech: float = 0.6,
    verbose: bool = True,
):
    """
    Drop the text Whisper invents after the speaker stops talking.

    Hold-to-talk clips end with dead air: the user finishes a thought but
    keeps the key held. Fed that, the decoder produces fluent, confident,
    entirely fabricated sentences -- often drifting language or reciting
    caption boilerplate. Three independent guards, since any one of them
    can miss:

      1. Trailing cut: once a low-confidence segment appears after a long
         silence gap, everything from there on is post-speech noise.
      2. Filler phrases: caption boilerplate is dropped when it is
         isolated or low-confidence (a genuine spoken "thank you" that is
         confident and continuous with the speech survives).
      3. Duplicate collapse: the decoder loops on near-silence, repeating
         the previous sentence verbatim.

    Returns (kept_texts, dropped_notes).
    """
    kept, dropped = [], []
    prev_end = None
    cut = False

    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue

        logprob = getattr(seg, "avg_logprob", 0.0) or 0.0
        no_speech = getattr(seg, "no_speech_prob", 0.0) or 0.0
        start = getattr(seg, "start", 0.0) or 0.0
        gap = (start - prev_end) if prev_end is not None else 0.0
        weak = logprob < min_logprob or no_speech > max_no_speech
        norm = _normalize(text)

        if cut:
            dropped.append(f"after-cut {text[:40]!r}")
            continue

        if kept and gap >= gap_cut and weak:
            cut = True
            dropped.append(
                f"trailing (gap {gap:.1f}s, logprob {logprob:.2f}) {text[:40]!r}"
            )
            continue

        if norm in _FILLER_HALLUCINATIONS and (weak or gap >= 1.5 or not kept):
            dropped.append(f"filler {text[:40]!r}")
            continue

        # Back-to-back repeats are always the decoder looping. A repeat of
        # something said earlier is only suspect when it is weak or arrives
        # after a pause -- people do legitimately restate a point mid-flow.
        if kept and _similar(norm, _normalize(kept[-1])):
            dropped.append(f"duplicate {text[:40]!r}")
            continue
        if (weak or gap >= 1.5) and any(
            _similar(norm, _normalize(k)) for k in kept[:-1]
        ):
            dropped.append(f"echo of earlier line {text[:40]!r}")
            continue

        kept.append(text)
        prev_end = getattr(seg, "end", start) or start

    if dropped and verbose:
        for note in dropped:
            print(f"[Whisper] dropped {note}")

    return kept, dropped


def apply_spoken_punctuation(text: str) -> str:
    """
    Convert spoken 'exclamation point' / 'question mark' into the symbols.

    Attachment depends on position. At the start of the text or of a sentence
    the mark is a prefix sigil and glues to the NEXT word ("exclamation point
    opus" -> "!opus", the Telegram model-routing case). Anywhere else it
    terminates the PREVIOUS word ("ship it exclamation point" -> "ship it!"),
    also swallowing the duplicate terminator Whisper tends to add after the
    spoken words ("... exclamation point." would otherwise become "...!.").

    Deliberately limited to these two marks: spoken commas/periods are far
    more likely to appear as ordinary words than as dictated punctuation.
    """
    if not text:
        return text

    out = []
    pos = 0
    for m in _PUNCT_WORDS.finditer(text):
        symbol = "!" if m.group(1).lower().startswith("exclamation") else "?"
        before = text[pos:m.start()]
        context = text[:m.start()].rstrip()
        end = m.end()

        if not context or context[-1] in ".!?\n":
            # Prefix sigil: keep leading whitespace, glue symbol to what follows.
            out.append(before)
            out.append(symbol)
            while end < len(text) and text[end] == " ":
                end += 1
        else:
            # Terminator: glue symbol to what precedes, drop any duplicate
            # punctuation Whisper appended, restore a single space if the
            # sentence continues.
            out.append(before.rstrip())
            out.append(symbol)
            while end < len(text) and text[end] == " ":
                end += 1
            if end < len(text) and text[end] in ".,!?":
                end += 1
                while end < len(text) and text[end] == " ":
                    end += 1
            if end < len(text):
                out.append(" ")
        pos = end

    out.append(text[pos:])
    return "".join(out)


def _load_faster_whisper(model: str, device: str, compute_type: str):
    """Get (or build) a cached faster-whisper model. Raises if unavailable."""
    key = (model, device, compute_type)
    with _model_lock:
        if key not in _model_cache:
            from faster_whisper import WhisperModel
            _model_cache[key] = WhisperModel(
                model, device=device, compute_type=compute_type
            )
        return _model_cache[key]


def cuda_available() -> bool:
    """True if CTranslate2 can see a usable CUDA device."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperTranscriber:
    """Handles transcription, preferring GPU faster-whisper."""

    def __init__(
        self,
        whisper_path: str = "",
        model: str = "base.en",
        language: str = "en",
        on_progress: Optional[Callable[[float, str], None]] = None,
        device: str = "auto",
        compute_type: str = "float16",
        vocabulary: Optional[List[str]] = None,
        corrections: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            whisper_path: Path to a whisper.cpp executable (auto-detected if empty)
            model: Whisper model id (base.en, small.en, large-v3, large-v3-turbo, ...)
            language: Language code for transcription
            on_progress: Callback (progress 0-1, status message)
            device: "auto" | "cuda" | "cpu" for the faster-whisper backend
            compute_type: CTranslate2 compute type (float16 on CUDA, int8 on CPU)
            vocabulary: Personal jargon to bias the decoder toward
            corrections: Misheard -> correct map applied after decoding
        """
        self.whisper_path = whisper_path or self._find_whisper()
        self.model = model
        self.language = language
        self.model_path = self._get_model_path()
        self.on_progress = on_progress
        self.vocabulary = list(vocabulary or [])
        self.corrections = dict(corrections or {})

        if device == "auto":
            device = "cuda" if cuda_available() else "cpu"
        self.device = device
        self.compute_type = compute_type if device == "cuda" else "int8"

    # -- backend selection -------------------------------------------------

    @property
    def fw_model_name(self) -> str:
        """The model id to hand faster-whisper."""
        return _MODEL_ALIASES.get(self.model, self.model)

    @property
    def initial_prompt(self) -> str:
        """Decoder-bias prompt built from the personal vocabulary."""
        return build_initial_prompt(self.vocabulary)

    def preload(self) -> bool:
        """
        Warm the GPU model so the first dictation isn't stuck behind a load.

        Safe to call from a background thread at startup. Returns True if a
        faster-whisper model is resident afterwards.
        """
        try:
            _load_faster_whisper(self.fw_model_name, self.device, self.compute_type)
            return True
        except Exception as e:
            print(f"faster-whisper preload failed: {e}")
            return False

    # -- transcription -----------------------------------------------------

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file, returning the text."""
        if self.on_progress:
            self.on_progress(0.0, "Starting transcription...")

        text = self._transcribe_faster_whisper(audio_path)

        if text is None:
            if not self.whisper_path:
                if self.on_progress:
                    self.on_progress(0.1, "Using Python whisper fallback...")
                text = self._transcribe_fallback(audio_path)
            else:
                text = self._transcribe_whisper_cpp(audio_path)

        # Single exit point so corrections are applied exactly once, whichever
        # backend produced the text.
        text = apply_corrections(text, self.corrections)
        return apply_spoken_punctuation(text)

    def _transcribe_faster_whisper(self, audio_path: str) -> Optional[str]:
        """
        Primary path: CTranslate2. Returns None (not "") on backend failure so
        the caller can tell "backend unavailable" from "you said nothing".
        """
        try:
            if self.on_progress:
                self.on_progress(0.2, f"Transcribing on {self.device.upper()}...")

            model = _load_faster_whisper(
                self.fw_model_name, self.device, self.compute_type
            )
            segments, _info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=1,
                # Hold-to-talk clips are bookended by dead air from the key
                # press/release; VAD trims it and stops Whisper hallucinating
                # filler into the silence.
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 200,
                },
                # Personal jargon: biases the decoder toward these spellings
                # instead of phonetic guesses ("sticks halo" -> "strixhalo").
                initial_prompt=self.initial_prompt or None,
                # THE hallucination fix: by default each window is decoded
                # conditioned on the text of the previous one, so a single
                # invented phrase in dead air feeds itself and snowballs
                # into paragraphs of confident nonsense (and can drift
                # language mid-clip). Every window now stands alone.
                condition_on_previous_text=False,
                # Reject windows that are repetitive, low-confidence, or
                # probably not speech at all.
                compression_ratio_threshold=2.2,
                log_prob_threshold=-0.9,
                no_speech_threshold=0.5,
                # Lets the decoder skip long silences it suspects it is
                # hallucinating into (needs word timings).
                word_timestamps=True,
                hallucination_silence_threshold=2.0,
            )
            kept, _dropped = filter_segments(segments)
            text = " ".join(kept).strip()

            if self.on_progress:
                self.on_progress(1.0, "Transcription complete")
            return text

        except Exception as e:
            print(f"faster-whisper unavailable ({e}); falling back")
            return None

    def _transcribe_whisper_cpp(self, audio_path: str) -> str:
        """Shell out to a whisper.cpp binary."""
        try:
            if self.on_progress:
                self.on_progress(0.2, "Running whisper.cpp...")

            cmd = [
                self.whisper_path,
                "-m", self.model_path,
                "-f", audio_path,
                "-otxt",
                "--no-timestamps",
                "-l", self.language,
            ]
            if self.initial_prompt:
                cmd += ["--prompt", self.initial_prompt]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if self.on_progress:
                self.on_progress(0.8, "Processing output...")

            if result.returncode == 0:
                txt_path = audio_path + ".txt"
                if os.path.isfile(txt_path):
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        text = f.read().strip()
                    os.unlink(txt_path)

                    if self.on_progress:
                        self.on_progress(1.0, "Transcription complete")
                    return text

                if self.on_progress:
                    self.on_progress(1.0, "Transcription complete")
                return result.stdout.strip()

            print(f"Whisper error: {result.stderr}")
            return self._transcribe_fallback(audio_path)

        except subprocess.TimeoutExpired:
            print("Transcription timed out")
            if self.on_progress:
                self.on_progress(1.0, "Transcription timed out")
            return ""
        except Exception as e:
            print(f"Transcription error: {e}")
            return self._transcribe_fallback(audio_path)

    def _transcribe_fallback(self, audio_path: str) -> str:
        """Last resort: openai-whisper. CPU only -- torch here is a cu124 build
        with no sm_120 kernels, so CUDA would fault on the RTX PRO 6000."""
        try:
            import whisper

            if self.on_progress:
                self.on_progress(0.3, "Loading whisper model...")

            model_name = self.model.replace(".en", "")
            model = whisper.load_model(model_name, device="cpu")

            if self.on_progress:
                self.on_progress(0.5, "Transcribing with Python whisper...")

            result = model.transcribe(
                audio_path,
                language=self.language,
                initial_prompt=self.initial_prompt or None,
            )

            if self.on_progress:
                self.on_progress(1.0, "Transcription complete")

            return result["text"].strip()

        except ImportError:
            print("No whisper backend found. Run: pip install faster-whisper")
            if self.on_progress:
                self.on_progress(1.0, "No whisper backend available")
            return ""
        except Exception as e:
            print(f"Fallback transcription error: {e}")
            if self.on_progress:
                self.on_progress(1.0, f"Transcription error: {e}")
            return ""

    # -- discovery ---------------------------------------------------------

    def _find_whisper(self) -> str:
        """Try to find a whisper.cpp executable."""
        for name in ["whisper", "whisper-cli", "main", "whisper-cpp"]:
            found = shutil.which(name)
            if found:
                return found

        possible_paths = [
            Path.home() / "whisper.cpp" / "main",
            Path.home() / "whisper.cpp" / "build" / "bin" / "main",
            Path.home() / ".local" / "bin" / "whisper",
            Path("/usr/local/bin/whisper"),
            Path("/usr/bin/whisper"),
            Path("./whisper"),
        ]

        for path in possible_paths:
            if path.exists() and os.access(path, os.X_OK):
                return str(path)

        return ""

    def _get_model_path(self) -> str:
        """Path to a ggml model for the whisper.cpp backend."""
        model_dirs = [
            Path.home() / ".cache" / "whisper",
            Path.home() / "whisper.cpp" / "models",
            Path("./models"),
            Path("/usr/share/whisper/models"),
        ]

        model_filename = f"ggml-{self.model}.bin"

        for dir_path in model_dirs:
            model_path = dir_path / model_filename
            if model_path.exists():
                return str(model_path)

        return model_filename

    def is_available(self) -> bool:
        """Check if any transcription backend is available."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            pass

        if self.whisper_path and os.path.isfile(self.model_path):
            return True

        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def get_available_models(self) -> list:
        """Models offered in the UI, fastest to most accurate."""
        return [
            "tiny.en", "base.en", "small.en", "medium.en",
            "distil-large-v3", "large-v3-turbo", "large-v3",
        ]
