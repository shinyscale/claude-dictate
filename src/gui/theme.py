"""
Theme configuration for Claude Dictate GUI
Color scheme and font definitions.
"""

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

# Font Configuration
FONTS = {
    "title": ("SF Pro Display", 28, "bold"),
    "heading": ("SF Pro Display", 18, "bold"),
    "body": ("SF Pro Text", 14),
    "small": ("SF Pro Text", 12),
    "mono": ("JetBrains Mono", 13),
}

# Window dimensions
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 900
LEFT_PANEL_WIDTH = 340
