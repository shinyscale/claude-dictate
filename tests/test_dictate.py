"""
Tests for the parts of Claude Dictate that have bitten us: word fixes,
spoken punctuation, joining one dictation onto the last, the microphone
lookup, settings files from other versions, and picking the clean-up model.

No microphone, display, GPU or real model server needed:

    python -m unittest discover -s tests -v
"""

import json
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The package imports pyaudio at the top; these tests never record.
if "pyaudio" not in sys.modules:
    try:
        import pyaudio  # noqa: F401
    except ImportError:
        sys.modules["pyaudio"] = types.SimpleNamespace(
            PyAudio=object, Stream=object, paInt16=8)

from src.config import (AppConfig, DEFAULT_CONFIG, DEFAULT_CORRECTIONS,  # noqa: E402
                        DEFAULT_VOCABULARY)
from src.devices import match_device  # noqa: E402
from src.refiner import LLMRefiner, get_model_status, resolve_llm  # noqa: E402
from src.seams import join_continuation, strip_refine_command  # noqa: E402
from src.transcriber import (apply_corrections, apply_spoken_punctuation,  # noqa: E402
                             build_initial_prompt, load_wav_samples)

# A port nothing listens on, for "this engine isn't running".
DEAD = "http://127.0.0.1:9"


class Corrections(unittest.TestCase):
    def fix(self, text):
        return apply_corrections(text, DEFAULT_CORRECTIONS)

    def test_known_manglings(self):
        self.assertEqual(self.fix("ask sticks halo about it"), "ask strixhalo about it")
        self.assertEqual(self.fix("Deep Seek is off"), "DeepSeek is off")

    def test_new_project_names(self):
        self.assertEqual(self.fix("open fools archery"), "open Fool's Archery")
        self.assertEqual(self.fix("red weather needs tuning"), "Red Weather needs tuning")
        self.assertEqual(self.fix("the boss game is down"), "the bosgame is down")
        self.assertEqual(self.fix("flash next on the Sparks"), "Flash-Next on the Sparks")

    def test_word_boundaries(self):
        # "sand pipe" must not fire inside another word
        self.assertEqual(self.fix("the sand pipes are fine"), "the sand pipes are fine")

    def test_longer_key_wins(self):
        out = apply_corrections("strix halo", {"strix": "X", "strix halo": "strixhalo"})
        self.assertEqual(out, "strixhalo")

    def test_empty(self):
        self.assertEqual(apply_corrections("", DEFAULT_CORRECTIONS), "")
        self.assertEqual(apply_corrections("hello", None), "hello")


class Vocabulary(unittest.TestCase):
    def test_prompt_is_a_sentence(self):
        p = build_initial_prompt(["Tower", " Lilli ", ""])
        self.assertEqual(p, "Glossary for this recording: Tower, Lilli.")

    def test_default_list_stays_short(self):
        # Whisper only conditions on the last 224 prompt tokens; a longer
        # glossary silently drops its FIRST terms. ~4 characters per token.
        self.assertLess(len(build_initial_prompt(DEFAULT_VOCABULARY)) / 4, 200)

    def test_no_duplicates(self):
        lowered = [t.lower() for t in DEFAULT_VOCABULARY]
        self.assertEqual(len(lowered), len(set(lowered)))


class SpokenPunctuation(unittest.TestCase):
    def test_terminator(self):
        self.assertEqual(apply_spoken_punctuation("ship it exclamation point."), "ship it!")
        self.assertEqual(apply_spoken_punctuation("is it done question mark"), "is it done?")

    def test_prefix_sigil(self):
        self.assertEqual(apply_spoken_punctuation("exclamation point opus do this"),
                         "!opus do this")

    def test_mid_text_keeps_one_space(self):
        self.assertEqual(apply_spoken_punctuation("really question mark. Then go"),
                         "really? Then go")

    def test_plain_text_untouched(self):
        self.assertEqual(apply_spoken_punctuation("mark the question"), "mark the question")


class RefineCommand(unittest.TestCase):
    def test_trailing_command(self):
        self.assertEqual(strip_refine_command("fix the tower page. Refine this."),
                         (True, "fix the tower page."))

    def test_repeated(self):
        self.assertEqual(strip_refine_command("hello there. Refine that. Refine that."),
                         (True, "hello there."))

    def test_only_the_command(self):
        self.assertEqual(strip_refine_command("Refine it."), (True, ""))

    def test_not_at_the_end(self):
        text = "we should refine this idea further"
        self.assertEqual(strip_refine_command(text), (False, text))


