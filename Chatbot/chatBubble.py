"""
chatBubble.py — A self-contained messaging-style chat widget for Moxie.

Public API (all on ChatView):
    view = ChatView(greeting="...", parent=None, history_path=...)
        # history_path: JSON file where every chat is kept between runs
        # (default ~/.moxie/chat_history.json, None disables saving)
    view.set_send_handler(fn)              # fn(text) called on send
    view.set_system_prompt_provider(fn)    # fn() -> str, refreshed per send
    view.get_system_prompt()               # -> str
    view.on_reply(text)                    # call when the AI replies
    view.on_error(message)                 # call when the AI fails
    view.set_busy(bool)                    # lock/unlock the composer
    view.reset()  # start a NEW chat (old ones are kept)
    view.show_history()                    # open the list of past chats
    view.open_session(session_id)          # switch to a past chat
    view.delete_session(session_id)        # delete a past chat
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
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Emoji icons. Each is a single codepoint (no variation selector), which
# renders at full width on Windows instead of a thin, narrow glyph.
HISTORY_GLYPH = "⌛︎"
SEND_GLYPH = "➤"
MIC_GLYPH = "🎙️"
NEW_CHAT_GLYPH = "✛"

BTN_SIZE = 40
BTN_FONT_PX = 20

# Where chats are saved between sessions. Pass history_path=None to
# ChatView to disable saving.
DEFAULT_HISTORY_PATH = Path.home() / ".moxie" / "chat_history.json"
MAX_MESSAGES_PER_CHAT = 500
MAX_SAVED_CHATS = 200


class ChatView(QWidget):
    """A messaging-style chat panel with bubbles, grouping, typing dots,
    timestamps, a date separator, a rounded composer, and a browsable
    list of past chats. One class."""

    def __init__(self,
                 greeting="Hi! I'm Moxie. How can I help?",
                 parent=None,
                 history_path=DEFAULT_HISTORY_PATH):
        super().__init__(parent)
        self.setObjectName("ChatView")

        self._history_path = history_path   # None = don't persist
        self._sessions = []                 # every saved chat
        self._current = None                # active chat (None = new, empty)
        self._greeting = greeting
        self._send_handler = None
        self._system_prompt_provider = None
        self._typing_bubble = None
        self._typing_timer = None
        self._typing_step = 0
        self._last_who = None
        self._is_busy = False
        self.history = []          # [{role, content}, ...] sent to the model
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
        composer buttons stay enabled and visible regardless of state.
        """
        self._is_busy = busy
        self.input.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def reset(self):
        """Start a new chat. The current chat stays saved in the
        history list; nothing is deleted."""
        self._current = None
        self._render_session(None)
        self._write_store()

    def open_session(self, session_id):
        """Switch to a past chat and continue it from where it ended."""
        if self._is_busy:
            return
        session = self._find_session(session_id)
        if session is None:
            return
        self._render_session(session)
        self._write_store()

    def delete_session(self, session_id):
        """Permanently delete a saved chat."""
        session = self._find_session(session_id)
        if session is None:
            return
        self._sessions = [s for s in self._sessions if s is not session]
        if self._current is session:
            self._current = None
            self._render_session(None)
        self._write_store()

    def show_history(self):
        """Open a window listing past chats. Open, continue or delete."""
        if self._is_busy:
            return

        dlg = QDialog(self)
        dlg.setObjectName("ChatHistoryDialog")
        dlg.setWindowTitle("Chat history")
        dlg.resize(420, 480)
        lay = QVBoxLayout(dlg)

        lst = QListWidget()
        lst.setObjectName("ChatHistoryList")
        lay.addWidget(lst, 1)

        empty = QLabel("No past chats yet. Start talking and they'll "
                       "show up here.")
        empty.setObjectName("ChatHistoryEmpty")
        empty.setWordWrap(True)
        lay.addWidget(empty)

        row = QHBoxLayout()
        open_btn = QPushButton("Open")
        del_btn = QPushButton("Delete")
        close_btn = QPushButton("Close")
        row.addWidget(open_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        lay.addLayout(row)

        def refill():
            lst.clear()
            ordered = sorted(
                self._sessions,
                key=lambda s: s.get("updated", ""),
                reverse=True,
            )
            for s in ordered:
                if not s["messages"]:
                    continue
                day, _, hm = s.get("updated", "").partition(" ")
                when = f"{self._date_label(day)} {hm}".strip()
                n = len(s["messages"])
                current = "  (current)" if s is self._current else ""
                item = QListWidgetItem(
                    f"{s['title'] or '(untitled)'}\n"
                    f"{when} - {n} messages{current}"
                )
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                lst.addItem(item)
            if lst.count():
                lst.setCurrentRow(0)
            empty.setVisible(lst.count() == 0)

        def selected_id():
            item = lst.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def do_open():
            sid = selected_id()
            if sid:
                dlg.accept()
                self.open_session(sid)

        def do_delete():
            sid = selected_id()
            if not sid:
                return
            answer = QMessageBox.question(
                dlg, "Delete chat", "Delete this chat permanently?"
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.delete_session(sid)
                refill()

        lst.itemDoubleClicked.connect(lambda _item: do_open())
        open_btn.clicked.connect(lambda: do_open())
        del_btn.clicked.connect(lambda: do_delete())
        close_btn.clicked.connect(dlg.reject)

        refill()
        dlg.exec()

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
        self.scroll.setObjectName("ChatScrollArea")

        self.content = QWidget()
        self.content.setObjectName("ChatTranscript")
        self.chat_layout = QVBoxLayout(self.content)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch(1)   # keeps bubbles pushed to the top
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        # ── Composer ─────────────────────────────────────────────────
        composer = QFrame()
        composer.setObjectName("ChatComposer")
        cl = QHBoxLayout(composer)
        cl.setContentsMargins(8, 4, 6, 4)
        cl.setSpacing(6)

        self.input = QLineEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Message Moxie...")
        self.input.setMinimumWidth(80)
        self.input.returnPressed.connect(self._on_send_clicked)
        cl.addWidget(self.input, 1)

        # ── Four emoji buttons — same size, same style ────────────
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

        self.history_btn = self._make_icon_button(
            HISTORY_GLYPH, "Chat history", BTN_SIZE, font_px=BTN_FONT_PX
        )
        self.history_btn.clicked.connect(lambda: self.show_history())
        cl.addWidget(self.history_btn, 0)

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

        btn.setObjectName("ChatIconButton")
        btn.setStyleSheet(
            f"border-radius: {size // 2}px;"
            f"font-family: 'Segoe UI Emoji', 'Apple Color Emoji', "
            f"'Noto Color Emoji';"
            f"font-size: {font_px}px;"
        )
        return btn

    # ── Saved chats (persistence) ─────────────────────────────────────
    #
    # File format:
    #   {"current": "<id>" | null,
    #    "sessions": [{"id", "title", "created", "updated",
    #                  "messages": [{"role", "content", "date", "time"}]}]}
    #
    def _find_session(self, session_id):
        for s in self._sessions:
            if s["id"] == session_id:
                return s
        return None

    @staticmethod
    def _make_title(text):
        line = " ".join(text.split())
        return line if len(line) <= 40 else line[:37] + "..."

    @staticmethod
    def _make_session(messages):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        first_user = next(
            (m["content"] for m in messages if m["role"] == "user"), ""
        )
        return {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "title": ChatView._make_title(first_user),
            "created": now,
            "updated": now,
            "messages": messages,
        }

    @staticmethod
    def _clean_message(m):
        if (isinstance(m, dict) and
                m.get("role") in ("user", "assistant") and
                isinstance(m.get("content"), str)):
            return {
                "role": m["role"],
                "content": m["content"],
                "date": str(m.get("date", "")),
                "time": str(m.get("time", "")),
            }
        return None

    def _read_store(self):
        """Return (sessions, current_id) from disk."""
        if not self._history_path:
            return [], None
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return [], None

        # Older versions saved one flat list of messages.
        if isinstance(data, list):
            msgs = [m for m in map(self._clean_message, data) if m]
            if not msgs:
                return [], None
            session = self._make_session(msgs)
            return [session], session["id"]

        if not isinstance(data, dict):
            return [], None

        sessions = []
        for raw in data.get("sessions", []):
            if not isinstance(raw, dict):
                continue
            msgs = [m for m in map(self._clean_message,
                                   raw.get("messages", [])) if m]
            if not msgs:
                continue
            fallback = self._make_session(msgs)
            sessions.append({
                "id": str(raw.get("id") or fallback["id"]),
                "title": str(raw.get("title") or fallback["title"]),
                "created": str(raw.get("created") or fallback["created"]),
                "updated": str(raw.get("updated") or fallback["updated"]),
                "messages": msgs,
            })
        return sessions, data.get("current")

    def _write_store(self):
        if not self._history_path:
            return
        payload = {
            "current": self._current["id"] if self._current else None,
            "sessions": [s for s in self._sessions if s["messages"]],
        }
        try:
            path = Path(self._history_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"[chat] saved {len(payload['sessions'])} chat(s) to {path}")
        except OSError as e:
            print(f"[chat] Could not save history: {e}")

    def _log_message(self, role, content):
        """Add a message to the current chat and write it to disk."""
        now = datetime.now()
        if self._current is None:
            self._current = self._make_session([])
            self._sessions.append(self._current)

        s = self._current
        s["messages"].append({
            "role": role,
            "content": content,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
        })
        s["messages"] = s["messages"][-MAX_MESSAGES_PER_CHAT:]
        s["updated"] = now.strftime("%Y-%m-%d %H:%M")
        if role == "user" and not s["title"]:
            s["title"] = self._make_title(content)

        # Keep the list from growing forever (never drop the active chat).
        if len(self._sessions) > MAX_SAVED_CHATS:
            others = sorted(
                (x for x in self._sessions if x is not s),
                key=lambda x: x.get("updated", ""),
            )
            drop = others[:len(self._sessions) - MAX_SAVED_CHATS]
            self._sessions = [x for x in self._sessions if x not in drop]

        self._write_store()

    def _restore(self):
        """On startup: reopen the chat you were last in."""
        self._sessions, current_id = self._read_store()
        print(f"[chat] history file: {self._history_path} "
              f"-> {len(self._sessions)} saved chat(s)")
        self._current = self._find_session(current_id)
        self._render_session(self._current)

    def _render_session(self, session):
        """Show a saved chat (or the greeting if session is None)."""
        self._clear_transcript()
        self._current = session
        msgs = session["messages"] if session else []

        if not msgs:
            self.history = []
            self._show_greeting()
            return

        last_date = None
        for m in msgs:
            d = m.get("date", "")
            if d and d != last_date:
                self._append_date_separator(self._date_label(d))
                last_date = d
                self._last_who = None   # new day starts a fresh group
            self._append_bubble(
                m["content"], who=m["role"], timestamp=m.get("time") or None
            )

        self.history = [
            {"role": m["role"], "content": m["content"]} for m in msgs
        ]
        self._trim_history()

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
                avatar.setObjectName("ChatAvatar")
                avatar.setFixedSize(28, 28)
                avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        bubble = QLabel(text)
        role = "User" if is_user else "Assistant"
        group = "Grouped" if grouped else "First"
        bubble.setObjectName(f"Chat{role}Bubble{group}")
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bubble.setMaximumWidth(440)
        bubble.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        col.addWidget(bubble)

        if not grouped:
            ts = QLabel(timestamp or datetime.now().strftime("%H:%M"))
            ts.setObjectName("ChatTimestamp")
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

    def _append_date_separator(self, label="Today"):
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(8)

        left = QFrame()
        left.setObjectName("ChatDateRule")
        left.setFrameShape(QFrame.Shape.HLine)
        left.setFixedHeight(1)

        lbl = QLabel(label)
        lbl.setObjectName("ChatDateLabel")

        right = QFrame()
        right.setObjectName("ChatDateRule")
        right.setFrameShape(QFrame.Shape.HLine)
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
        avatar.setObjectName("ChatAvatar")
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        dots = QLabel(".  .  .")
        dots.setObjectName("ChatTypingBubble")
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
