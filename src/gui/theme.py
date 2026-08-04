"""
Theme configuration for Claude Dictate GUI
Color scheme and font definitions.
"""

import tkinter.font as tkfont

# Theme Colors
THEME = {
    "bg_dark": "#0D0D0D",
    "bg_medium": "#1A1A1A",
    "bg_light": "#262626",
    "accent": "#FF6B35",
    "accent_hover": "#FF8555",
    "accent_secondary": "#4ECDC4",
    "action_green": "#2E7D32",  # Dark green for action buttons
    "action_green_hover": "#388E3C",  # Slightly lighter green for hover
    "text_primary": "#FFFFFF",
    "text_secondary": "#A0A0A0",
    "text_muted": "#666666",
    "success": "#4CAF50",
    "warning": "#FFC107",
    "error": "#F44336",
    "border": "#333333",
}

# Font stacks, most-preferred first.
#
# Tk silently substitutes its own generic sans when a family is missing, so a
# misspelled or absent family degrades invisibly rather than raising. The old
# defaults here asked for SF Pro Display / SF Pro Text / JetBrains Mono -- all
# macOS or opt-in installs -- which meant every label on Windows rendered in
# Tk's fallback and nothing in the UI was actually using the font it declared.
# resolve_fonts() picks the first family that is genuinely installed.
FONT_STACKS = {
    # Chrome and labels.
    "ui": [
        "Segoe UI Variable Text",
        "Segoe UI",
        "Inter",
        "Helvetica Neue",
        "Helvetica",
    ],
    # Titles and headings; the Display optical size is tuned for large sizes.
    "display": [
        "Segoe UI Variable Display",
        "Segoe UI Semibold",
        "Segoe UI",
        "Helvetica Neue",
        "Helvetica",
    ],
    # Transcript / code. Cascadia Code ships with Windows Terminal, so text set
    # in it reads as part of the terminal rather than as a foreign window.
    "mono": [
        "Cascadia Code",
        "Cascadia Mono",
        "JetBrains Mono",
        "Consolas",
        "Courier New",
    ],
}

# Static defaults: correct on a stock Windows 11 box, and used verbatim if
# resolve_fonts() is never called or Tk can't enumerate families.
FONTS = {
    "title": ("Segoe UI Variable Display", 28, "bold"),
    "heading": ("Segoe UI Variable Display", 18, "bold"),
    "body": ("Segoe UI Variable Text", 14),
    "small": ("Segoe UI Variable Text", 12),
    "mono": ("Cascadia Code", 13),
    "pill": ("Segoe UI Variable Text", 12, "bold"),  # overlay state word
}

_fonts_resolved = False


def _first_installed(stack, installed):
    """First family in `stack` that Tk reports as installed, else stack[-1]."""
    for family in stack:
        if family.lower() in installed:
            return family
    return stack[-1]


def resolve_fonts() -> dict:
    """
    Replace the declared font families with ones actually present on this
    machine. Mutates FONTS in place so modules that already did
    `from .theme import FONTS` see the result.

    Must be called after a Tk root exists (tkfont.families() needs an
    interpreter). Safe to call more than once; only the first call does work.
    """
    global _fonts_resolved
    if _fonts_resolved:
        return FONTS

    try:
        installed = {name.lower() for name in tkfont.families()}
    except Exception as e:  # no root yet, or a headless/broken display
        print(f"[Theme] Could not enumerate fonts, keeping defaults: {e}")
        return FONTS

    if not installed:
        return FONTS

    ui = _first_installed(FONT_STACKS["ui"], installed)
    display = _first_installed(FONT_STACKS["display"], installed)
    mono = _first_installed(FONT_STACKS["mono"], installed)

    FONTS.update({
        "title": (display, 28, "bold"),
        "heading": (display, 18, "bold"),
        "body": (ui, 14),
        "small": (ui, 12),
        "mono": (mono, 13),
        "pill": (ui, 12, "bold"),
    })

    _fonts_resolved = True
    print(f"[Theme] Fonts resolved: ui={ui!r} display={display!r} mono={mono!r}")
    return FONTS


# Window dimensions
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 700
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600
LEFT_PANEL_WIDTH = 320