class Continuation(unittest.TestCase):
    VOCAB = ["Tower", "DeepSeek", "Fool's Archery"]

    def test_new_sentence(self):
        self.assertEqual(join_continuation("It works.", "next thing", self.VOCAB),
                         (0, " Next thing"))

    def test_fake_period_after_function_word(self):
        # Whisper ended an unfinished sentence on "the."
        self.assertEqual(join_continuation("Open the.", "Settings page", self.VOCAB),
                         (1, " settings page"))

    def test_mid_sentence_keeps_proper_nouns(self):
        self.assertEqual(join_continuation("Then open", "Tower again", self.VOCAB),
                         (0, " Tower again"))
        self.assertEqual(join_continuation("and then", "I left", self.VOCAB),
                         (0, " I left"))
        self.assertEqual(join_continuation("ask", "DeepSeek first", self.VOCAB),
                         (0, " DeepSeek first"))

    def test_trailing_space_counted(self):
        self.assertEqual(join_continuation("Open the. ", "Door", self.VOCAB),
                         (2, " door"))

    def test_nothing_before(self):
        self.assertEqual(join_continuation("", "Hello", self.VOCAB), (0, "Hello"))


class Microphone(unittest.TestCase):
    # What PortAudio lists on a Windows machine with a Behringer UMC404HD:
    # every input once per audio API, MME first with names cut at 31 chars.
    DEVICES = [
        {"index": 0, "name": "Microsoft Sound Mapper - Input"},
        {"index": 1, "name": "IN 3-4 (BEHRINGER UMC 404HD 192"},
        {"index": 2, "name": "IN 1-2 (BEHRINGER UMC 404HD 192"},
        {"index": 3, "name": "IN 1-4 (BEHRINGER UMC 404HD 192"},
        {"index": 9, "name": "IN 1-2 (BEHRINGER UMC 404HD 192k)"},
        {"index": 14, "name": "IN 1-2 (BEHRINGER UMC 404HD 192k)"},
    ]

    def test_full_name_finds_truncated_mme_entry(self):
        self.assertEqual(match_device(self.DEVICES, "IN 1-2 (BEHRINGER UMC 404HD 192k)"), 9)
        # ...and when only the truncated entry exists, that one
        self.assertEqual(match_device(self.DEVICES[:4], "IN 1-2 (BEHRINGER UMC 404HD 192k)"), 2)

    def test_truncated_name_is_exact(self):
        self.assertEqual(match_device(self.DEVICES, "IN 1-2 (BEHRINGER UMC 404HD 192"), 2)

    def test_short_name(self):
        self.assertEqual(match_device(self.DEVICES, "IN 1-2"), 2)
        self.assertEqual(match_device(self.DEVICES, "in 3-4"), 1)

    def test_survives_renumbering(self):
        shuffled = [dict(d, index=d["index"] + 5) for d in self.DEVICES]
        self.assertEqual(match_device(shuffled, "IN 1-2 (BEHRINGER UMC 404HD 192"), 7)

    def test_missing(self):
        self.assertIsNone(match_device(self.DEVICES, "Blue Yeti"))
        self.assertIsNone(match_device(self.DEVICES, None))
        self.assertIsNone(match_device(self.DEVICES, ""))


