"""
Text editor widget for Claude Dictate GUI
Displays and allows editing of transcribed/refined text.
"""

import customtkinter as ctk
import pyperclip

from .theme import THEME, FONTS
from .widgets import Tooltip


class TextEditor(ctk.CTkFrame):
    """Text editor panel with header and hover copy button."""

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

        # Hover-revealed action buttons: copy and clear live with the text
        # they act on, so their meaning needs no guessing.
        self.copy_btn = ctk.CTkButton(
            header,
            text="📋",
            font=("", 14),
            width=32,
            height=28,
            fg_color="transparent",
            hover_color=THEME["bg_medium"],
            text_color=THEME["text_muted"],
            corner_radius=6,
            command=self._copy_to_clipboard
        )
        Tooltip(self.copy_btn, f"Copy the {title.lower()}")

        self.clear_btn = ctk.CTkButton(
            header,
            text="🗑",
            font=("", 14),
            width=32,
            height=28,
            fg_color="transparent",
            hover_color=THEME["bg_medium"],
            text_color=THEME["text_muted"],
            corner_radius=6,
            command=self._clear_clicked
        )
        Tooltip(self.clear_btn, f"Clear the {title.lower()}")

        # Initially hidden - pack_forget() isn't needed since we haven't packed it yet
        self._copy_btn_visible = False

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

        # Bind hover events for copy button visibility
        self.bind("<Enter>", self._on_mouse_enter)
        self.bind("<Leave>", self._on_mouse_leave)
        self.textbox.bind("<Enter>", self._on_mouse_enter)
        self.textbox.bind("<Leave>", self._on_mouse_leave)
        header.bind("<Enter>", self._on_mouse_enter)
        header.bind("<Leave>", self._on_mouse_leave)

    def _on_mouse_enter(self, event=None) -> None:
        """Show action buttons when mouse enters the editor."""
        if not self._copy_btn_visible and self.get_text().strip():
            self.copy_btn.pack(side="right", padx=(0, 8))
            self.clear_btn.pack(side="right", padx=(0, 2))
            self._copy_btn_visible = True

    def _on_mouse_leave(self, event=None) -> None:
        """Hide copy button when mouse leaves the editor."""
        # Check if mouse is still within the widget bounds
        try:
            x, y = self.winfo_pointerxy()
            widget_x = self.winfo_rootx()
            widget_y = self.winfo_rooty()
            widget_w = self.winfo_width()
            widget_h = self.winfo_height()

            # Only hide if mouse is actually outside the widget
            if not (widget_x <= x <= widget_x + widget_w and
                    widget_y <= y <= widget_y + widget_h):
                if self._copy_btn_visible:
                    self.copy_btn.pack_forget()
                    self.clear_btn.pack_forget()
                    self._copy_btn_visible = False
        except Exception:
            pass

    def _copy_to_clipboard(self) -> None:
        """Copy text content to clipboard."""
        text = self.get_text()
        if text.strip():
            pyperclip.copy(text)
            # Flash the button to indicate success
            original_color = self.copy_btn.cget("text_color")
            self.copy_btn.configure(text="✓", text_color=THEME["success"])
            self.after(800, lambda: self.copy_btn.configure(
                text="📋", text_color=original_color
            ))

    def _clear_clicked(self) -> None:
        """Clear this panel with a brief confirmation flash."""
        if not self.get_text().strip():
            return
        self.clear()
        self.clear_btn.configure(text="✓", text_color=THEME["success"])
        self.after(800, lambda: self.clear_btn.configure(
            text="🗑", text_color=THEME["text_muted"]
        ))

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
