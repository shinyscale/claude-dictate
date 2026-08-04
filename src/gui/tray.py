"""
System tray integration for Claude Dictate
Provides minimize-to-tray functionality with context menu.
"""

import threading
from typing import Callable, Optional
import io

TRAY_AVAILABLE = False
TRAY_ERROR: Optional[str] = None
pystray = None
Image = None
ImageDraw = None

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
    TRAY_ERROR = None
except ImportError as e:
    TRAY_ERROR = str(e)
    print(f"[Tray] Import failed: {TRAY_ERROR}")


def is_tray_available() -> bool:
    """Check if system tray functionality is available."""
    return TRAY_AVAILABLE


def get_tray_error() -> Optional[str]:
    """Get the error message if tray is unavailable."""
    return TRAY_ERROR


def create_tray_icon() -> Optional["Image.Image"]:
    """Create a simple microphone icon for the system tray."""
    if not TRAY_AVAILABLE:
        return None

    # Create a 32x32 image with solid dark background (RGB, not RGBA - Windows compatible)
    size = 32
    image = Image.new('RGB', (size, size), (30, 30, 30))
    draw = ImageDraw.Draw(image)

    # Draw a microphone shape (scaled for 32x32)
    # Mic body (rounded rectangle)
    mic_color = (255, 107, 53)  # Orange accent color (no alpha)
    draw.rounded_rectangle(
        [(11, 4), (21, 18)],
        radius=5,
        fill=mic_color
    )

    # Mic stand (arc)
    draw.arc(
        [(8, 10), (24, 24)],
        start=0,
        end=180,
        fill=mic_color,
        width=2
    )

    # Mic stand vertical line
    draw.line([(16, 22), (16, 26)], fill=mic_color, width=2)

    # Mic stand base
    draw.line([(11, 26), (21, 26)], fill=mic_color, width=2)

    return image


class SystemTray:
    """System tray icon manager for Claude Dictate."""

    def __init__(
        self,
        on_show: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        on_exit: Optional[Callable] = None,
        paste_mode_getter: Optional[Callable[[], str]] = None,
        on_paste_mode_change: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the system tray.

        Args:
            on_show: Callback when "Show" is clicked
            on_settings: Callback when "Settings" is clicked
            on_exit: Callback when "Exit" is clicked
            paste_mode_getter: Returns "raw" or "refined"; when provided,
                the menu grows a radio pair for switching paste modes
            on_paste_mode_change: Called with the newly selected mode
        """
        self.on_show = on_show
        self.on_settings = on_settings
        self.on_exit = on_exit
        self.paste_mode_getter = paste_mode_getter
        self.on_paste_mode_change = on_paste_mode_change
        self.icon: Optional["pystray.Icon"] = None
        self._running = False
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _create_menu(self) -> "pystray.Menu":
        """Create the system tray context menu."""
        if not TRAY_AVAILABLE:
            return None

        items = [
            pystray.MenuItem(
                "Show Claude Dictate",
                self._on_show,
                default=True  # Double-click action
            ),
            pystray.Menu.SEPARATOR,
        ]

        if self.paste_mode_getter:
            items += [
                pystray.MenuItem(
                    "Paste raw transcript",
                    lambda icon, item: self._set_paste_mode("raw"),
                    checked=lambda item: self.paste_mode_getter() == "raw",
                    radio=True,
                ),
                pystray.MenuItem(
                    "Refine, then paste",
                    lambda icon, item: self._set_paste_mode("refined"),
                    checked=lambda item: self.paste_mode_getter() == "refined",
                    radio=True,
                ),
                pystray.Menu.SEPARATOR,
            ]

        items += [
            pystray.MenuItem(
                "Settings",
                self._on_settings
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                self._on_exit
            )
        ]
        return pystray.Menu(*items)

    def _set_paste_mode(self, mode: str) -> None:
        if self.on_paste_mode_change:
            self.on_paste_mode_change(mode)
        if self.icon:
            self.icon.update_menu()

    def _on_show(self, icon, item) -> None:
        """Handle Show menu item click."""
        if self.on_show:
            self.on_show()

    def _on_settings(self, icon, item) -> None:
        """Handle Settings menu item click."""
        if self.on_settings:
            self.on_settings()

    def _on_exit(self, icon, item) -> None:
        """Handle Exit menu item click."""
        self.stop()
        if self.on_exit:
            self.on_exit()

    def start(self) -> bool:
        """
        Start the system tray icon.

        Returns:
            True if started successfully, False if tray not available
        """
        if not TRAY_AVAILABLE:
            print("[Tray] System tray not available (pystray/Pillow not installed)")
            return False

        if self._running:
            print("[Tray] Already running")
            return True

        try:
            image = create_tray_icon()
            menu = self._create_menu()

            self.icon = pystray.Icon(
                name="claude-dictate",
                icon=image,
                title="Claude Dictate",
                menu=menu
            )

            # Run in background thread with setup callback
            self._running = True
            self._ready = threading.Event()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

            # Wait for tray to be ready (up to 2 seconds)
            if self._ready.wait(timeout=2.0):
                print("[Tray] System tray icon started and ready")
            else:
                print("[Tray] System tray icon started (ready state unknown)")

            return True

        except Exception as e:
            print(f"[Tray] Failed to start system tray: {e}")
            import traceback
            traceback.print_exc()
            self._running = False
            return False

    def _run(self) -> None:
        """Run the tray icon (blocking)."""
        if self.icon:
            # Use setup callback to signal readiness
            self.icon.run(setup=self._on_setup)

    def _on_setup(self, icon) -> None:
        """Called when tray icon is ready."""
        # Passing a custom setup= to icon.run() replaces pystray's default
        # setup, which is the thing that sets visible=True. Without this line
        # the icon runs headless: menu and all, but never shown in the tray.
        icon.visible = True
        print("[Tray] Icon setup complete, tray is visible")
        if hasattr(self, '_ready'):
            self._ready.set()

    def stop(self) -> None:
        """Stop the system tray icon."""
        self._running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                print(f"[Tray] Error stopping tray: {e}")
            self.icon = None
        print("[Tray] System tray icon stopped")

    def update_icon(self, recording: bool = False) -> None:
        """
        Update the tray icon state.

        Args:
            recording: True if currently recording (show different color)
        """
        if not TRAY_AVAILABLE or not self.icon:
            return

        try:
            # Create new icon with different color based on state (32x32 RGB for Windows)
            size = 32
            image = Image.new('RGB', (size, size), (30, 30, 30))
            draw = ImageDraw.Draw(image)

            # Red when recording, orange otherwise (no alpha channel)
            mic_color = (244, 67, 54) if recording else (255, 107, 53)

            # Draw microphone (scaled for 32x32)
            draw.rounded_rectangle([(11, 4), (21, 18)], radius=5, fill=mic_color)
            draw.arc([(8, 10), (24, 24)], start=0, end=180, fill=mic_color, width=2)
            draw.line([(16, 22), (16, 26)], fill=mic_color, width=2)
            draw.line([(11, 26), (21, 26)], fill=mic_color, width=2)

            self.icon.icon = image
            self.icon.title = "Claude Dictate - Recording..." if recording else "Claude Dictate"

        except Exception as e:
            print(f"[Tray] Error updating icon: {e}")

    @property
    def is_running(self) -> bool:
        """Check if tray icon is currently running."""
        return self._running
