"""
Text editor widget for Claude Dictate GUI
Displays and allows editing of transcribed/refined text.
"""

import customtkinter as ctk

from .theme import THEME, FONTS


class TextEditor(ctk.CTkFrame):
    """Text editor panel with header."""

    def __init__(self, master, title: str, **kwargs):
        """
        Initialize text editor.

        Args:
            master: Parent widget
            title: Editor panel title
            **kwargs: Additional frame arguments
        """
        super().__init__(
            master,
            fg_color=THEME["bg_light"],
            corner_radius=12,
            **kwargs
        )

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        self.title_label = ctk.CTkLabel(
            header,
            text=title,
            font=FONTS["heading"],
            text_color=THEME["text_primary"]
        )
        self.title_label.pack(side="left")

        # Word count label
        self.word_count_label = ctk.CTkLabel(
            header,
            text="",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        )
        self.word_count_label.pack(side="right")

        # Text area
        self.textbox = ctk.CTkTextbox(
            self,
            font=FONTS["mono"],
            fg_color=THEME["bg_medium"],
            text_color=THEME["text_primary"],
            border_width=1,
            border_color=THEME["border"],
            corner_radius=8,
            wrap="word"
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Bind text change for word count
        self.textbox.bind("<KeyRelease>", self._update_word_count)

    def get_text(self) -> str:
        """Get text content."""
        return self.textbox.get("1.0", "end-1c")

    def set_text(self, text: str) -> None:
        """
        Set text content.

        Args:
            text: Text to display
        """
        # Ensure textbox is editable before and after setting text
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self.textbox.configure(state="normal")  # Keep editable
        self._update_word_count()

    def append_text(self, text: str) -> None:
        """
        Append text to the editor (for streaming).

        Args:
            text: Text to append
        """
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text)
        self.textbox.see("end")
        self.textbox.configure(state="normal")  # Keep editable
        self._update_word_count()

    def clear(self) -> None:
        """Clear text content."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="normal")  # Keep editable
        self._update_word_count()

    def set_title(self, title: str) -> None:
        """
        Update the editor title.

        Args:
            title: New title
        """
        self.title_label.configure(text=title)

    def _update_word_count(self, event=None) -> None:
        """Update the word count display."""
        text = self.get_text()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self.word_count_label.configure(text=f"{words} words, {chars} chars")

    def set_readonly(self, readonly: bool = True) -> None:
        """
        Set editor to readonly mode.

        Args:
            readonly: Whether to make editor readonly
        """
        if readonly:
            self.textbox.configure(state="disabled")
        else:
            self.textbox.configure(state="normal")

    def highlight_text(self, start: str, end: str, tag: str = "highlight") -> None:
        """
        Highlight a portion of text.

        Args:
            start: Start index (e.g., "1.0")
            end: End index (e.g., "1.10")
            tag: Tag name for the highlight
        """
        self.textbox.tag_add(tag, start, end)
        self.textbox.tag_config(tag, background=THEME["accent"], foreground=THEME["bg_dark"])

    def clear_highlights(self, tag: str = "highlight") -> None:
        """
        Clear all highlights with the given tag.

        Args:
            tag: Tag name to clear
        """
        self.textbox.tag_remove(tag, "1.0", "end")
