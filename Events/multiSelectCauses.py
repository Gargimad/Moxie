"""
multiSelectCauses.py — A dropdown button that lets the user check one
or more career clusters (shown to volunteers as "Causes").

Emits selectionChanged(list_of_names) whenever the checked set changes.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QMenu, QPushButton

import Events.theme as theme


class MultiSelectCauses(QPushButton):
    selection_changed = pyqtSignal(list)

    def __init__(self, placeholder="All Causes", parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FILTER_COMBO)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._placeholder = placeholder
        self._actions = {}

        menu = QMenu(self)
        self.setMenu(menu)
        self._menu = menu

        self.setText(f"{placeholder}  ▾")

    def set_items(self, items, checked=None):
        self._menu.clear()
        self._actions = {}
        checked = set(checked or [])
        for name in items:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name in checked)
            action.triggered.connect(self._refresh_display)
            self._menu.addAction(action)
            self._actions[name] = action
        self._refresh_display()

    def checked_items(self):
        return [n for n, a in self._actions.items() if a.isChecked()]

    def set_checked(self, names):
        names = set(names or [])
        for n, a in self._actions.items():
            a.setChecked(n in names)
        self._refresh_display()

    def clear_selection(self):
        for a in self._actions.values():
            a.setChecked(False)
        self._refresh_display()

    def _refresh_display(self, *_args):
        checked = self.checked_items()
        if not checked:
            self.setText(f"{self._placeholder}  ▾")
        elif len(checked) == 1:
            self.setText(f"{checked[0]}  ▾")
        else:
            self.setText(f"{len(checked)} causes  ▾")
        self.selection_changed.emit(checked)
    selectionChanged = property(lambda self: self.selection_changed)  # noqa: N815
