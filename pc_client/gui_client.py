"""GUI Client for AI Workspace Enterprise."""

# pylint: disable=no-name-in-module

import asyncio
import base64
import html
import json
import os
import random
import ssl
import sys
import urllib.request
import uuid
from pathlib import Path

import markdown
import websockets
from dotenv import load_dotenv
from PySide6.QtCore import QBuffer, QIODevice, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QTextBrowser, QTextEdit, QVBoxLayout,
    QWidget
)

from cipher_utils import decrypt_message, encrypt_message

# ==========================================
# گارد امنیتی ضد پروکسی
# ==========================================
_PROXY_VARS = [
    "http_proxy", "https_proxy", "all_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"
]
for _env_var in _PROXY_VARS:
    os.environ.pop(_env_var, None)


def _empty_proxies() -> dict:
    """Return an empty dictionary to bypass system proxies safely."""
    return {}


urllib.request.getproxies = _empty_proxies

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

current_dir = Path(__file__).parent
env_path = current_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

CLIENT_ID = f"gui_{uuid.uuid4().hex[:8]}"

raw_url = os.getenv("BRIDGE_WS_URL", "ws://127.0.0.1:8000").strip().rstrip("/")
if raw_url.startswith("http://"):
    raw_url = raw_url.replace("http://", "ws://", 1)
elif raw_url.startswith("https://"):
    raw_url = raw_url.replace("https://", "wss://", 1)

if raw_url.endswith("/ws/pc") or raw_url.endswith("/ws"):
    _parsed = raw_url.rsplit("/ws", 1)[0]
else:
    _parsed = raw_url

SERVER_URI = f"{_parsed}/ws/client/{CLIENT_ID}"

# ==========================================
# استایل‌ها و تم‌های مدرن حرفه‌ای
# ==========================================
DARK_STYLESHEET = """
    QMainWindow, QDialog { background-color: #09090b; }
    QTextBrowser { background-color: #09090b; border: none; color: #f4f4f5;
        font-size: 14px; font-family: 'Segoe UI', system-ui, sans-serif; }
    QScrollBar:vertical { border: none; background: #09090b; width: 8px;
        margin: 0; }
    QScrollBar::handle:vertical { background: #3f3f46; min-height: 20px;
        border-radius: 4px; }
    QScrollBar::handle:vertical:hover { background: #52525b; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none; background: none; }
    QTextEdit#ChatInput { background-color: #18181b; color: #f4f4f5;
        padding: 12px; border-radius: 16px; border: 1px solid #27272a;
        font-size: 14px; font-family: 'Segoe UI', system-ui, sans-serif; }
    QTextEdit#ChatInput:focus { border: 1px solid #10b981; }
    QPushButton#SendBtn { background-color: #10b981; color: white;
        border-radius: 16px; padding: 10px; font-weight: bold;
        font-size: 14px; }
    QPushButton#SendBtn:hover { background-color: #059669; }
    QPushButton#SendBtn:disabled { background-color: #27272a; color: #52525b;
        border: 1px solid #27272a; }
    QPushButton#AttachBtn { background-color: transparent; color: #a1a1aa;
        border: 1px solid #27272a; border-radius: 16px; padding: 10px;
        font-weight: bold; font-size: 14px; }
    QPushButton#AttachBtn:hover { background-color: rgba(255,255,255,0.05);
        color: #f4f4f5; }
    QPushButton#AttachBtn[hasImage="true"] { background-color: #10b981;
        color: white; border-color: #10b981; }
    QPushButton#ToolBtn, QPushButton#ActionBtn { background-color: transparent;
        color: #a1a1aa; border: 1px solid #27272a; border-radius: 14px;
        padding: 6px 14px; font-weight: 600; font-size: 12px; }
    QPushButton#ToolBtn:checked { background-color: rgba(16, 185, 129, 0.1);
        color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
    QPushButton#ActionBtn:hover { background-color: rgba(255,255,255,0.05);
        color: #f4f4f5; }
    QComboBox { background-color: #18181b; color: #10b981;
        border: 1px solid #27272a; border-radius: 14px; padding: 4px 12px;
        font-weight: 600; font-size: 12px; min-width: 120px; }
    QComboBox::drop-down { border: none; }
    QFrame#Header { background-color: rgba(24, 24, 27, 0.9);
        border-bottom: 1px solid #27272a; }
    QLabel#ChipGPU { background-color: #16a34a; color: white; border-radius: 6px;
        padding: 3px 8px; font-weight: bold; font-size: 11px;}
    QLabel#ChipCPU { background-color: #2563eb; color: white; border-radius: 6px;
        padding: 3px 8px; font-weight: bold; font-size: 11px;}
"""

