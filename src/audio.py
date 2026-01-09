"""
Audio recording module for Claude Dictate
Handles audio recording with push-to-talk functionality.
"""

import wave
import tempfile
import threading
from typing import Optional, Callable, List

import pyaudio


class AudioRecorder:
    """Handles audio recording with push-to-talk functionality."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        device_index: Optional[int] = None,
        on_level_update: Optional[Callable[[float], None]] = None
    ):
        """
        Initialize the audio recorder.

        Args:
            sample_rate: Audio sample rate in Hz (default 16000 for Whisper)
            channels: Number of audio channels (1 for mono)
            chunk_size: Size of audio chunks to read
            device_index: Index of input device (None for default)
            on_level_update: Callback for audio level updates (0.0-1.0)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.device_index = device_index
        self.on_level_update = on_level_update

        self.audio: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.frames: List[bytes] = []
        self.is_recording = False
        self.record_thread: Optional[threading.Thread] = None

    @staticmethod
    def get_input_devices() -> List[dict]:
        """
        Get list of available audio input devices.

        Returns:
            List of dicts with 'index', 'name', and 'channels' for each device.
        """
        devices = []
        audio = pyaudio.PyAudio()
        try:
            for i in range(audio.get_device_count()):
                try:
                    info = audio.get_device_info_by_index(i)
                    if info.get('maxInputChannels', 0) > 0:
                        devices.append({
                            'index': i,
                            'name': info.get('name', f'Device {i}'),
                            'channels': info.get('maxInputChannels', 1)
                        })
                except Exception:
                    continue
        finally:
            audio.terminate()
        return devices

    def set_device(self, device_index: Optional[int]) -> None:
        """Set the input device index."""
        self.device_index = device_index

    def start_recording(self) -> None:
        """Start recording audio."""
        if self.is_recording:
            return

        self.frames = []
        self.is_recording = True

        # Create fresh PyAudio instance for each recording session
        if self.audio is None:
            self.audio = pyaudio.PyAudio()

        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk_size
        )

        self.record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.record_thread.start()

    def _record_loop(self) -> None:
        """Recording loop that runs in a separate thread."""
        while self.is_recording and self.stream:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.frames.append(data)

                # Calculate audio level for visualization
                if self.on_level_update:
                    level = self._calculate_level(data)
                    self.on_level_update(level)

            except Exception as e:
                print(f"Recording error: {e}")
                break

    def _calculate_level(self, data: bytes) -> float:
        """Calculate audio level from raw data (0.0-1.0)."""
        import struct

        # Unpack 16-bit audio samples
        count = len(data) // 2
        shorts = struct.unpack(f"{count}h", data)

        # Calculate RMS
        sum_squares = sum(s * s for s in shorts)
        rms = (sum_squares / count) ** 0.5

        # Normalize to 0.0-1.0 (max 16-bit value is 32768)
        # Use 15x amplification for better visualization of typical speech levels
        level = min(1.0, rms / 32768.0 * 15)
        return level

    def stop_recording(self) -> Optional[str]:
        """
        Stop recording and return path to WAV file.

        Returns:
            Path to the temporary WAV file, or None if no audio was recorded.
        """
        if not self.is_recording:
            return None

        self.is_recording = False

        if self.record_thread:
            self.record_thread.join(timeout=1.0)

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if not self.frames:
            # No audio captured, still clean up PyAudio
            if self.audio:
                self.audio.terminate()
                self.audio = None
            return None

        # Get sample width before terminating PyAudio
        sample_width = self.audio.get_sample_size(pyaudio.paInt16) if self.audio else 2

        # Save to temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(temp_file.name, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.frames))

        # Terminate PyAudio so next recording gets fresh instance
        if self.audio:
            self.audio.terminate()
            self.audio = None

        return temp_file.name

    def cleanup(self) -> None:
        """Clean up audio resources."""
        self.is_recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.audio:
            self.audio.terminate()
            self.audio = None

    def __del__(self):
        """Destructor to ensure resources are cleaned up."""
        self.cleanup()
