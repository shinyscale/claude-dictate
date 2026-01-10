"""
System tray integration for Claude Dictate
Provides minimize-to-tray functionality with context menu.
"""

import threading
from typing import Callable, Optional
import io

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    pystray = None
    Image = None
    ImageDraw = None


def is_tray_available() -> bool:
    """Check if system tray functionality is available."""
    return TRAY_AVAILABLE


def create_tray_icon() -> Optional["Image.Image"]:
    """Create a simple microphone icon for the system tray."""
    if not TRAY_AVAILABLE:
        return None

    # Create a 64x64 image with transparent background
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw a microphone shape
    # Mic body (rounded rectangle)
    mic_color = (255, 107, 53, 255)  # Orange accent color
    draw.rounded_rectangle(
        [(22, 8), (42, 36)],
        radius=10,
        fill=mic_color
    )

    # Mic stand (arc)
    draw.arc(
        [(16, 20), (48, 48)],
        start=0,
        end=180,
        fill=mic_color,
        width=4
    )

    # Mic stand vertical line
    draw.line([(32, 44), (32, 52)], fill=mic_color, width=4)

    # Mic stand base
    draw.line([(22, 52), (42, 52)], fill=mic_color, width=4)

    return image


class SystemTray:
    """System tray icon manager for Claude Dictate."""

    def __init__(
        self,
        on_show: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        on_exit: Optional[Callable] = None
    ):
        """
        Initialize the system tray.

        Args:
            on_show: Callback when "Show" is clicked
            on_settings: Callback when "Settings" is clicked
            on_exit: Callback when "Exit" is clicked
        """
        self.on_show = on_show
        self.on_settings = on_settings
        self.on_exit = on_exit
        self.icon: Optional["pystray.Icon"] = None
        self._running = False
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _create_menu(self) -> "pystray.Menu":
        """Create the system tray context menu."""
        if not TRAY_AVAILABLE:
            return None

        return pystray.Menu(
            pystray.MenuItem(
                "Show Claude Dictate",
                self._on_show,
                default=True  # Double-click action
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Settings",
                self._on_settings
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                self._on_exit
            )
        )

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
            # Create new icon with different color based on state
            size = 64
            image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)

            # Red when recording, orange otherwise
            mic_color = (244, 67, 54, 255) if recording else (255, 107, 53, 255)

            # Draw microphone
            draw.rounded_rectangle([(22, 8), (42, 36)], radius=10, fill=mic_color)
            draw.arc([(16, 20), (48, 48)], start=0, end=180, fill=mic_color, width=4)
            draw.line([(32, 44), (32, 52)], fill=mic_color, width=4)
            draw.line([(22, 52), (42, 52)], fill=mic_color, width=4)

            self.icon.icon = image
            self.icon.title = "Claude Dictate - Recording..." if recording else "Claude Dictate"

        except Exception as e:
            print(f"[Tray] Error updating icon: {e}")

    @property
    def is_running(self) -> bool:
        """Check if tray icon is currently running."""
        return self._running