LIGHT_STYLESHEET = """
    QMainWindow, QDialog { background-color: #f4f4f5; }
    QTextBrowser { background-color: #f4f4f5; border: none; color: #18181b;
        font-size: 14px; font-family: 'Segoe UI', system-ui, sans-serif; }
    QScrollBar:vertical { border: none; background: #f4f4f5; width: 8px;
        margin: 0; }
    QScrollBar::handle:vertical { background: #d4d4d8; min-height: 20px;
        border-radius: 4px; }
    QScrollBar::handle:vertical:hover { background: #a1a1aa; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none; background: none; }
    QTextEdit#ChatInput { background-color: #ffffff; color: #18181b;
        padding: 12px; border-radius: 16px; border: 1px solid #d4d4d8;
        font-size: 14px; font-family: 'Segoe UI', system-ui, sans-serif; }
    QTextEdit#ChatInput:focus { border: 1px solid #059669; }
    QPushButton#SendBtn { background-color: #059669; color: white;
        border-radius: 16px; padding: 10px; font-weight: bold;
        font-size: 14px; }
    QPushButton#SendBtn:hover { background-color: #047857; }
    QPushButton#SendBtn:disabled { background-color: #e4e4e7; color: #a1a1aa;
        border: 1px solid #d4d4d8; }
    QPushButton#AttachBtn { background-color: #ffffff; color: #52525b;
        border: 1px solid #d4d4d8; border-radius: 16px; padding: 10px;
        font-weight: bold; font-size: 14px; }
    QPushButton#AttachBtn:hover { background-color: #f4f4f5; color: #18181b; }
    QPushButton#AttachBtn[hasImage="true"] { background-color: #059669;
        color: white; border-color: #059669; }
    QPushButton#ToolBtn, QPushButton#ActionBtn { background-color: #ffffff;
        color: #52525b; border: 1px solid #d4d4d8; border-radius: 14px;
        padding: 6px 14px; font-weight: 600; font-size: 12px; }
    QPushButton#ToolBtn:checked { background-color: rgba(5, 150, 105, 0.1);
        color: #059669; border: 1px solid rgba(5, 150, 105, 0.3); }
    QPushButton#ActionBtn:hover { background-color: #f4f4f5; color: #18181b; }
    QComboBox { background-color: #ffffff; color: #059669;
        border: 1px solid #d4d4d8; border-radius: 14px; padding: 4px 12px;
        font-weight: 600; font-size: 12px; min-width: 120px; }
    QComboBox::drop-down { border: none; }
    QFrame#Header { background-color: rgba(255, 255, 255, 0.9);
        border-bottom: 1px solid #d4d4d8; }
    QLabel#ChipGPU { background-color: #16a34a; color: white; border-radius: 6px;
        padding: 3px 8px; font-weight: bold; font-size: 11px;}
    QLabel#ChipCPU { background-color: #2563eb; color: white; border-radius: 6px;
        padding: 3px 8px; font-weight: bold; font-size: 11px;}
"""

DICT = {
    "fa": {
        "title": "فضای کاری هوش مصنوعی",
        "tools": "🛠 ابزارها",
        "placeholder": "پیام خود را بنویسید... (Shift+Enter برای خط جدید)",
        "send": "ارسال",
        "offline": "🔴 آفلاین",
        "online": "🟢 آنلاین",
        "server_off": "سرور: قطع",
        "server_on": "سرور: آماده",
        "you": "شما",
        "ai": "هوش مصنوعی ✦",
        "loading": "در حال اتصال...",
        "err_img": "❌ خطا: فایل انتخاب شده تصویر معتبری نیست.",
        "def_model": "مدل پیش‌فرض",
        "err_conn": "ارتباط قطع است.",
        "clear_chat": "پاک کردن / گفتگوی جدید",
        "about_title": "درباره AI Workspace",
        "about_desc": (
            "<h2 style='color:#10b981;'>AI Workspace Enterprise</h2>"
            "<p>نسخه 17.6 Final<br>تضمین پایداری مطلق، همگام‌سازی "
            "محتوا و ارتباط رمزنگاری شده.</p>"
        ),
        "close": "بستن",
        "processing": "در حال پردازش",
        "dir": "rtl",
        "align_me": "right",
        "align_ai": "left"
    },
    "en": {
        "title": "AI Workspace",
        "tools": "🛠 Tools",
        "placeholder": "Type your message... (Shift+Enter for new line)",
        "send": "Send",
        "offline": "🔴 Offline",
        "online": "🟢 Online",
        "server_off": "Server: Off",
        "server_on": "Server: Ready",
        "you": "You",
        "ai": "AI Assistant ✦",
        "loading": "Connecting...",
        "err_img": "❌ Error: Invalid image file.",
        "def_model": "Default Model",
        "err_conn": "Connection lost.",
        "clear_chat": "Clear Chat / New Chat",
        "about_title": "About AI Workspace",
        "about_desc": (
            "<h2 style='color:#10b981;'>AI Workspace Enterprise</h2>"
            "<p>Version 17.6 Final<br>Absolute stability, context "
            "synchronization, and secure E2E encryption.</p>"
        ),
        "close": "Close",
        "processing": "Processing",
        "dir": "ltr",
        "align_me": "left",
        "align_ai": "right"
    }
}


