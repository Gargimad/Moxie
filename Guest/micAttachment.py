"""
micAttachment.py - Attach a trailing mic action to a single QLineEdit.
"""

from PyQt6.QtCore import QThread
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QLineEdit, QMessageBox

import Events.theme as theme


def attach_mic_to_line_edit(widget: QLineEdit):
    for a in widget.actions():
        if a.property("moxieMic"):
            return

    try:
        from Guest.voiceWorker import VoiceWorker
    except ImportError as e:
        VoiceWorker = None
        import_error = str(e)
    else:
        import_error = ""

    action = QAction(widget)
    action.setProperty("moxieMic", True)
    action.setIcon(QIcon(theme.asset("mic.png")))
    action.setToolTip("Dictate into this field")

    state: dict[str, QThread | None] = {"worker": None}

    def on_result(text):
        text = (text or "").strip()
        if not text:
            return
        widget.insert(text)
        widget.setFocus()

    def on_error(message):
        QMessageBox.information(widget, "Voice input", message)

    def on_finished():
        state["worker"] = None
        action.setEnabled(True)
        action.setToolTip("Dictate into this field")

    def start():
        if VoiceWorker is None:
            QMessageBox.warning(
                widget, "Voice unavailable",
                "Speech recognition isn't installed on this system.\n\n"
                f"({import_error})",
            )
            return
        worker = VoiceWorker(widget)
        state["worker"] = worker
        worker.transcribed.connect(on_result)
        worker.failed.connect(on_error)
        worker.finished.connect(on_finished)
        action.setEnabled(False)
        action.setToolTip("Listening… speak now")
        worker.start()

    def triggered(_checked=False):
        if state["worker"] is None:
            start()

    action.triggered.connect(triggered)
    widget.addAction(action, QLineEdit.ActionPosition.TrailingPosition)