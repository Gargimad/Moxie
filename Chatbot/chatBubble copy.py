"""
chatBubble.py — A self-contained messaging-style chat widget for Moxie.

Public API (all on ChatView):
    view = ChatView(greeting="...", parent=None, history_path=...)
        # history_path: JSON file used to keep the chat between runs
        # (default ~/.moxie/chat_history.json, None disables saving)
    view.set_send_handler(fn)              # fn(text) called on send
    view.set_system_prompt_provider(fn)    # fn() -> str, refreshed per send
    view.get_system_prompt()               # -> str
    view.on_reply(text)                    # call when the AI replies
    view.on_error(message)                 # call when the AI fails
    view.set_busy(bool)                    # lock/unlock the composer
    view.reset()                           # clear and greet again
    view.history                           # list[{role, content}, ...]

ChatView knows nothing about HTTP or Groq. The caller wires a backend
by passing a send handler that starts a worker and later calls
view.on_reply() / view.on_error().
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Emoji icons. Each is a single codepoint (no variation selector), which
# renders at full width on Windows instead of a thin, narrow glyph.
SEND_GLYPH = "➤"
MIC_GLYPH = "🎙️"
NEW_CHAT_GLYPH = "✛"

# Solid button colours (no transparency).
ICON_BG = "#2D1A3E"          # matches the user bubble colour
ICON_HOVER_BG = "#4A2C66"
ICON_PRESSED_BG = "#1F1129"
ICON_CHECKED_BG = "#C62828"  # red while the mic is listening
ICON_BORDER = "#8C8C8C"

BTN_SIZE = 40
BTN_FONT_PX = 20

# Where the chat log is saved between sessions, and how many messages
# to keep on disk. Pass history_path=None to ChatView to disable saving.
DEFAULT_HISTORY_PATH = Path.home() / ".moxie" / "chat_history.json"
MAX_SAVED_MESSAGES = 500


class ChatView(QWidget):
    """A messaging-style chat panel with bubbles, grouping, typing dots,
    timestamps, a date separator, and a rounded composer. One class."""

    def __init__(self,
                 greeting="Hi! I'm Moxie. How can I help?",
                 parent=None,
                 history_path=DEFAULT_HISTORY_PATH):
        super().__init__(parent)

        self._history_path = history_path   # None = don't persist
        self._log = []                      # saved transcript with dates
        self._greeting = greeting
        self._send_handler = None
        self._system_prompt_provider = None
        self._typing_bubble = None
        self._typing_timer = None
        self._typing_step = 0
        self._last_who = None
        self._is_busy = False
        self.history = []          # [{role, content}, ...]
        self._voice_worker = None

        self._build_ui()
        self._restore()

    # ── Public API ────────────────────────────────────────────────────
    def set_send_handler(self, fn):
        """fn(text: str) is called when the user sends a message."""
        self._send_handler = fn

    def set_system_prompt_provider(self, fn):
        """fn() -> str, called on every send to get a fresh prompt."""
        self._system_prompt_provider = fn

    def get_system_prompt(self):
        if self._system_prompt_provider:
            return self._system_prompt_provider()
        return "You are a helpful assistant."

    def on_reply(self, text):
        """Deliver the AI's reply to the chat view."""
        self._hide_typing()
        self.history.append({"role": "assistant", "content": text})
        self._log_message("assistant", text)
        self._append_bubble(text, who="assistant")
        self.set_busy(False)

    def on_error(self, message):
        """Deliver an error message to the chat view."""
        self._hide_typing()
        # Don't add errors to history — they aren't part of the
        # conversation the model should see.
        self._append_bubble(message, who="assistant")
        self.set_busy(False)

    def set_busy(self, busy):
        """
        While a reply is in flight, only the input is locked. The
        three composer buttons stay enabled and visible regardless
        of state.
        """
        self._is_busy = busy
        self.input.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def reset(self):
        """Start a new chat: clear the transcript and saved history,
        then greet again."""
        self._clear_transcript()
        self.history = []
        self._log = []
        self._delete_saved()
        self._show_greeting()

    # ── Persistence ───────────────────────────────────────────────────
    def _clear_transcript(self):
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._hide_typing()
        self._last_who = None

    def _show_greeting(self):
        self._append_date_separator("Today")
        self._append_bubble(self._greeting, who="assistant")

    def _trim_history(self):
        """Keep the model-facing history short and starting on a user turn."""
        self.history = self.history[-20:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def _log_message(self, role, content):
        """Add a message to the saved transcript and write it to disk."""
        now = datetime.now()
        self._log.append({
            "role": role,
            "content": content,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
        })
        self._log = self._log[-MAX_SAVED_MESSAGES:]
        self._write_saved()

    def _read_saved(self):
        if not self._history_path:
            return []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [
            e for e in data
            if isinstance(e, dict) and
            e.get("role") in ("user", "assistant") and
            isinstance(e.get("content"), str)
        ]

    def _write_saved(self):
        if not self._history_path:
            return
        try:
            path = Path(self._history_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._log, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[chat] Could not save history: {e}")

    def _delete_saved(self):
        if not self._history_path:
            return
        try:
            Path(self._history_path).unlink(missing_ok=True)
        except OSError as e:
            print(f"[chat] Could not delete history: {e}")

    @staticmethod
    def _date_label(iso_date):
        try:
            d = date.fromisoformat(iso_date)
        except ValueError:
            return iso_date
        today = date.today()
        if d == today:
            return "Today"
        if d == today - timedelta(days=1):
            return "Yesterday"
        return f"{d:%B} {d.day}, {d.year}"

    def _restore(self):
        """Rebuild the transcript from disk, or greet if there's none."""
        self._clear_transcript()
        saved = self._read_saved()
        if not saved:
            self.history = []
            self._log = []
            self._show_greeting()
            return

        last_date = None
        for entry in saved:
            d = entry.get("date", "")
            if d and d != last_date:
                self._append_date_separator(self._date_label(d))
                last_date = d
                self._last_who = None   # new day starts a fresh group
            self._append_bubble(
                entry["content"],
                who=entry["role"],
                timestamp=entry.get("time"),
            )

        self._log = saved[-MAX_SAVED_MESSAGES:]
        self.history = [
            {"role": e["role"], "content": e["content"]} for e in saved
        ]
        self._trim_history()

    # ── UI construction ───────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.content = QWidget()
        self.chat_layout = QVBoxLayout(self.content)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch(1)   # keeps bubbles pushed to the top
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        # ── Composer ─────────────────────────────────────────────────
        composer = QFrame()
        composer.setObjectName("ChatComposer")
        composer.setStyleSheet(
            "QFrame#ChatComposer {"
            "  background: rgba(127,127,127,20);"
            "  border-radius: 24px;"
            "  padding: 4px;"
            "}"
        )
        cl = QHBoxLayout(composer)
        cl.setContentsMargins(8, 4, 6, 4)
        cl.setSpacing(6)

        self.input = QLineEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Message Moxie...")
        self.input.setStyleSheet(
            "QLineEdit#ChatInput {"
            "  border: none;"
            "  background: transparent;"
            "  padding: 6px 4px;"
            "  font-size: 13px;"
            "}"
        )
        self.input.setMinimumWidth(80)
        self.input.returnPressed.connect(self._on_send_clicked)
        cl.addWidget(self.input, 1)

        # ── Three emoji buttons — same size, same style ───────────
        self.send_btn = self._make_icon_button(
            SEND_GLYPH, "Send", BTN_SIZE, font_px=BTN_FONT_PX
        )
        self.send_btn.clicked.connect(self._on_send_clicked)
        cl.addWidget(self.send_btn, 0)

        self.mic_btn = self._make_icon_button(
            MIC_GLYPH, "Dictate your message", BTN_SIZE, font_px=BTN_FONT_PX
        )
        self.mic_btn.setCheckable(True)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        cl.addWidget(self.mic_btn, 0)

        self.clear_btn = self._make_icon_button(
            NEW_CHAT_GLYPH, "New chat", BTN_SIZE, font_px=BTN_FONT_PX
        )
        self.clear_btn.clicked.connect(self._on_new_chat)
        cl.addWidget(self.clear_btn, 0)

        outer.addWidget(composer)

    def _make_icon_button(self, glyph, tooltip, size, font_px=20):
        """
        Solid, clearly visible emoji button.

        Padding is zeroed (Qt's default button padding squeezes emoji
        inside a small circle) and the font size is set in pixels in the
        stylesheet, because a stylesheet font-family would otherwise
        override any size set with setFont().
        """
        btn = QPushButton(glyph)
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)

        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {ICON_BG};"
            f"  border: 1px solid {ICON_BORDER};"
            f"  border-radius: {size // 2}px;"
            f"  padding: 0px;"
            f"  margin: 0px;"
            f"  font-family: 'Segoe UI Emoji', 'Apple Color Emoji', "
            f"'Noto Color Emoji';"
            f"  font-size: {font_px}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {ICON_HOVER_BG}; }}"
            f"QPushButton:pressed {{ background-color: {ICON_PRESSED_BG}; }}"
            f"QPushButton:checked {{ background-color: {ICON_CHECKED_BG}; }}"
        )
        return btn

    # ── Bubble rendering ──────────────────────────────────────────────
    def _append_bubble(self, text, who="assistant", timestamp=None):
        """Build a single message row inline (no helper class)."""
        is_user = who == "user"
        grouped = (self._last_who == who)
        self._last_who = who

        row = QWidget()
        outer = QHBoxLayout(row)
        outer.setContentsMargins(
            8, 1 if grouped else 4, 8, 1 if grouped else 4
        )
        outer.setSpacing(8)

        # Assistant avatar (first bubble of a group only).
        if not is_user:
            if grouped:
                spacer = QLabel()
                spacer.setFixedSize(28, 28)
                outer.addWidget(spacer, 0, Qt.AlignmentFlag.AlignTop)
            else:
                avatar = QLabel("M")
                avatar.setFixedSize(28, 28)
                avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                avatar.setStyleSheet(
                    "background: #2D1A3E;"
                    " color: #F5F0EE;"
                    " border-radius: 14px;"
                    " font-size: 13px;"
                    " font-weight: bold;"
                )
                outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bubble.setMaximumWidth(440)
        bubble.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        bubble.setStyleSheet(self._bubble_qss(is_user, grouped))
        col.addWidget(bubble)

        if not grouped:
            ts = QLabel(timestamp or datetime.now().strftime("%H:%M"))
            ts.setStyleSheet(
                "color: rgba(140,140,140,180);"
                "font-size: 10px;"
                "padding: 0 6px;"
            )
            ts.setAlignment(
                Qt.AlignmentFlag.AlignRight if is_user
                else Qt.AlignmentFlag.AlignLeft
            )
            col.addWidget(ts)

        if is_user:
            outer.addStretch(1)
            outer.addLayout(col)
        else:
            outer.addLayout(col)
            outer.addStretch(1)

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    @staticmethod
    def _bubble_qss(is_user, grouped):
        if is_user:
            bg = "#2D1A3E"
            fg = "#F5F0EE"
            radii = (16, 16, 16, 16) if grouped else (16, 16, 4, 16)
        else:
            bg = "rgba(127,127,127,32)"
            fg = "palette(text)"
            radii = (16, 16, 16, 16) if grouped else (4, 16, 16, 16)

        tl, tr, br, bl = radii
        return (
            f"background: {bg};"
            f"color: {fg};"
            f"border-top-left-radius: {tl}px;"
            f"border-top-right-radius: {tr}px;"
            f"border-bottom-right-radius: {br}px;"
            f"border-bottom-left-radius: {bl}px;"
            "padding: 8px 12px;"
            "font-size: 13px;"
        )

    def _append_date_separator(self, label="Today"):
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(8)

        left = QFrame()
        left.setFrameShape(QFrame.Shape.HLine)
        left.setStyleSheet("color: rgba(127,127,127,60);")
        left.setFixedHeight(1)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            "color: rgba(140,140,140,200);"
            "font-size: 11px;"
            "font-weight: 600;"
            "padding: 0 6px;"
        )

        right = QFrame()
        right.setFrameShape(QFrame.Shape.HLine)
        right.setStyleSheet("color: rgba(127,127,127,60);")
        right.setFixedHeight(1)

        lay.addWidget(left, 1)
        lay.addWidget(lbl, 0)
        lay.addWidget(right, 1)

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrap)

    def _scroll_to_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Typing indicator ──────────────────────────────────────────────
    def _show_typing(self):
        if self._typing_bubble is not None:
            return
        self._typing_bubble = self._append_typing_bubble()
        self._typing_step = 0
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(450)
        self._typing_timer.timeout.connect(self._tick_typing)
        self._typing_timer.start()

    def _append_typing_bubble(self):
        """A bare-bones assistant bubble used only for the dots."""
        row = QWidget()
        outer = QHBoxLayout(row)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(8)

        avatar = QLabel("M")
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background: #2D1A3E;"
            " color: #F5F0EE;"
            " border-radius: 14px;"
            " font-size: 13px;"
            " font-weight: bold;"
        )
        outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        dots = QLabel(".  .  .")
        dots.setStyleSheet(
            "background: rgba(127,127,127,32);"
            "color: rgba(140,140,140,200);"
            "border-top-left-radius: 4px;"
            "border-top-right-radius: 16px;"
            "border-bottom-right-radius: 16px;"
            "border-bottom-left-radius: 16px;"
            "padding: 8px 14px;"
            "font-size: 11px;"
            "letter-spacing: 2px;"
        )
        outer.addWidget(dots, 0, Qt.AlignmentFlag.AlignTop)
        outer.addStretch(1)

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)
        self._last_who = "assistant"
        return row

    def _tick_typing(self):
        if self._typing_bubble is None:
            return
        self._typing_step = (self._typing_step + 1) % 3
        frames = [".  .  .", " .  .  ", "  .  . "]
        labels = self._typing_bubble.findChildren(QLabel)
        if len(labels) >= 2:
            labels[1].setText(frames[self._typing_step])

    def _hide_typing(self):
        if self._typing_timer:
            self._typing_timer.stop()
            self._typing_timer = None
        if self._typing_bubble is None:
            return
        self.chat_layout.removeWidget(self._typing_bubble)
        self._typing_bubble.setParent(None)
        self._typing_bubble.deleteLater()
        self._typing_bubble = None
        # So the real reply starts a fresh group with its own avatar.
        self._last_who = None

    # ── Voice input ───────────────────────────────────────────────────
    def _on_mic_clicked(self):
        """Start or stop voice input."""
        if self._voice_worker is not None:
            try:
                self._voice_worker.stop()
            except Exception:
                pass
            self.mic_btn.setChecked(False)
            return

        try:
            from Guest.voiceWorker import VoiceWorker
        except Exception as e:
            print(f"[chat] VoiceWorker import failed: {e}")
            self.mic_btn.setChecked(False)
            return

        self.mic_btn.setChecked(True)
        self.input.setPlaceholderText("Listening... speak now")

        self._voice_worker = VoiceWorker()
        self._voice_worker.transcribed.connect(self._on_voice_result)
        self._voice_worker.failed.connect(self._on_voice_error)
        self._voice_worker.finished.connect(self._on_voice_finished)
        self._voice_worker.start()

    def _on_voice_result(self, text):
        self.input.setText(text)
        self.input.setPlaceholderText("Message Moxie...")
        self.mic_btn.setChecked(False)

    def _on_voice_error(self, message):
        self.input.setPlaceholderText("Message Moxie...")
        self.mic_btn.setChecked(False)
        print(f"[chat] Voice error: {message}")

    def _on_voice_finished(self):
        self._voice_worker = None
        self.mic_btn.setChecked(False)
        self.input.setPlaceholderText("Message Moxie...")

    # ── Event handlers ────────────────────────────────────────────────
    def _on_send_clicked(self):
        text = self.input.text().strip()
        if not text or self._is_busy:
            return
        self.input.clear()
        self.history.append({"role": "user", "content": text})
        self._trim_history()
        self._log_message("user", text)

        self._append_bubble(text, who="user")
        self.set_busy(True)
        self._show_typing()

        if self._send_handler:
            self._send_handler(text)
        else:
            self.on_error("(No send handler configured.)")

    def _on_new_chat(self):
        if self._is_busy:
            return
        self.reset()
