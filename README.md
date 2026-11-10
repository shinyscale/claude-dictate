# Claude Dictate

Hold a hotkey anywhere, talk, let go. What you said is typed into whatever
window you were in.

Everything runs on your own machine. Speech is recognised by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) on your graphics
card; an optional clean-up pass uses whatever local model you already have
running (LM Studio, Ollama, llama.cpp, vLLM). Nothing is sent to a cloud
service.

Built for dictating into Claude Code and other chat boxes. Windows is the
supported platform; the editor window and command-line mode also run on
macOS and Linux.

## What it does

- **Hold-to-talk, auto-paste.** Hold `Ctrl+Shift`, speak, release. The text
  is pasted where your cursor is. A small overlay shows recording,
  transcribing and pasted.
- **Lives in the tray.** No window. Right-click the tray icon for the menu.
- **Knows your words.** A personal word list biases recognition toward the
  names you actually say, and a fix-up table repairs the ones it still
  mangles ("sticks halo" becomes "strixhalo").
- **Joins sentences.** Dictate in several goes and the pieces are stitched
  together: one space between them, no stray period or capital in the
  middle of a sentence.
- **Terminal-aware.** Pastes with `Ctrl+Shift+V` in terminals, `Ctrl+V`
  everywhere else.
- **Won't paste into the wrong window.** If you switch windows while it is
  working, the text stays on the clipboard instead.
- **Never loses a dictation.** Every transcription is appended to a history
  file before anything else happens to it.
- **Optional clean-up.** Say "refine this" at the end of a dictation, or
  switch the tray menu to "Refine, then paste", and a local model removes
  the ums and false starts. Raw is the default: it is instant and cannot
  invent words.
- **Spoken punctuation** for the two marks worth saying: "question mark" and
  "exclamation point".

## Install (Windows)

You need Python 3.10, 3.11 or 3.12 and, for speed, an NVIDIA graphics card.

```
git clone https://github.com/shinyscale/claude-dictate
cd claude-dictate
install_windows.bat
```

The installer makes a private Python environment in the folder, installs the
packages, downloads the speech model (about 1.6 GB, once) and runs a
check-up. Every line of the check-up starts with `OK`, `WARN` or `FAIL`.

Then choose your microphone by name (any part of the name works):

```
venv\Scripts\python doctor.py --set-mic "IN 1-2"
```

and start it:

```
run_windows.bat
```

To have it start every time you sign in, right-click the tray icon and tick
**Start when I sign in**.

## Using it

| Do this | What happens |
|---|---|
| Hold `Ctrl+Shift`, talk, release | Your words are pasted where the cursor is |
| End with "refine this" | That one dictation is cleaned up by the local model first |
| Say "question mark" / "exclamation point" | `?` / `!` |
| Tray menu: Paste raw transcript / Refine, then paste | Sets what happens by default |
| Tray menu: Show Claude Dictate | Opens the editor window, with history and settings |
| Tray menu: Start when I sign in | Turns starting with Windows on or off |
| Tray menu: Open log | Opens the log file, for when something goes wrong |

The editor window (`run_windows.bat --gui`) can also record, refine in
several styles, and save as Markdown, a PRD, or a Claude Code prompt.

## Check-up

```
venv\Scripts\python doctor.py                  check everything
venv\Scripts\python doctor.py --mic 4          also record 4 s and transcribe it
venv\Scripts\python doctor.py --wav clip.wav   also transcribe a file
```

It reports the saved microphone, whether the graphics card is used, how fast
the speech model is, which clean-up model answered, and where the log is.
It changes nothing unless you pass `--set-mic`.

## Settings

Settings are in the editor window (Settings button) and are saved to
`%APPDATA%\ClaudeDictate\config.json`. The ones that matter:

| Setting | Default | Meaning |
|---|---|---|
| `whisper.model` | `large-v3-turbo` | Speech model. Smaller ones (`small.en`, `base.en`) are faster on a machine without a graphics card. |
| `audio.device_name` | none (Windows default) | The microphone, remembered by name so it survives Windows renumbering devices. |
| `hotkey.record_hotkey` | `ctrl+shift` | Hold-to-talk keys. |
| `output.paste_mode` | `raw` | `raw` or `refined`. |
| `llm.backend` | `auto` | `auto`, `lm_studio`, `ollama`, `local` or `f235`. `auto` uses whichever one has a model loaded right now and never loads one itself. |
| `llm.model` | `auto` | A model name, or `auto` for whatever is loaded. |
| `llm.local_url` | `http://127.0.0.1:8012/v1` | Any OpenAI-compatible server on this machine (llama.cpp, vLLM). |
| `vocabulary.terms` | a starter list | Words to bias recognition toward. Keep it short: only about the last 200 tokens count. |
| `vocabulary.corrections` | a starter table | "heard this" to "write this" fix-ups, applied after recognition. |
| `output.terminal_windows` | common terminals | Windows that get `Ctrl+Shift+V`. |

The same folder holds `history.md` (every dictation) and `dictate.log`.

## When something is off

Run the check-up first; it names the problem in plain words. The usual ones:

- **Nothing is pasted, or the wrong thing is.** Open the log from the tray
  menu. Each dictation logs what it heard, how long each step took, and
  which window it pasted into.
- **Microphone FAIL, "dead silent".** Wrong input chosen, the input is
  muted, or the mic is unplugged. Run `doctor.py --set-mic "part of name"`.
- **"no graphics card visible".** Speech falls back to the processor and is
  slow. Re-run `install_windows.bat`; it installs the NVIDIA libraries the
  speech engine needs.
- **Clean-up does nothing.** No local model is running. Raw dictation still
  works; start LM Studio, Ollama or your model server and try again.
- **It pastes `^V` into a terminal.** Add part of that terminal's window
  title to `terminal_windows`.

## Tests

```
venv\Scripts\python -m unittest discover -s tests -v
```

They need no microphone, display, graphics card or model server.

## License

MIT. See [LICENSE](LICENSE).

## Credits

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and
[CTranslate2](https://github.com/OpenNMT/CTranslate2) for speech,
[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the
window, [pystray](https://github.com/moses-palmer/pystray) and
[pynput](https://github.com/moses-palmer/pynput) for the tray and hotkeys.
