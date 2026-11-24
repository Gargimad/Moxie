"""
focusTracker.py - Remembers the last focused text-input widget.

Used by the global microphone button so that dictation knows where to
insert its transcript. We install a QApplication-wide event filter;
whenever a QLineEdit or QTextEdit gains focus, we remember it. The mic
button reads FocusTracker.last_input when the transcript is ready.

If no input has ever been focused, last_input is None and the mic
shows a friendly hint instead of failing silently.
"""

import weakref

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit


class FocusTracker(QObject):
    # Weak reference to the last focused input widget, or None.
    last_input = None

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.FocusIn:
            if isinstance(obj, (QLineEdit, QTextEdit, QPlainTextEdit)):
                # Store a weak ref so closing a page doesn't keep
                # the widget alive.
                FocusTracker.last_input = weakref.ref(obj)
        return super().eventFilter(obj, event)

    @classmethod
    def get_input(cls):
        """Return the last focused input widget, or None."""
        ref = cls.last_input
        if ref is None:
            return None
        widget = ref()
        # The widget may have been destroyed since it was focused.
        if widget is None:
            cls.last_input = None
            return None
        return widget


# Module-level singleton so the whole app shares one filter.
_INSTANCE = FocusTracker()


def install(app):
    """Install the event filter on the QApplication."""
    app.installEventFilter(_INSTANCE)
    return _INSTANCE
