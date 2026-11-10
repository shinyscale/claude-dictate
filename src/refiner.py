"""
LLM refinement module for Claude Dictate
Handles text refinement using local LLMs (Ollama or LM Studio).
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Callable, Generator

import requests

from .prompts import get_prompt, get_available_styles, SYSTEM_PROMPT


DEFAULT_URLS = {
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first,
    # and every connection to a port nothing listens on costs ~2 s.
    "ollama": "http://127.0.0.1:11434",
    "f235": "http://spark-f235:8012/v1",
    "lm_studio": "http://127.0.0.1:1234/v1",
    # Any OpenAI-compatible server on this machine (llama.cpp, vLLM, ...).
    "local": "http://127.0.0.1:8012/v1",
}

# Order "auto" probes in: engines on this machine first, the Spark last.
AUTO_ORDER = ("lm_studio", "ollama", "local", "f235")


def _post_chat(base_url: str, payload: dict, **kwargs):
    """POST /chat/completions with model thinking switched off.

    Cleaning up a sentence needs no reasoning pass; on a thinking model it
    is the difference between ~1 s and ~10 s per dictation (measured on
    Qwen3.8-27B, 2026-11-09). chat_template_kwargs is a llama.cpp / vLLM
    extension -- servers that reject unknown fields get the plain request.
    """
    url = f"{base_url}/chat/completions"
    quiet = dict(payload, chat_template_kwargs={"enable_thinking": False})
    response = requests.post(url, json=quiet, **kwargs)
    if response.status_code in (400, 422):
        response = requests.post(url, json=payload, **kwargs)
    return response


def detect_loaded_model(backend: str, base_url: str) -> Optional[str]:
    """Model id currently resident on a backend, or None. Never triggers a
    load: LM Studio is asked via the v0 REST API (which reports load state),
    not /v1/models (which lists everything downloaded and would make picking
    one a JIT load). f235/vLLM serves a fixed model, so its /models listing
    is by definition the loaded one."""
    try:
        if backend == "ollama":
            r = requests.get(f"{base_url}/api/ps", timeout=3)
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    name = m.get("name") or m.get("model")
                    if name:
                        return name
            return None
        if backend == "lm_studio":
            root = base_url.rsplit("/v1", 1)[0]
            r = requests.get(f"{root}/api/v0/models", timeout=3)
            if r.status_code == 200:
                for m in r.json().get("data", []):
                    if m.get("state") == "loaded" and m.get("type") != "embeddings":
                        return m.get("id")
            return None
        r = requests.get(f"{base_url}/models", timeout=3)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return data[0].get("id")
    except Exception:
        pass
    return None


def resolve_llm(backend: str, model: str, urls: Optional[dict] = None) -> Optional[tuple]:
    """Resolve 'auto' backend/model settings to a concrete
    (backend, base_url, model), riding whatever is already resident rather
    than loading anything. Backend 'auto' probes LM Studio, then Ollama,
    then the local OpenAI-compatible server, then f235. Returns None when
    nothing is loaded anywhere."""
    urls = urls or {}

    def url_for(b: str) -> str:
        return urls.get(b) or DEFAULT_URLS[b]

    if backend == "auto":
        # Asked all at once: an engine that isn't running takes seconds to
        # say so on Windows, and asking in turn stacked those waits in front
        # of every dictation (12 s measured). Preference order still decides.
        with ThreadPoolExecutor(max_workers=len(AUTO_ORDER)) as pool:
            found = list(pool.map(
                lambda b: detect_loaded_model(b, url_for(b)), AUTO_ORDER))
        for b, model_id in zip(AUTO_ORDER, found):
            if model_id:
                return b, url_for(b), model_id
        return None
    if model == "auto":
        found = detect_loaded_model(backend, url_for(backend))
        return (backend, url_for(backend), found) if found else None
    return backend, urls.get(backend, ""), model


def _lms_loaded_size_gb(model: str) -> Optional[float]:
    """Resident size of a loaded LM Studio model via `lms ps`, if the CLI
    is installed. The REST API reports load state but not memory."""
    lms = Path.home() / ".lmstudio" / "bin" / "lms.exe"
    if not lms.exists():
        return None
    try:
        out = subprocess.run(
            [str(lms), "ps", "--json"],
            capture_output=True, text=True, timeout=6,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        for m in json.loads(out.stdout or "[]"):
            if model in (m.get("identifier"), m.get("modelKey"), m.get("path")):
                size = m.get("sizeBytes")
                return round(size / 1e9, 1) if size else None
    except Exception:
        pass
    return None


def get_model_status(backend: str, base_url: str, model: str,
                     urls: Optional[dict] = None) -> dict:
    """
    Best-effort load state for the configured refinement model.

    Returns {"state": "loaded"|"not-loaded"|"remote"|"unknown",
             "size_gb": float|None}.
    "remote" means a non-local backend we can't introspect (e.g. f235).
    In auto mode the resolved model id is reported as "resolved_model".
    """
    if backend == "auto" or model == "auto":
        resolved = resolve_llm(backend, model,
                               urls or ({backend: base_url} if base_url else None))
        if not resolved:
            return {"state": "not-loaded", "size_gb": None, "resolved_model": None}
        r_backend, r_url, r_model = resolved
        status = get_model_status(r_backend, r_url, r_model)
        status["resolved_model"] = r_model
        return status
    try:
        if backend == "ollama":
            r = requests.get(f"{base_url}/api/ps", timeout=3)
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    if model in (m.get("name"), m.get("model")):
                        size = m.get("size_vram") or m.get("size") or 0
                        return {"state": "loaded",
                                "size_gb": round(size / 1e9, 1) if size else None}
                return {"state": "not-loaded", "size_gb": None}
        else:
            root = base_url.rsplit("/v1", 1)[0]
            if "localhost" not in root and "127.0.0.1" not in root:
                return {"state": "remote", "size_gb": None}
            r = requests.get(f"{root}/api/v0/models", timeout=3)
            if r.status_code == 200:
                for m in r.json().get("data", []):
                    if m.get("id") == model:
                        if m.get("state") == "loaded":
                            return {"state": "loaded",
                                    "size_gb": _lms_loaded_size_gb(model)}
                        return {"state": "not-loaded", "size_gb": None}
            # Not LM Studio (llama.cpp, vLLM): these serve exactly what they
            # have loaded, so being listed means being resident.
            r = requests.get(f"{base_url}/models", timeout=3)
            if r.status_code == 200:
                ids = [m.get("id") for m in r.json().get("data", [])]
                if model in ids:
                    return {"state": "loaded", "size_gb": None}
                return {"state": "not-loaded", "size_gb": None}
    except Exception:
        pass
    return {"state": "unknown", "size_gb": None}


class LLMRefiner:
    """Handles text refinement using local LLMs."""

    def __init__(
        self,
        backend: str = "ollama",
        base_url: str = "",
        model: str = "llama3.2",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        system_prompt: str = "",
        on_progress: Optional[Callable[[str], None]] = None,
        urls: Optional[dict] = None,
    ):
        """
        Initialize the LLM refiner.

        Args:
            backend: LLM backend ("ollama", "lm_studio", "local", "f235",
                     or "auto" to ride whichever engine has a model loaded)
            base_url: Base URL for the LLM API (fixed backends)
            model: Model name to use, or "auto" for whatever is loaded
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system_prompt: Custom system prompt (uses default if empty)
            on_progress: Callback for streaming text updates
            urls: Optional {"ollama"|"lm_studio"|"local"|"f235": url} overrides,
                  needed so backend "auto" knows where to probe
        """
        self.backend = backend
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.on_progress = on_progress

        self._last_resolved: Optional[tuple] = None
        self.urls = {k: v for k, v in (urls or {}).items() if v}
        if base_url and backend != "auto":
            self.urls[backend] = base_url

        if backend == "auto":
            self.base_url = ""  # resolved per call
        else:
            self.base_url = self.urls.get(backend) or DEFAULT_URLS.get(
                backend, DEFAULT_URLS["lm_studio"])
            self.urls.setdefault(backend, self.base_url)

    def _resolve(self) -> Optional[tuple]:
        """Concrete (backend, base_url, model) for this call, honoring
        'auto' settings against whatever is loaded right now."""
        is_auto = "auto" in (self.backend, self.model)
        # Whatever answered last time is asked first: one quick request
        # instead of probing every engine before each dictation.
        last = self._last_resolved
        if is_auto and last and detect_loaded_model(last[0], last[1]) == last[2]:
            return last
        resolved = resolve_llm(self.backend, self.model, self.urls)
        if resolved is None:
            self._last_resolved = None
            print("[Refiner] No model loaded on any backend; skipping refinement")
            return None
        backend, base_url, model = resolved
        if not base_url:
            base_url = self.base_url
        if (backend, model) != (self.backend, self.model):
            print(f"[Refiner] auto-resolved to '{model}' on {backend}")
        self._last_resolved = (backend, base_url, model) if is_auto else None
        return backend, base_url, model

    def refine(self, text: str, style: str = "clean") -> str:
        """
        Refine transcribed text using LLM.

        Args:
            text: Text to refine
            style: Refinement style (clean, professional, technical, etc.)

        Returns:
            Refined text
        """
        if not text.strip():
            return ""

        resolved = self._resolve()
        if not resolved:
            return ""
        backend, base_url, model = resolved

        prompt = get_prompt(style, text)

        if backend == "ollama":
            return self._refine_ollama(prompt, base_url, model)
        else:
            return self._refine_openai_compatible(prompt, base_url, model)

    def refine_stream(self, text: str, style: str = "clean") -> Generator[str, None, None]:
        """
        Refine text with streaming response.

        Args:
            text: Text to refine
            style: Refinement style

        Yields:
            Text chunks as they arrive
        """
        if not text.strip():
            return

        resolved = self._resolve()
        if not resolved:
            return
        backend, base_url, model = resolved

        prompt = get_prompt(style, text)

        if backend == "ollama":
            yield from self._refine_ollama_stream(prompt, base_url, model)
        else:
            yield from self._refine_openai_stream(prompt, base_url, model)

    def _refine_ollama(self, prompt: str, base_url: str = "", model: str = "") -> str:
        """Refine using Ollama API."""
        base_url = base_url or self.base_url
        model = model or self.model
        try:
            print(f"[Ollama] Connecting to {base_url}...")
            print(f"[Ollama] Using model: {model}")
            print(f"[Ollama] Sending {len(prompt)} chars for refinement...")

            response = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": self.system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    }
                },
                timeout=300  # 5 minutes for large models like 120B
            )

            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                print(f"[Ollama] Response received ({len(result)} chars)")
                return result
            else:
                print(f"[Ollama] Error: HTTP {response.status_code} - {response.text[:100]}")
                return ""

        except requests.exceptions.ConnectionError:
            print("[Ollama] Connection failed - is Ollama running?")
            return ""
        except Exception as e:
            print(f"[Ollama] Error: {e}")
            return ""

    def _refine_ollama_stream(self, prompt: str, base_url: str = "",
                              model: str = "") -> Generator[str, None, None]:
        """Refine using Ollama API with streaming."""
        base_url = base_url or self.base_url
        model = model or self.model
        try:
            response = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": self.system_prompt,
                    "stream": True,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    }
                },
                stream=True,
                timeout=600  # 10 minutes for large models streaming
            )

            if response.status_code == 200:
                import json
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        chunk = data.get("response", "")
                        if chunk:
                            yield chunk
                            if self.on_progress:
                                self.on_progress(chunk)
            else:
                print(f"Ollama stream error: {response.status_code}")

        except requests.exceptions.ConnectionError:
            print("Could not connect to Ollama. Is it running?")
        except Exception as e:
            print(f"Ollama stream error: {e}")

    def _refine_openai_compatible(self, prompt: str, base_url: str = "",
                                  model: str = "") -> str:
        """Refine using OpenAI-compatible API (LM Studio)."""
        base_url = base_url or self.base_url
        model = model or self.model
        try:
            print(f"[LLM] Connecting to {base_url}...")
            print(f"[LLM] Using model: {model}")
            print(f"[LLM] Sending {len(prompt)} chars for refinement...")

            response = _post_chat(
                base_url,
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
                timeout=300  # 5 minutes for large models
            )

            if response.status_code == 200:
                result = response.json()["choices"][0]["message"]["content"].strip()
                print(f"[LLM] Response received ({len(result)} chars)")
                return result
            else:
                print(f"[LLM] Error: HTTP {response.status_code} - {response.text[:100]}")
                return ""

        except requests.exceptions.ConnectionError:
            print("[LLM] Connection failed - is the model server running?")
            return ""
        except Exception as e:
            print(f"[LLM] Error: {e}")
            return ""

    def _refine_openai_stream(self, prompt: str, base_url: str = "",
                              model: str = "") -> Generator[str, None, None]:
        """Refine using OpenAI-compatible API with streaming."""
        base_url = base_url or self.base_url
        model = model or self.model
        try:
            response = _post_chat(
                base_url,
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "stream": True,
                },
                stream=True,
                timeout=600  # 10 minutes for large models streaming
            )

            if response.status_code == 200:
                import json
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                chunk = data["choices"][0]["delta"].get("content", "")
                                if chunk:
                                    yield chunk
                                    if self.on_progress:
                                        self.on_progress(chunk)
                            except json.JSONDecodeError:
                                continue
            else:
                print(f"LLM stream error: {response.status_code}")

        except requests.exceptions.ConnectionError:
            print("[LLM] Could not connect to the model server. Is it running?")
        except Exception as e:
            print(f"LLM stream error: {e}")

    def check_connection(self) -> bool:
        """Check if the LLM backend is available."""
        if self.backend == "auto":
            return resolve_llm(self.backend, self.model, self.urls) is not None
        try:
            if self.backend == "ollama":
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            else:
                response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except:
            return False

    def get_available_models(self) -> list:
        """Get list of available models from the backend."""
        if self.backend == "auto":
            resolved = resolve_llm(self.backend, self.model, self.urls)
            return [resolved[2]] if resolved else []
        try:
            if self.backend == "ollama":
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return [m["name"] for m in models]
            else:
                response = requests.get(f"{self.base_url}/models", timeout=5)
                if response.status_code == 200:
                    models = response.json().get("data", [])
                    return [m["id"] for m in models]
        except:
            pass
        return []

    @staticmethod
    def get_refinement_styles() -> list:
        """Get list of available refinement styles."""
        return get_available_styles()