class ChatInputEdit(QTextEdit):
    """Custom QTextEdit for chat input with auto-resize functionality."""
    returnPressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInput")
        self.setAcceptRichText(False)
        self._max_height = 150
        self._min_height = 45
        self.document().documentLayout().documentSizeChanged.connect(
            self.adjust_height
        )
        self.setMaxHeight(150)
        self.setMinHeight(45)

    def setMaxHeight(self, h):  # pylint: disable=invalid-name
        """Set maximum height for auto-resizing."""
        self._max_height = h

    def setMinHeight(self, h):  # pylint: disable=invalid-name
        """Set minimum height for auto-resizing."""
        self._min_height = h
        self.setMinimumHeight(h)

    def adjust_height(self):
        """Adjust input field height dynamically based on content."""
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        total_height = doc_height + margins.top() + margins.bottom() + 10
        if total_height < self._min_height:
            self.setFixedHeight(self._min_height)
        elif total_height > self._max_height:
            self.setFixedHeight(self._max_height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.setFixedHeight(total_height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        """Handle Shift+Enter for newline and Enter for send."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.returnPressed.emit()
                event.accept()
        else:
            super().keyPressEvent(event)


class BridgeManager(QThread):
    """Background thread to manage WebSocket connection."""
    packet_received = Signal(str, str, dict)
    connection_status = Signal(bool)
    sys_status = Signal(bool, str)
    kill_socket = Signal()

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.ws = None
        self.is_connected = False
        self.running = True
        self.reconnect_attempts = 0
        self.ws_send_lock = asyncio.Lock()
        self.kill_socket.connect(self._force_kill_socket)

    def run(self):
        """Run the main event loop for WebSockets."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.start_ws())

    @Slot()
    def _force_kill_socket(self):
        """Forcefully close the socket safely."""
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)

    async def heartbeat_task(self):
        """Maintain connection via ping/pong."""
        while self.running:
            if self.ws:
                try:
                    async with asyncio.timeout(2.0):
                        async with self.ws_send_lock:
                            await self.ws.send(json.dumps({"type": "ping"}))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            await asyncio.sleep(15)

    async def start_ws(self):
        """Establish WebSocket connection with the Bridge Server."""
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        kwargs = {"ping_interval": None, "max_size": 20_971_520}
        if SERVER_URI.startswith("wss://"):
            kwargs["ssl"] = ssl_ctx

        while self.running:
            try:
                async with websockets.connect(SERVER_URI, **kwargs) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.connection_status.emit(True)

                    hb_task = asyncio.create_task(self.heartbeat_task())
                    try:
                        async for message in ws:
                            if not self.running:
                                break
                            try:
                                data = json.loads(message)
                                if data.get("type") == "ping":
                                    async with self.ws_send_lock:
                                        await ws.send(
                                            json.dumps({"type": "pong"})
                                        )
                                    continue
                                if data.get("type") == "pong":
                                    continue

                                if "payload" in data:
                                    self.reconnect_attempts = 0
                                    dec = json.loads(
                                        decrypt_message(data["payload"])
                                    )
                                    p_type = dec.get("type", "unknown")
                                    p_content = dec.get("content", "")
                                    if p_type == "sys_status":
                                        self.sys_status.emit(
                                            p_content == "online",
                                            dec.get("hw", "CPU")
                                        )
                                    else:
                                        self.packet_received.emit(
                                            p_type, p_content, dec
                                        )
                            except Exception:  # pylint: disable=broad-exception-caught
                                pass
                    finally:
                        hb_task.cancel()

                    self.ws = None
                    self.is_connected = False
                    self.connection_status.emit(False)
            except Exception:  # pylint: disable=broad-exception-caught
                self.ws = None
                self.is_connected = False
                self.connection_status.emit(False)
                if self.running:
                    delay = min(
                        60.0,
                        (2 ** self.reconnect_attempts) + random.random()
                    )
                    await asyncio.sleep(delay)
                    self.reconnect_attempts += 1

    def send_msg(self, payload_dict):
        """Encrypt and send message payload to server."""
        if self.ws and self.is_connected:
            try:
                payload_str = json.dumps(payload_dict)

                async def _send():
                    async with self.ws_send_lock:
                        await self.ws.send(json.dumps({
                            "payload": encrypt_message(payload_str)
                        }))

                asyncio.run_coroutine_threadsafe(_send(), self.loop)
                return True
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return False

    def stop(self):
        """Stop the background worker cleanly."""
        self.running = False
        self.is_connected = False
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        for task in asyncio.all_tasks(self.loop):
            task.cancel()
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:
            pass


class AboutDialog(QDialog):
    """About dialog modal window."""

    def __init__(self, parent=None, lang="fa", theme="dark"):
        super().__init__(parent)
        self.setFixedSize(350, 200)
        layout = QVBoxLayout(self)

        icon = QLabel("✦")
        icon.setStyleSheet("font-size: 32px; color: #10b981;")
        icon.setAlignment(Qt.AlignCenter)

        self.desc = QLabel()
        self.desc.setAlignment(Qt.AlignCenter)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("ActionBtn")
        self.close_btn.clicked.connect(self.accept)

        layout.addWidget(icon)
        layout.addWidget(self.desc)
        layout.addWidget(self.close_btn)
        self.update_texts(lang, theme)

    def update_texts(self, lang, theme):
        """Apply language and theme settings dynamically."""
        self.setWindowTitle(DICT[lang]["about_title"])
        self.desc.setText(DICT[lang]["about_desc"])
        self.close_btn.setText(DICT[lang]["close"])
        if theme == "dark":
            self.setStyleSheet(DARK_STYLESHEET)
        else:
            self.setStyleSheet(LIGHT_STYLESHEET)


class ModernChatWindow(QMainWindow):
    """Main Application Window."""

    def __init__(self, background_bridge):
        super().__init__()
        self.bridge = background_bridge
        self.current_lang = "fa"
        self.current_theme = "dark"

        self.setMinimumSize(900, 850)
        self.current_image_b64 = None

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            "font-weight: 800; font-size: 18px; letter-spacing: -0.5px;"
        )
        self.title_label.setAlignment(Qt.AlignCenter)

        right_panel = QHBoxLayout()
        right_panel.setSpacing(10)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("ActionBtn")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.clicked.connect(self.toggle_theme)

        self.lang_btn = QPushButton("EN")
        self.lang_btn.setObjectName("ActionBtn")
        self.lang_btn.setFixedSize(36, 36)
        self.lang_btn.clicked.connect(self.toggle_lang)

        self.clear_btn = QPushButton("🗑")
        self.clear_btn.setObjectName("ActionBtn")
        self.clear_btn.setFixedSize(36, 36)
        self.clear_btn.clicked.connect(self.clear_chat)

        self.about_btn = QPushButton("ℹ️")
        self.about_btn.setObjectName("ActionBtn")
        self.about_btn.setFixedSize(36, 36)
        self.about_btn.clicked.connect(self.show_about)

        self.tools_btn = QPushButton()
        self.tools_btn.setObjectName("ToolBtn")
        self.tools_btn.setCheckable(True)

        self.model_combo = QComboBox()
        self.model_combo.setEnabled(False)

        self.pc_status_label = QLabel()
        self.pc_status_label.setStyleSheet(
            "font-weight: 600; font-size: 13px;"
        )
        self.hw_chip = QLabel("OFF")
        self.hw_chip.setVisible(False)

        right_panel.addWidget(self.theme_btn)
        right_panel.addWidget(self.lang_btn)
        right_panel.addWidget(self.clear_btn)
        right_panel.addWidget(self.about_btn)
        right_panel.addWidget(self.tools_btn)
        right_panel.addWidget(self.model_combo)
        right_panel.addWidget(self.pc_status_label)
        right_panel.addWidget(self.hw_chip)

        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.title_label, 1)
        header_layout.addLayout(right_panel)
        main_layout.addWidget(header)

        # --- Chat Display ---
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(20, 20, 20, 0)
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        chat_layout.addWidget(self.chat_display)
        main_layout.addWidget(chat_container)

        # --- Input Area ---
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(20, 15, 20, 20)
        input_layout.setSpacing(12)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setObjectName("AttachBtn")
        self.attach_btn.setProperty("hasImage", False)
        self.attach_btn.setFixedSize(46, 46)
        self.attach_btn.clicked.connect(self.attach_image)

        self.input_field = ChatInputEdit()
        self.input_field.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton()
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setFixedSize(85, 46)

        btn_layout_attach = QVBoxLayout()
        btn_layout_attach.addStretch()
        btn_layout_attach.addWidget(self.attach_btn)

        btn_layout_send = QVBoxLayout()
        btn_layout_send.addStretch()
        btn_layout_send.addWidget(self.send_btn)

        input_layout.addLayout(btn_layout_attach)
        input_layout.addWidget(self.input_field)
        input_layout.addLayout(btn_layout_send)
        main_layout.addWidget(input_container)

        self.chat_history = []
        self.is_streaming = False
        self.is_thinking = False
        self.dots = 0

        self.think_timer = QTimer()
        self.think_timer.timeout.connect(self.update_thinking_anim)

        self.watchdog_timer = QTimer()
        self.watchdog_timer.setSingleShot(True)
        self.watchdog_timer.timeout.connect(self.watchdog_timeout)

        self.bridge.packet_received.connect(self.handle_packet)
        self.bridge.connection_status.connect(self.update_status)
        self.bridge.sys_status.connect(self.update_pc_status)

        self.apply_theme()
        self.apply_lang()

    def clear_chat(self):
        """Clear current chat history and sync with server."""
        self.chat_history.clear()
        self.update_ui()
        if self.bridge.is_connected:
            self.bridge.send_msg({"type": "clear_history"})

    def apply_theme(self):
        """Apply dark or light theme dynamically."""
        if self.current_theme == "dark":
            self.setStyleSheet(DARK_STYLESHEET)
            self.theme_btn.setText("🌙")
        else:
            self.setStyleSheet(LIGHT_STYLESHEET)
            self.theme_btn.setText("🌞")
        self.update_ui()

    def toggle_theme(self):
        """Toggle active theme."""
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"
        self.apply_theme()

    def apply_lang(self):
        """Apply active language dictionary."""
        d = DICT[self.current_lang]
        self.setWindowTitle(d["title"])
        self.title_label.setText(f"✦ {d['title']}")
        self.tools_btn.setText(d["tools"])
        self.clear_btn.setToolTip(d["clear_chat"])
        self.input_field.setPlaceholderText(d["placeholder"])
        self.send_btn.setText(d["send"])

        if self.current_lang == "fa":
            self.lang_btn.setText("EN")
        else:
            self.lang_btn.setText("FA")

        if self.model_combo.count() == 0:
            self.model_combo.addItem(d["loading"])

        if self.bridge.is_connected:
            self.status_label.setText(d["online"])
            self.status_label.setStyleSheet("color: #10b981;")
        else:
            self.status_label.setText(d["offline"])
            self.status_label.setStyleSheet("color: #ef4444;")

        if self.hw_chip.isVisible():
            self.pc_status_label.setText(d["server_on"])
        else:
            self.pc_status_label.setText(d["server_off"])

        self.update_ui()

    def toggle_lang(self):
        """Toggle active language (fa/en)."""
        if self.current_lang == "fa":
            self.current_lang = "en"
        else:
            self.current_lang = "fa"
        self.apply_lang()

    def show_about(self):
        """Show About Application dialog."""
        dlg = AboutDialog(self, self.current_lang, self.current_theme)
        dlg.exec()

    def get_html_styles(self):
        """Return raw HTML styles depending on the current theme."""
        if self.current_theme == "dark":
            return """
                body { font-family: 'Segoe UI', system-ui, sans-serif;
                    line-height: 1.6; color: #f4f4f5; }
                pre { background-color: #0d1117; padding: 15px;
                    border-radius: 12px; border: 1px solid #30363d;
                    color: #e6edf3;
                    font-family: 'Consolas', ui-monospace, monospace;
                    font-size: 13.5px; margin: 15px 0; }
                code { background-color: #27272a; color: #60a5fa;
                    padding: 2px 6px; border-radius: 6px;
                    font-family: 'Consolas', monospace; font-size: 13px; }
                table { border-collapse: collapse; width: 100%; margin: 15px 0;}
                th, td { border: 1px solid #3f3f46; padding: 10px;}
                th { background-color: #18181b;}
                a { color: #10b981; text-decoration: none; }
                p { margin-top: 0; margin-bottom: 12px; }
                img { max-width: 100%; border-radius: 8px; }
                .sys-msg { background:#18181b; padding:6px 16px;
                    border-radius:16px; border:1px solid #27272a;
                    font-size:12px; }
                .usr-bubble { background-color:#27272a;
                    border: 1px solid #3f3f46; border-radius:18px;
                    color:#f4f4f5; }
            """

        return """
            body { font-family: 'Segoe UI', system-ui, sans-serif;
                line-height: 1.6; color: #18181b; }
            pre { background-color: #f8fafc; padding: 15px;
                border-radius: 12px; border: 1px solid #e2e8f0;
                color: #1e293b;
                font-family: 'Consolas', ui-monospace, monospace;
                font-size: 13.5px; margin: 15px 0; }
            code { background-color: #e4e4e7; color: #0ea5e9;
                padding: 2px 6px; border-radius: 6px;
                font-family: 'Consolas', monospace; font-size: 13px; }
            table { border-collapse: collapse; width: 100%; margin: 15px 0;}
            th, td { border: 1px solid #d4d4d8; padding: 10px;}
            th { background-color: #f4f4f5;}
            a { color: #059669; text-decoration: none; }
            p { margin-top: 0; margin-bottom: 12px; }
            img { max-width: 100%; border-radius: 8px; }
            .sys-msg { background:#ffffff; padding:6px 16px;
                border-radius:16px; border:1px solid #d4d4d8;
                font-size:12px; }
            .usr-bubble { background-color:#e4e4e7;
                border: 1px solid #d4d4d8; border-radius:18px;
                color:#18181b; }
        """

    def attach_image(self):
        """Prompt user for an image and load it in Base64."""
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Image", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if file_name:
            try:
                img = QImage(file_name)
                if img.isNull():
                    err_msg = DICT[self.current_lang]["err_img"]
                    self.chat_history.append({
                        "role": "sys",
                        "content": err_msg
                    })
                    self.update_ui()
                    return
                max_dim = 1024
                if img.width() > max_dim or img.height() > max_dim:
                    img = img.scaled(
                        max_dim, max_dim,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )

                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                img.save(buffer, "JPEG", 80)
                img_data = buffer.data().data()

                enc_img = base64.b64encode(img_data).decode('utf-8')
                self.current_image_b64 = f"data:image/jpeg;base64,{enc_img}"

                self.attach_btn.setProperty("hasImage", True)
                self.attach_btn.style().unpolish(self.attach_btn)
                self.attach_btn.style().polish(self.attach_btn)
                self.send_btn.setDisabled(False)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.chat_history.append({
                    "role": "sys",
                    "content": f"Image Error: {e}"
                })
                self.update_ui()

    def reset_watchdog(self):
        """Reset communication watchdog timer."""
        if self.is_streaming or self.is_thinking:
            self.watchdog_timer.start(60000)
        else:
            self.watchdog_timer.stop()

    def watchdog_timeout(self):
        """Force quit on response timeout."""
        self.handle_packet("error", "Timeout.", {})
        self.bridge.kill_socket.emit()

    def update_thinking_anim(self):
        """Update loading indicator animations."""
        self.dots = (self.dots + 1) % 4
        self.update_ui()

    def _render_markdown_safe(self, text):
        """Escape HTML correctly and parse markdown."""
        safe_text = html.escape(text).replace("&gt;", ">")
        safe_text = safe_text.replace("&lt;br&gt;", "<br>")
        return markdown.markdown(
            safe_text, extensions=['fenced_code', 'tables', 'nl2br']
        )

    def update_ui(self):
        """Render all messages from history cleanly to QTextBrowser."""
        self.chat_display.document().setDefaultStyleSheet(
            self.get_html_styles()
        )
        d = DICT[self.current_lang]
        dr = d["dir"]
        al_me = d["align_me"]
        al_ai = d["align_ai"]

        full_html = f"<div dir='{dr}'>"
        for i, msg in enumerate(self.chat_history):
            sender = msg["role"]
            is_last = (i == len(self.chat_history) - 1)

            if sender == "sys":
                color = "#3b82f6" if "🛠" in msg['content'] else (
                    "#a1a1aa" if self.current_theme == "dark" else "#52525b"
                )
                full_html += (
                    f"<div style='text-align:center; margin:15px 0;'>"
                    f"<span class='sys-msg' style='color:{color};'>"
                    f"{msg['content']}</span></div>"
                )
                continue

            if sender == "user":
                content = self._render_markdown_safe(msg["content"])
                img_html = ""
                if msg.get("image"):
                    img_html = (
                        f"<img src='{msg.get('image')}' "
                        f"style='max-width:300px; max-height:300px; "
                        f"display:block; margin-bottom:10px;'/><br>"
                    )
                br_radius = (
                    "border-top-right-radius:4px;"
                    if dr == "rtl" else "border-top-left-radius:4px;"
                )
                full_html += (
                    f"<div style='text-align:{al_me}; margin-bottom: 24px;'>"
                    f"<span style='color:#a1a1aa; font-size:12px; "
                    f"font-weight:bold; margin-bottom:5px; display:block;'>"
                    f"{d['you']}</span><div class='usr-bubble' "
                    f"style='display:inline-block; padding:14px 18px; "
                    f"{br_radius} text-align:{al_me}; max-width:85%;'>"
                    f"{img_html}{content}</div></div>"
                )
            elif sender == "ai":
                if is_last and self.is_thinking:
                    dots = "." * self.dots
                    content_html = (
                        f"<span style='color:#10b981;'>"
                        f"{d['processing']}{dots}</span>"
                    )
                elif is_last and self.is_streaming:
                    escaped_content = html.escape(msg["content"])
                    content_html = escaped_content.replace('\n', '<br>')
                else:
                    content_html = self._render_markdown_safe(msg["content"])

                full_html += (
                    f"<div style='text-align:{al_ai}; margin-bottom: 24px;'>"
                    f"<span style='color:#10b981; font-size:12px; "
                    f"font-weight:bold; margin-bottom:5px; display:block;'>"
                    f"{d['ai']}</span><div style='display:block; width:100%;'>"
                    f"{content_html}</div></div>"
                )

        full_html += "</div>"
        scrollbar = self.chat_display.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 50
        self.chat_display.setHtml(full_html)
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    @Slot(str, str, dict)
    def handle_packet(self, msg_type, content, full_packet):
        """Handle incoming instructions from WebSocket worker."""
        if msg_type == "models_list":
            self.model_combo.clear()
            models = full_packet.get("models", [])
            if models:
                for m in models:
                    self.model_combo.addItem(m["id"].split('/')[-1], m["id"])
                self.model_combo.setEnabled(True)
            else:
                self.model_combo.addItem(DICT[self.current_lang]["def_model"])
                self.model_combo.setEnabled(True)

        elif msg_type == "tool_event":
            self.chat_history.append({
                "role": "sys",
                "content": f"🛠 {content}"
            })
            self.update_ui()
            self.reset_watchdog()

        elif msg_type == "status" and content == "thinking":
            self.is_thinking = True
            self.think_timer.start(500)
            self.chat_history.append({"role": "ai", "content": ""})
            self.update_ui()
            self.reset_watchdog()

        elif msg_type == "chunk":
            if not content:
                return
            if self.is_thinking:
                self.is_thinking = False
                self.think_timer.stop()

            if not self.is_streaming:
                self.is_streaming = True
                if self.chat_history[-1]["role"] == "ai":
                    self.chat_history[-1]["content"] = content
                else:
                    self.chat_history.append(
                        {"role": "ai", "content": content}
                    )
            else:
                self.chat_history[-1]["content"] += content

            QTimer.singleShot(0, self.update_ui)
            self.reset_watchdog()

        elif msg_type in ("done", "full"):
            self.is_streaming = False
            self.is_thinking = False
            self.think_timer.stop()
            self.watchdog_timer.stop()

            if msg_type == "full":
                if (
                    self.chat_history and
                    self.chat_history[-1]["role"] == "ai" and
                    self.chat_history[-1]["content"] == ""
                ):
                    self.chat_history[-1]["content"] = content
                else:
                    self.chat_history.append(
                        {"role": "ai", "content": content}
                    )

            self.unlock_inputs()
            self.update_ui()

        elif msg_type == "queue":
            if (
                self.chat_history and
                self.chat_history[-1]["content"] == content
            ):
                return
            self.chat_history.append({"role": "sys", "content": content})
            self.update_ui()

        elif msg_type == "error":
            self.is_streaming = False
            self.is_thinking = False
            self.think_timer.stop()
            self.watchdog_timer.stop()

            err_msg = f"❌ {content}"
            if (
                self.chat_history and
                self.chat_history[-1]["role"] == "ai" and
                self.chat_history[-1]["content"] == ""
            ):
                self.chat_history.pop()

            if (
                self.chat_history and
                self.chat_history[-1]["content"] == err_msg
            ):
                self.unlock_inputs()
                return

            self.chat_history.append({"role": "sys", "content": err_msg})
            self.unlock_inputs()
            self.update_ui()

    @Slot(bool)
    def update_status(self, connected):
        """Update UI status depending on connection to bridge."""
        d = DICT[self.current_lang]
        if connected:
            self.status_label.setText(d["online"])
            self.status_label.setStyleSheet("color: #10b981;")
            self.bridge.send_msg({"type": "get_models"})
        else:
            self.status_label.setText(d["offline"])
            self.status_label.setStyleSheet("color: #ef4444;")
            self.pc_status_label.setText(d["server_off"])
            self.hw_chip.setVisible(False)
            self.model_combo.setEnabled(False)

    @Slot(bool, str)
    def update_pc_status(self, is_online, hw_mode):
        """Update PC hardware status."""
        d = DICT[self.current_lang]
        if is_online:
            self.pc_status_label.setText(d["server_on"])
            self.hw_chip.setVisible(True)
            self.hw_chip.setText(hw_mode)
            self.hw_chip.setObjectName(
                "ChipGPU" if hw_mode == "GPU" else "ChipCPU"
            )
            self.hw_chip.style().unpolish(self.hw_chip)
            self.hw_chip.style().polish(self.hw_chip)
            self.bridge.send_msg({"type": "get_models"})
        else:
            self.pc_status_label.setText(d["server_off"])
            self.hw_chip.setVisible(False)
            self.model_combo.setEnabled(False)

    def lock_inputs(self):
        """Lock input interface."""
        self.input_field.setDisabled(True)
        self.send_btn.setDisabled(True)
        self.model_combo.setDisabled(True)
        self.tools_btn.setDisabled(True)
        self.attach_btn.setDisabled(True)

    def unlock_inputs(self):
        """Unlock input interface."""
        self.input_field.setDisabled(False)
        self.send_btn.setDisabled(False)
        self.model_combo.setDisabled(False)
        self.tools_btn.setDisabled(False)
        self.attach_btn.setDisabled(False)
        self.input_field.setFocus()

    def send_message(self):
        """Send message payload using background thread."""
        text = self.input_field.toPlainText().strip()
        img_to_pass = self.current_image_b64

        if text or img_to_pass:
            current_data = self.model_combo.currentData()
            current_text = self.model_combo.currentText()
            selected_model = current_data if current_data else current_text

            # Prepare history for context sync
            sync_history = []
            for msg in self.chat_history:
                if msg["role"] in ["user", "ai"]:
                    sync_history.append({
                        "role": msg["role"],
                        "content": msg["content"],
                        "image": msg.get("image")
                    })

            payload = {
                "type": "chat",
                "text": text,
                "model": selected_model,
                "use_tools": self.tools_btn.isChecked(),
                "image": img_to_pass,
                "history": sync_history
            }

            if self.bridge.send_msg(payload):
                self.chat_history.append({
                    "role": "user",
                    "content": text,
                    "image": img_to_pass
                })

                self.current_image_b64 = None
                self.attach_btn.setProperty("hasImage", False)
                self.attach_btn.style().unpolish(self.attach_btn)
                self.attach_btn.style().polish(self.attach_btn)

                self.lock_inputs()
                self.update_ui()
                self.input_field.clear()
            else:
                err_msg = DICT[self.current_lang]["err_conn"]
                if not (
                    self.chat_history and
                    self.chat_history[-1]["content"] == err_msg
                ):
                    self.chat_history.append({
                        "role": "sys",
                        "content": err_msg
                    })
                self.update_ui()

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """Execute on application termination securely."""
        self.bridge.stop()
        self.bridge.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    bridge_thread = BridgeManager()
    bridge_thread.start()
    window = ModernChatWindow(bridge_thread)
    window.show()
    sys.exit(app.exec())