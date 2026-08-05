"""
LLM refinement module for Claude Dictate
Handles text refinement using local LLMs (Ollama or LM Studio).
"""

import json
import subprocess
from pathlib import Path
from typing import Optional, Callable, Generator

import requests

from .prompts import get_prompt, get_available_styles, SYSTEM_PROMPT


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


def get_model_status(backend: str, base_url: str, model: str) -> dict:
    """
    Best-effort load state for the configured refinement model.

    Returns {"state": "loaded"|"not-loaded"|"remote"|"unknown",
             "size_gb": float|None}.
    "remote" means a non-local backend we can't introspect (e.g. f235).
    """
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
        on_progress: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the LLM refiner.

        Args:
            backend: LLM backend ("ollama" or "lm_studio")
            base_url: Base URL for the LLM API
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system_prompt: Custom system prompt (uses default if empty)
            on_progress: Callback for streaming text updates
        """
        self.backend = backend
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.on_progress = on_progress

        if backend == "ollama":
            self.base_url = base_url or "http://localhost:11434"
        elif backend == "f235":
            self.base_url = base_url or "http://spark-f235:8000/v1"
        else:  # lm_studio
            self.base_url = base_url or "http://localhost:1234/v1"

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

        prompt = get_prompt(style, text)

        if self.backend == "ollama":
            return self._refine_ollama(prompt)
        else:
            return self._refine_openai_compatible(prompt)

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

        prompt = get_prompt(style, text)

        if self.backend == "ollama":
            yield from self._refine_ollama_stream(prompt)
        else:
            yield from self._refine_openai_stream(prompt)

    def _refine_ollama(self, prompt: str) -> str:
        """Refine using Ollama API."""
        try:
            print(f"[Ollama] Connecting to {self.base_url}...")
            print(f"[Ollama] Using model: {self.model}")
            print(f"[Ollama] Sending {len(prompt)} chars for refinement...")

            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
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

    def _refine_ollama_stream(self, prompt: str) -> Generator[str, None, None]:
        """Refine using Ollama API with streaming."""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
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

    def _refine_openai_compatible(self, prompt: str) -> str:
        """Refine using OpenAI-compatible API (LM Studio)."""
        try:
            print(f"[LM Studio] Connecting to {self.base_url}...")
            print(f"[LM Studio] Using model: {self.model}")
            print(f"[LM Studio] Sending {len(prompt)} chars for refinement...")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
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
                print(f"[LM Studio] Response received ({len(result)} chars)")
                return result
            else:
                print(f"[LM Studio] Error: HTTP {response.status_code} - {response.text[:100]}")
                return ""

        except requests.exceptions.ConnectionError:
            print("[LM Studio] Connection failed - is LM Studio running?")
            return ""
        except Exception as e:
            print(f"[LM Studio] Error: {e}")
            return ""

    def _refine_openai_stream(self, prompt: str) -> Generator[str, None, None]:
        """Refine using OpenAI-compatible API with streaming."""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
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
                print(f"LM Studio stream error: {response.status_code}")

        except requests.exceptions.ConnectionError:
            print("Could not connect to LM Studio. Is it running?")
        except Exception as e:
            print(f"LM Studio stream error: {e}")

    def check_connection(self) -> bool:
        """Check if the LLM backend is available."""
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
