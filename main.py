"""
main.py - Entry point.

Creates the QApplication, applies the initial theme, and shows Landing.
"""

import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

import Events.theme as theme
import Guest.focusTracker as focusTracker
from Guest.focusTracker import FocusTracker
from Guest.landing import Landing

APP_ID = "Moxie.VolunteerManager.1"


def _set_windows_app_id():
    """
    Tell Windows this process is 'Moxie', not 'python.exe'.

    Without this, the taskbar groups the window under the Python
    interpreter and shows the Python icon, even though setWindowIcon()
    was called. No-op on macOS and Linux.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_ID
        )
    except Exception as e:
        print(f"[main] could not set AppUserModelID: {e}")


def _app_icon():
    """Pick the best icon file present in assets/."""
    for name in ("logoHalfDark.png"):
        path = theme.asset(name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


def main():
    # Must happen before QApplication is created on Windows.
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("Moxie")
    app.setOrganizationName("Moxie")
    app.setApplicationDisplayName("Moxie")

    # Default icon for every top-level window that doesn't override it.
    app.setWindowIcon(_app_icon())
    focusTracker.install(app)
    window = Landing()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