class WavLoading(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _wav(self, rate, channels, frames=1600):
        import wave
        path = str(Path(self.tmp.name) / f"{rate}-{channels}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"\x00\x40" * frames * channels)
        return path

    def test_our_own_recordings_skip_the_file_decoder(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed here")
        samples = load_wav_samples(self._wav(16000, 1))
        self.assertEqual(len(samples), 1600)
        self.assertAlmostEqual(float(samples[0]), 0.5, places=4)

    def test_other_formats_are_left_to_the_decoder(self):
        self.assertIsNone(load_wav_samples(self._wav(44100, 1)))
        self.assertIsNone(load_wav_samples(self._wav(16000, 2)))
        self.assertIsNone(load_wav_samples("no-such-file.wav"))


class Settings(unittest.TestCase):
    def test_defaults_do_not_point_at_a_retired_model(self):
        flat = AppConfig().to_flat_dict()
        self.assertEqual(flat["default_llm"], "auto")
        self.assertEqual(flat["default_model"], "auto")
        self.assertNotIn("DeepSeek-V4", json.dumps(DEFAULT_CONFIG))
        self.assertNotIn(":8000", json.dumps(DEFAULT_CONFIG))

    def test_round_trip_keeps_the_mic_name(self):
        flat = AppConfig().to_flat_dict()
        flat["audio_device_name"] = "IN 1-2 (BEHRINGER UMC 404HD 192"
        flat["local_url"] = "http://localhost:9999/v1"
        saved = AppConfig.from_dict(flat).to_dict()          # what goes to disk
        again = AppConfig.from_dict(saved).to_flat_dict()    # what comes back
        self.assertEqual(again["audio_device_name"], "IN 1-2 (BEHRINGER UMC 404HD 192")
        self.assertEqual(again["local_url"], "http://localhost:9999/v1")

    def test_unknown_keys_do_not_stop_the_app(self):
        saved = AppConfig().to_dict()
        saved["audio"]["from_a_newer_version"] = 1
        saved["llm"]["retired_setting"] = "x"
        cfg = AppConfig.from_dict(saved)
        self.assertEqual(cfg.audio.sample_rate, 16000)

    def test_old_file_without_new_keys(self):
        old = {"whisper": {"model": "large-v3-turbo"},
               "audio": {"device_index": 3},
               "llm": {"backend": "f235", "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
                       "f235_url": "http://spark-f235:8000/v1"}}
        cfg = AppConfig.from_dict(old)
        self.assertEqual(cfg.audio.device_index, 3)
        self.assertIsNone(cfg.audio.device_name)
        self.assertEqual(cfg.llm.backend, "f235")  # a saved choice is kept


class _FakeServer:
    """A tiny OpenAI-compatible server. strict=True rejects the
    chat_template_kwargs extension, like a server that validates fields."""

    def __init__(self, model="qwen-test", strict=False):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/v1/models":
                    self._send(200, {"data": [{"id": model}]})
                else:
                    self._send(404, {"error": "no"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                if strict and "chat_template_kwargs" in body:
                    self._send(400, {"error": "unknown field"})
                    return
                self._send(200, {"choices": [{"message": {"content": " cleaned text "}}]})

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CleanUpModel(unittest.TestCase):
    def setUp(self):
        self.server = _FakeServer()
        self.addCleanup(self.server.close)
        self.urls = {"lm_studio": DEAD + "/v1", "ollama": DEAD,
                     "local": self.server.url, "f235": DEAD + "/v1"}

    def test_auto_finds_the_local_server(self):
        self.assertEqual(resolve_llm("auto", "auto", self.urls),
                         ("local", self.server.url, "qwen-test"))

    def test_auto_with_nothing_running(self):
        dead = dict(self.urls, local=DEAD + "/v1")
        self.assertIsNone(resolve_llm("auto", "auto", dead))

    def test_local_backend_auto_model(self):
        self.assertEqual(resolve_llm("local", "auto", self.urls),
                         ("local", self.server.url, "qwen-test"))

    def test_status_of_a_non_lm_studio_server(self):
        status = get_model_status("local", self.server.url, "qwen-test")
        self.assertEqual(status["state"], "loaded")
        status = get_model_status("local", self.server.url, "something-else")
        self.assertEqual(status["state"], "not-loaded")

    def test_refine_turns_thinking_off(self):
        r = LLMRefiner(backend="auto", model="auto", urls=self.urls)
        self.assertEqual(r.refine("um hello"), "cleaned text")
        sent = self.server.requests[-1]
        self.assertEqual(sent["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(sent["model"], "qwen-test")

    def test_refine_still_works_on_a_strict_server(self):
        strict = _FakeServer(strict=True)
        self.addCleanup(strict.close)
        r = LLMRefiner(backend="local", model="auto", urls={"local": strict.url})
        self.assertEqual(r.refine("um hello"), "cleaned text")
        self.assertEqual(len(strict.requests), 2)
        self.assertNotIn("chat_template_kwargs", strict.requests[-1])

    def test_auto_remembers_the_last_answer(self):
        r = LLMRefiner(backend="auto", model="auto", urls=self.urls)
        first = r._resolve()
        self.assertEqual(r._last_resolved, first)
        # The remembered server is asked directly: with it as the only URL
        # left, the answer is the same.
        r.urls = {"local": self.server.url}
        self.assertEqual(r._resolve(), first)

    def test_auto_forgets_a_server_that_went_away(self):
        gone = _FakeServer()
        r = LLMRefiner(backend="auto", model="auto",
                       urls=dict(self.urls, local=gone.url, f235=self.server.url))
        self.assertEqual(r._resolve(), ("local", gone.url, "qwen-test"))
        gone.close()
        self.assertEqual(r._resolve(), ("f235", self.server.url, "qwen-test"))

    def test_refine_with_nothing_running_returns_empty(self):
        r = LLMRefiner(backend="auto", model="auto",
                       urls=dict(self.urls, local=DEAD + "/v1"))
        self.assertEqual(r.refine("um hello"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
