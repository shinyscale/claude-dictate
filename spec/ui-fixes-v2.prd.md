# Claude Dictate UI Fixes v2 - Product Requirements Document

**Version:** 2.0
**Date:** 2026-01-09
**Status:** Draft

---

## Overview

This PRD documents bug fixes and feature improvements for the Claude Dictate application's user interface. These changes aim to improve usability, fix broken functionality, and create a cleaner visual layout.

---

## Bug Fixes

### BUG-001: Waveform Visualization Not Animating

**Priority:** High
**Severity:** Medium
**Component:** `src/gui/recorder.py`, `src/gui/app.py`

#### Description
The waveform visualization above the record button does not display audio levels during recording. It should show real-time voice patterns as the user speaks.

#### Root Cause Analysis
- `WaveformCanvas.update_level(level)` method exists in `recorder.py:132-162`
- `AudioRecorder` has `on_level_update` callback parameter in `audio.py:23`
- **The callback is never connected** - audio level updates are not being sent to the waveform

#### Acceptance Criteria
- [ ] Waveform bars animate based on actual voice input volume
- [ ] Animation responds in real-time during recording
- [ ] Bars return to idle state when recording stops

#### Technical Implementation
Connect the AudioRecorder callback to the WaveformCanvas in `app.py`:
```python
self.app.recorder.on_level_update = self.waveform.update_level
```

---

### BUG-002: LLM Refinement Not Producing Output

**Priority:** Critical
**Severity:** High
**Component:** `src/gui/app.py`, `src/main.py`, `src/refiner.py`

#### Description
Clicking "Refine with LLM" shows "Done" status immediately but no output appears in the Refined Text editor window.

#### Expected Behavior
1. User clicks "Refine with LLM"
2. Progress indicator shows refinement in progress
3. Ollama processes the text
4. Refined text appears in the Refined Text editor

#### Diagnosis Required
- Verify Ollama connection is established
- Confirm `refine_text()` returns text
- Ensure `on_refinement_complete` callback fires
- Check terminal for Ollama connection logs

#### Acceptance Criteria
- [ ] Refined text appears in the Refined Text editor after processing
- [ ] Terminal shows Ollama connection status and response info
- [ ] Error messages display if Ollama is unavailable

---

## Feature Requests

### FEAT-001: Window Size Adjustment

**Priority:** High
**Component:** `src/gui/theme.py`

#### Description
The application UI exceeds the default window boundaries, causing content to be cut off or require scrolling.

#### Current State
- Window dimensions: 1100x800 pixels
- Content overflows due to added features

#### Requirements
- [ ] Increase window height to accommodate all UI elements
- [ ] All controls visible without scrolling
- [ ] Window remains usable on standard 1080p displays

#### Technical Implementation
```python
# src/gui/theme.py
WINDOW_HEIGHT = 900  # Was 800
```

---

### FEAT-002: Style Selector Dropdown

**Priority:** Medium
**Component:** `src/gui/app.py`

#### Description
Replace the vertical list of radio buttons for LLM refinement styles with a compact dropdown menu.

#### Current State
- 6 radio buttons displayed vertically
- Takes significant vertical space
- Styles: Clean, Professional, Technical, Casual, PRD Format, Markdown

#### Requirements
- [ ] Replace radio buttons with dropdown/combobox
- [ ] Maintain all existing style options
- [ ] Default selection: "Clean"
- [ ] Match application theme styling

#### Technical Implementation
```python
self.style_var = ctk.StringVar(value="Clean")
styles = ["Clean", "Professional", "Technical", "Casual", "PRD Format", "Markdown"]
self.style_dropdown = ctk.CTkComboBox(
    style_frame,
    variable=self.style_var,
    values=styles,
    font=FONTS["body"],
    fg_color=THEME["bg_light"],
    ...
)
```

#### Style Code Mapping
| Display Name | Code |
|--------------|------|
| Clean | clean |
| Professional | professional |
| Technical | technical |
| Casual | casual |
| PRD Format | prd |
| Markdown | bullets |

---

### FEAT-003: Output Directory Browser

**Priority:** Medium
**Component:** `src/gui/settings.py`

#### Description
Add a "Browse" button to the output directory setting that opens a directory picker dialog.

#### Current State
- Simple text entry field for output directory
- Users must type paths manually
- Default: `./outputs`

#### Requirements
- [ ] Add "Browse" button next to output directory entry
- [ ] Button opens native directory picker dialog
- [ ] Selected path populates the text field
- [ ] Initial directory set to current value or default

#### Technical Implementation
```python
from tkinter import filedialog

def _browse_output_dir(self):
    path = filedialog.askdirectory(
        initialdir=self.output_dir_var.get() or "./outputs"
    )
    if path:
        self.output_dir_var.set(path)
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/gui/app.py` | Connect waveform callback; change styles to dropdown; add debug logging |
| `src/gui/theme.py` | Increase `WINDOW_HEIGHT` from 800 to 900 |
| `src/gui/settings.py` | Add Browse button for output directory |
| `src/main.py` | Add debug logging for refinement call chain |
| `src/refiner.py` | Verify logging is present for Ollama calls |

---

## Verification Checklist

### Bug Fixes
- [ ] BUG-001: Waveform animates during recording showing voice levels
- [ ] BUG-002: LLM refinement produces output in refined text editor

### Feature Requests
- [ ] FEAT-001: Window fits all UI elements without scrolling
- [ ] FEAT-002: Style selector is a clean dropdown menu
- [ ] FEAT-003: Can browse and select output directory via dialog

### Regression Testing
- [ ] Recording still works correctly
- [ ] Transcription still appends (not replaces)
- [ ] Clear button still works
- [ ] Settings save and persist correctly
- [ ] Export functions work with new output directory

---

## Timeline

| Phase | Items | Est. Effort |
|-------|-------|-------------|
| Phase 1 | BUG-001, BUG-002 | Bug fixes |
| Phase 2 | FEAT-001, FEAT-002 | UI improvements |
| Phase 3 | FEAT-003 | Settings enhancement |
| Phase 4 | Testing & verification | QA |

---

*Generated by Claude Dictate PRD workflow*
