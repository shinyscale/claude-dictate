# Claude Dictate

> 🎤 Voice-to-Text Tool for Claude Code

A local, privacy-first dictation tool that uses **whisper.cpp** for transcription and optionally refines text with local LLMs via **Ollama** or **LM Studio**. Perfect for creating prompts, PRDs, and documentation for Claude Code workflows.

![Claude Dictate](https://img.shields.io/badge/whisper.cpp-local-green) ![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20LM%20Studio-blue) ![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)

## ✨ Features

- **🎤 Hold-to-Talk Recording** - Press and hold a hotkey to record, release to transcribe
- **⚡ Local Transcription** - Uses whisper.cpp for fast, private, offline transcription
- **🤖 LLM Refinement** - Optional text cleanup and formatting via Ollama or LM Studio
- **📄 Multiple Export Formats** - Save as `.md`, `.prd`, or Claude Code prompts
- **📋 Clipboard Integration** - One-click copy to clipboard
- **🎨 Modern UI** - Clean, dark-themed interface built with CustomTkinter
- **🔒 Privacy-First** - Everything runs locally, no data leaves your machine

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai/) or [LM Studio](https://lmstudio.ai/) (optional, for text refinement)

### Installation

```bash
# Clone or download this repository
cd claude-dictate

# Run the setup script (installs whisper.cpp and models)
chmod +x setup.sh
./setup.sh

# Or manually install dependencies
pip install -r requirements.txt
```

### Running

```bash
# GUI mode (default)
python claude_dictate.py --gui

# Or just
python claude_dictate.py

# CLI mode - single recording
python claude_dictate.py --record
```

## 🎯 Usage

### GUI Mode

1. **Launch the app**: `python claude_dictate.py`
2. **Record**: Hold `Ctrl+Shift` or click and hold the record button
3. **Transcribe**: Release to automatically transcribe
4. **Refine** (optional): Click "Refine with LLM" to clean up the text
5. **Export**: Copy to clipboard or save as `.md`, `.prd`, or prompt file

### CLI Mode

```bash
# Record and copy to clipboard
python claude_dictate.py --record --output clipboard

# Record and save as markdown
python claude_dictate.py --record --output md

# Record, refine, and save as PRD
python claude_dictate.py --record --refine --style professional --output prd

# Use LM Studio instead of Ollama
python claude_dictate.py --record --llm lm_studio --model mistral
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift` (hold) | Record audio |
| Release | Stop recording and transcribe |

## 📁 Output Formats

### Markdown (`.md`)
Standard markdown file with your transcription/refined text.

### PRD (`.prd.md`)
Product Requirements Document format compatible with Claude Code workflows:

```markdown
# Product Requirements Document

## Overview
[Your dictated content]

## User Stories
- [ ] As a user, I want to...

## Technical Requirements
[To be filled]

## Success Criteria
- [ ] All requirements implemented
- [ ] Tests passing
- [ ] Documentation updated
```

### Claude Code Prompt
Formatted for use with Claude Code's Ralph Wiggum workflow:

```markdown
# Claude Code Prompt

[Your dictated content]

---
## Completion Criteria
When complete, output: <promise>DONE</promise>

## Process
1. Analyze the requirements above
2. Plan the implementation
3. Execute step by step
4. Verify each step works
5. Test the final result
```

## ⚙️ Configuration

Edit `config.json` or use the Settings panel in the GUI:

```json
{
    "whisper_cpp_path": "/path/to/whisper.cpp/main",
    "whisper_model": "base.en",
    "hotkey": "ctrl+shift",
    "ollama_url": "http://localhost:11434",
    "lm_studio_url": "http://localhost:1234/v1",
    "default_llm": "ollama",
    "default_model": "llama3.2",
    "output_dir": "./outputs"
}
```

### Whisper Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `tiny.en` | 75 MB | Fastest | Basic |
| `base.en` | 142 MB | Fast | Good |
| `small.en` | 466 MB | Medium | Better |
| `medium.en` | 1.5 GB | Slow | Great |
| `large` | 2.9 GB | Slowest | Best |

### LLM Refinement Styles

- **Clean**: Fix grammar, remove filler words, improve readability
- **Professional**: Polish for professional communication
- **Technical**: Format for technical documentation
- **Casual**: Keep conversational tone while fixing errors

## 🔧 Troubleshooting

### No audio input
- Check microphone permissions
- On macOS: System Preferences → Security & Privacy → Microphone
- On Linux: Ensure PulseAudio/ALSA is configured

### Whisper.cpp not found
- Run `./setup.sh` to install whisper.cpp
- Or set the path manually in config.json

### LLM refinement not working
- Ensure Ollama is running: `ollama serve`
- Or start LM Studio's local server
- Check the URL in settings matches your setup

### Hotkey not working
- On macOS: Grant accessibility permissions to Terminal/Python
- On Linux: May require running with elevated privileges for global hotkeys
- Try a different hotkey combination in settings

## 📦 Dependencies

- `pyaudio` - Audio recording
- `keyboard` - Global hotkey binding
- `pyperclip` - Clipboard operations
- `requests` - HTTP client for LLM APIs
- `customtkinter` - Modern GUI framework
- `whisper.cpp` - Local speech recognition (external)

## 🤝 Integration with Claude Code

### Using with Ralph Wiggum Plugin

1. Dictate your task description
2. Save as Claude Code Prompt
3. Use in Ralph loop:

```bash
/ralph-loop "$(cat outputs/prompt_*.md)" --max-iterations 20
```

### Custom Slash Commands

Save dictated prompts directly to Claude Code commands:

```python
# In the app, use "Save as Claude Code Prompt"
# Files are saved to ~/.claude/commands/
```

Then use in Claude Code:
```
/user:your-command-name
```

## 📄 License

MIT License - feel free to use and modify for your needs.

## 🙏 Credits

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) - Fast C/C++ Whisper implementation
- [Ollama](https://ollama.ai/) - Local LLM runner
- [LM Studio](https://lmstudio.ai/) - LLM GUI
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern Tkinter widgets

---

*Built for the Claude Code community* 🚀
