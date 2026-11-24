"""
globalMic.py - App-wide voice dictation button.

A small round mic button floats in the bottom-right corner of the main
window. Click it, speak, and the transcript is inserted at the cursor
of whatever text field was most recently focused (tracked by
focusTracker.py).

Design notes:
    - Reuses voiceWorker.VoiceWorker; same recognition stack as the
      chat's own mic.
    - While listening, the button pulses (colour + text change) so
      it's obvious something is happening.
    - If no field has focus, shows a hint instead of failing.
    - If speech_recognition / pyaudio are missing, shows a clear
      message the first time only.
"""

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QMessageBox, QPushButton

import Guest.focusTracker as focusTracker

# Size and position of the floating button.
SIZE = 44
MARGIN = 20


class GlobalMicButton(QPushButton):
    def __init__(self, parent):
        super().__init__("🎙️", parent)
        self.setObjectName("GlobalMic")
        self.setFixedSize(SIZE, SIZE)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Dictate into the focused field")
        self._voice_worker = None
        self._miss_import_warned = False
        self.clicked.connect(self._on_clicked)

        # Make sure it stays on top of child widgets.
        self.raise_()

    # ── Position ───────────────────────────────────────────────────
    def reposition(self):
        """Anchor to the bottom-right of the parent window."""
        if not self.parent():
            return
        pw = self.parent().width()
        ph = self.parent().height()
        self.move(QPoint(pw - SIZE - MARGIN, ph - SIZE - MARGIN))

    # ── Click handling ─────────────────────────────────────────────
    def _on_clicked(self):
        if self._voice_worker is not None:
            self._stop_voice()
            return
        self._start_voice()

    def _start_voice(self):
        # Lazy import so the app still launches if the deps are missing.
        try:
            from Guest.voiceWorker import VoiceWorker
        except Exception as e:
            if not self._miss_import_warned:
                self._miss_import_warned = True
                QMessageBox.warning(
                    self, "Voice unavailable",
                    "Speech recognition isn't installed on this "
                    f"system.\n\n({e})"
                )
            return

        # Pre-flight: is there a field to type into?
        target = focusTracker.FocusTracker.get_input()
        if target is None:
            QMessageBox.information(
                self, "Tap a field first",
                "Click into a text field, then tap the mic to dictate."
            )
            return

        self.setProperty("listening", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("■")
        self.setToolTip("Listening… click to stop")

        self._voice_worker = VoiceWorker(self)
        self._voice_worker.transcribed.connect(self._on_result)
        self._voice_worker.failed.connect(self._on_error)
        self._voice_worker.finished.connect(self._on_finished)
        self._voice_worker.start()

    def _stop_voice(self):
        if self._voice_worker is None:
            return
        self._voice_worker.stop()
        # finished will fire when the thread actually exits.

    def _on_result(self, text):
        text = (text or "").strip()
        if not text:
            return

        # Re-check the target — the user may have clicked elsewhere
        # while the mic was listening.
        target = focusTracker.FocusTracker.get_input()
        if target is None:
            QMessageBox.information(
                self, "Voice input",
                f"Heard: “{text}”\n\n"
                "But no text field is focused right now. Click a "
                "field and try again."
            )
            return

        # Insert at cursor, with a separating space if needed.
        try:
            existing = target.text() if hasattr(target, "text") \
                else target.toPlainText()
        except Exception:
            existing = ""

        cursor = target.textCursor() if hasattr(target, "textCursor") \
            else None

        if hasattr(target, "insert"):
            # QLineEdit / QTextEdit both have insert().
            if existing and not existing.endswith(" "):
                target.insert(" ")
            target.insert(text)
        else:
            # Fallback — append.
            if existing and not existing.endswith(" "):
                target.setText(existing + " " + text)
            else:
                target.setText(existing + text)

        # Put the cursor at the end.
        if cursor is not None and hasattr(target, "setTextCursor"):
            new_cursor = target.textCursor()
            new_cursor.movePosition(new_cursor.MoveOperation.End)
            target.setTextCursor(new_cursor)

        # Restore focus so the user can keep typing.
        target.setFocus()

    def _on_error(self, message):
        QMessageBox.information(self, "Voice input", message)

    def _on_finished(self):
        self._voice_worker = None
        self.setProperty("listening", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("🎙️")
        self.setToolTip("Dictate into the focused field")
