"""
voiceWorker.py — Background thread for speech-to-text.
Emits transcribed text via a Qt signal.
"""

import speech_recognition as sr
from PyQt6.QtCore import QThread, pyqtSignal


class VoiceWorker(QThread):
    """Listens to the microphone and emits the transcribed text."""

    transcribed = pyqtSignal(str)   # emitted with the recognized text
    failed = pyqtSignal(str)        # emitted on error

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recognizer = sr.Recognizer()
        self._running = False

    def run(self):
        """Capture one utterance from the mic and transcribe it."""
        self._running = True

        try:
            with sr.Microphone() as source:
                self.recognizer.pause_threshold = 0.6
                self.recognizer.adjust_for_ambient_noise(
                    source, duration=0.25
                )
                # Listen for speech (blocks until the user stops talking)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            self.failed.emit("No speech detected. Try again.")
            return
        except (OSError, AttributeError) as e:
            self.failed.emit(f"Microphone unavailable: {e}")
            return

        try:
            # Google's free recognition service (no API key needed)
            text = self.recognizer.recognize_google(audio)
            self.transcribed.emit(text)
        except sr.UnknownValueError:
            self.failed.emit("Couldn't understand the audio.")
        except sr.RequestError as e:
            self.failed.emit(f"Speech service error: {e}")

    def stop(self):
        self._running = False