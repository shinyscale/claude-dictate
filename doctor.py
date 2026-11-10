#!/usr/bin/env python3
"""
Claude Dictate check-up. Run it after installing, or when something is off:

    python doctor.py                 # check everything
    python doctor.py --mic 3         # also record 3 s from the saved mic
    python doctor.py --wav clip.wav  # also transcribe a file
    python doctor.py --set-mic "IN 1-2"   # save a microphone by name

It changes nothing unless you pass --set-mic. Each line starts with OK,
WARN or FAIL; the exit code is 1 if anything failed.
"""

import argparse
import os
import struct
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

failed = False


def say(level: str, text: str) -> None:
    global failed
    if level == "FAIL":
        failed = True
    print(f"{level:4} {text}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Claude Dictate check-up")
    ap.add_argument("--mic", type=float, metavar="SECONDS",
                    help="record this long from the saved microphone and report the level")
    ap.add_argument("--wav", help="transcribe this WAV file with the saved settings")
    ap.add_argument("--set-mic", metavar="NAME",
                    help="save the microphone whose name matches NAME")
    ap.add_argument("--no-model", action="store_true",
                    help="skip loading the speech model")
    args = ap.parse_args()

    from src.config import AppConfig
    from src.devices import match_device
    from src.audio import AudioRecorder
    from src import autostart

    cfg = AppConfig.load()
    say("OK", f"settings file: {AppConfig.get_config_path()}")

    # ---- microphone ----
    devices = AudioRecorder.get_input_devices()
    say("OK" if devices else "FAIL", f"{len(devices)} input device(s) found")
    if args.set_mic:
        idx = match_device(devices, args.set_mic)
        if idx is None:
            say("FAIL", f"no input device matches {args.set_mic!r}")
            for d in devices:
                print(f"       [{d['index']}] {d['name']}")
        else:
            name = next(d["name"] for d in devices if d["index"] == idx)
            cfg.audio.device_name = name
            cfg.audio.device_index = idx
            cfg.save()
            say("OK", f"microphone saved: {name!r}")
    if cfg.audio.device_name:
        idx = match_device(devices, cfg.audio.device_name)
        if idx is None:
            say("FAIL", f"saved microphone {cfg.audio.device_name!r} is not plugged in "
                        f"(the system default would be used)")
        else:
            say("OK", f"microphone: {cfg.audio.device_name!r} (currently device {idx})")
    else:
        say("WARN", "no microphone saved; the Windows default input is used")

    if args.mic:
        rec = AudioRecorder(sample_rate=cfg.audio.sample_rate, channels=cfg.audio.channels,
                            chunk_size=cfg.audio.chunk_size,
                            device_index=cfg.audio.device_index,
                            device_name=cfg.audio.device_name)
        try:
            rec.start_recording()
            time.sleep(args.mic)
            path = rec.stop_recording()
            with wave.open(path, "rb") as w:
                raw = w.readframes(w.getnframes())
                secs = w.getnframes() / w.getframerate()
            samples = struct.unpack(f"{len(raw) // 2}h", raw)
            peak = max((abs(s) for s in samples), default=0) / 32768
            rms = (sum(s * s for s in samples) / max(1, len(samples))) ** 0.5 / 32768
            level = "OK" if peak > 0.002 else "FAIL"
            say(level, f"recorded {secs:.1f} s from the microphone: peak {peak:.4f}, "
                       f"average {rms:.5f}" + ("" if level == "OK" else
                                               " (dead silent: wrong input, muted, or unplugged)"))
            if not args.wav:
                args.wav = path
                say("OK", "transcribing that recording next")
        except Exception as e:
            say("FAIL", f"could not record: {e}")

    # ---- speech model ----
    from src import transcriber as tr
    added = tr.add_cuda_dll_dirs()
    if added:
        say("OK", f"NVIDIA libraries found in {len(added)} folder(s)")
    gpu = tr.cuda_available()
    say("OK" if gpu else "WARN",
        "graphics card visible to the speech engine" if gpu else
        "no graphics card visible; speech will run on the processor (slow)")
    if not args.no_model:
        t = tr.WhisperTranscriber(model=cfg.whisper.model,
                                  vocabulary=cfg.vocabulary.terms,
                                  corrections=cfg.vocabulary.corrections)
        t0 = time.time()
        ok = t.preload()
        say("OK" if ok else "FAIL",
            f"speech model {t.fw_model_name} on {t.device} ({t.compute_type}) "
            + (f"loaded in {time.time() - t0:.1f} s" if ok else "did not load"))
        if ok and args.wav:
            with wave.open(args.wav, "rb") as w:
                secs = w.getnframes() / w.getframerate()
            t0 = time.time()
            # Straight to the GPU path: transcribe() would hide a failure
            # behind the slow fallbacks, and this check exists to catch that.
            text = t._transcribe_faster_whisper(args.wav)
            took = time.time() - t0
            if text is None:
                say("FAIL", "the speech engine failed on the recording (see the message above)")
            else:
                # The same word fixes and spoken punctuation a dictation gets.
                text = tr.apply_spoken_punctuation(
                    tr.apply_corrections(text, cfg.vocabulary.corrections))
                say("OK", f"transcribed {secs:.1f} s of audio in {took:.2f} s "
                          f"({secs / max(took, 1e-6):.0f}x real time)")
                print(f"       heard: {text!r}")

    # ---- clean-up model ----
    from src.refiner import resolve_llm, LLMRefiner
    urls = {"ollama": cfg.llm.ollama_url, "lm_studio": cfg.llm.lm_studio_url,
            "local": cfg.llm.local_url, "f235": cfg.llm.f235_url}
    found = resolve_llm(cfg.llm.backend, cfg.llm.model, urls)
    if not found:
        say("WARN", f"clean-up model: nothing answering (setting: {cfg.llm.backend}/"
                    f"{cfg.llm.model}). Raw dictation still works.")
    else:
        backend, url, model = found
        r = LLMRefiner(backend=cfg.llm.backend, model=cfg.llm.model, urls=urls)
        t0 = time.time()
        out = r.refine("um so basically I want the the page to uh show the temperature, you know.")
        took = time.time() - t0
        say("OK" if out else "FAIL",
            f"clean-up model {model} via {backend} ({url}) "
            + (f"answered in {took:.1f} s" if out else "gave no answer"))
        if out:
            print(f"       cleaned: {out!r}")

    # ---- startup ----
    if autostart.supported():
        say("OK", "starts at sign-in: " + ("yes" if autostart.is_enabled() else
                                           "no (tray menu > Start when I sign in)"))
    from src.logfile import log_path
    say("OK", f"log file: {log_path()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
