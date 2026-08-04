"""
Small reusable GUI widgets: fading tooltips and the session history panel.
"""

import tkinter as tk
from typing import Dict, List, Optional

import customtkinter as ctk
import pyperclip

from .theme import THEME, FONTS


def _blend(c1: str, c2: str, t: float) -> str:
    """Linear blend between two #rrggbb colors, t in [0, 1]."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class Tooltip:
    """Delayed, fade-in tooltip attached to any widget.

    The label text can be swapped at runtime via the `text` attribute
    (used by toggle buttons whose meaning flips).
    """

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._dismiss, add="+")
        widget.bind("<ButtonPress>", self._dismiss, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _dismiss(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
            tip.attributes("-alpha", 0.0)
        except Exception:
            pass
        frame = tk.Frame(
            tip, bg=THEME["bg_medium"],
            highlightthickness=1, highlightbackground=THEME["border"],
        )
        frame.pack()
        tk.Label(
            frame, text=self.text,
            bg=THEME["bg_medium"], fg=THEME["text_primary"],
            font=(FONTS["small"][0], 10), justify="left", padx=8, pady=4,
        ).pack()
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + (self.widget.winfo_width() - tip.winfo_width()) // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.geometry(f"+{x}+{y}")
        self._tip = tip
        self._fade(0.0)

    def _fade(self, alpha: float) -> None:
        if self._tip is None:
            return
        alpha = min(alpha + 0.18, 0.96)
        try:
            self._tip.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < 0.96:
            self._tip.after(16, lambda: self._fade(alpha))


class HistoryPanel(ctk.CTkFrame):
    """Collapsible sidebar listing this session's dictations, newest first.

    Purely a viewer: it renders entries handed to refresh() and never
    touches the editors, so it can't interfere with the append workflow.
    Clicking a card copies that dictation back to the clipboard.
    """

    EXPANDED_WIDTH = 300
    COLLAPSED_WIDTH = 44
    SHOW_KINDS = ("raw", "refined")
    MAX_CARDS = 50

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=THEME["bg_light"],
            corner_radius=12,
            width=self.EXPANDED_WIDTH,
            **kwargs,
        )
        self.pack_propagate(False)
        self._collapsed = False
        self._anim_id = None
        self._shown_keys = set()
        self._last_keys: list = []

        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.pack(fill="x", padx=12, pady=(14, 4))

        self.toggle_btn = ctk.CTkButton(
            self._header,
            text="⟫",
            width=28, height=28,
            font=(FONTS["small"][0], 14),
            fg_color="transparent",
            hover_color=THEME["bg_medium"],
            text_color=THEME["text_muted"],
            corner_radius=6,
            command=self.toggle,
        )
        self.toggle_btn.pack(side="right")
        self._toggle_tip = Tooltip(self.toggle_btn, "Collapse history")

        self.title_label = ctk.CTkLabel(
            self._header,
            text="Session History",
            font=FONTS["heading"],
            text_color=THEME["text_primary"],
        )
        self.title_label.pack(side="left")

        self.count_label = ctk.CTkLabel(
            self,
            text="No dictations yet this session",
            font=FONTS["small"],
            text_color=THEME["text_muted"],
        )
        self.count_label.pack(anchor="w", padx=14)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=THEME["bg_medium"],
            scrollbar_button_hover_color=THEME["accent"],
        )
        self.scroll.pack(fill="both", expand=True, padx=6, pady=(6, 10))

    # -- data --

    def refresh(self, entries: List[Dict[str, str]]) -> None:
        """Rebuild the card list from entries (oldest-first input)."""
        shown = [e for e in entries if e["kind"] in self.SHOW_KINDS][-self.MAX_CARDS:]
        keys = [(e["time"], e["kind"], len(e["text"])) for e in shown]
        if keys == self._last_keys:
            return
        new_keys = {k for k in keys if k not in self._shown_keys}
        first_fill = not self._shown_keys
        self._last_keys = keys

        for child in self.scroll.winfo_children():
            child.destroy()

        for entry, key in zip(reversed(shown), reversed(keys)):
            card = self._build_card(entry)
            # A gentle accent wash on cards that just arrived, so a tray
            # dictation visibly lands in the panel without stealing focus.
            if not first_fill and key in new_keys:
                self._flash(card, _blend(THEME["bg_medium"], THEME["accent"], 0.30))

        self._shown_keys.update(keys)
        n = len(shown)
        self.count_label.configure(
            text=f"{n} dictation{'s' if n != 1 else ''} this session"
            if n else "No dictations yet this session"
        )

    def _build_card(self, entry: Dict[str, str]):
        card = ctk.CTkFrame(self.scroll, fg_color=THEME["bg_medium"], corner_radius=8)
        card.pack(fill="x", padx=4, pady=4)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 0))

        kind = entry["kind"]
        kind_color = THEME["accent"] if kind == "refined" else THEME["text_muted"]
        ctk.CTkLabel(
            top, text=kind.upper(),
            font=(FONTS["small"][0], 9, "bold"), text_color=kind_color,
        ).pack(side="left")
        ctk.CTkLabel(
            top, text=entry["time"][11:16],
            font=(FONTS["small"][0], 9), text_color=THEME["text_muted"],
        ).pack(side="right")

        preview = entry["text"]
        if len(preview) > 220:
            preview = preview[:220].rstrip() + "…"
        body = ctk.CTkLabel(
            card, text=preview,
            font=(FONTS["small"][0], 11),
            text_color=THEME["text_secondary"],
            wraplength=self.EXPANDED_WIDTH - 60,
            justify="left", anchor="w",
        )
        body.pack(fill="x", padx=10, pady=(2, 8))

        for w in (card, top, body):
            w.bind("<Button-1>",
                   lambda _e, c=card, t=entry["text"]: self._copy_entry(c, t))
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        return card

    def _copy_entry(self, card, text: str) -> None:
        if not text:
            return
        pyperclip.copy(text)
        self._flash(card, _blend(THEME["bg_medium"], THEME["success"], 0.35))

    def _flash(self, card, from_color: str, steps: int = 14) -> None:
        """Fade a card's background from from_color back to its base."""
        base = THEME["bg_medium"]

        def step(i: int = 0) -> None:
            try:
                if i > steps or not card.winfo_exists():
                    return
                card.configure(fg_color=_blend(from_color, base, i / steps))
                card.after(30, lambda: step(i + 1))
            except Exception:
                pass

        step()

    # -- collapse / expand --

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        if collapsed:
            self.title_label.pack_forget()
            self.count_label.pack_forget()
            self.scroll.pack_forget()
            self.toggle_btn.configure(text="⟪")
            self._toggle_tip.text = "Expand history"
            self._animate_width(self.COLLAPSED_WIDTH)
        else:
            self.toggle_btn.configure(text="⟫")
            self._toggle_tip.text = "Collapse history"
            self._animate_width(self.EXPANDED_WIDTH, on_done=self._repack_content)

    def _repack_content(self) -> None:
        self.title_label.pack(side="left")
        self.count_label.pack(anchor="w", padx=14)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=(6, 10))

    def _animate_width(self, target: int, on_done=None, frames: int = 10) -> None:
        if self._anim_id is not None:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None
        start = self.winfo_width()

        def step(i: int = 1) -> None:
            if i > frames:
                self.configure(width=target)
                self._anim_id = None
                if on_done:
                    on_done()
                return
            t = 1 - (1 - i / frames) ** 3  # ease-out
            self.configure(width=round(start + (target - start) * t))
            self._anim_id = self.after(14, lambda: step(i + 1))

        step()
