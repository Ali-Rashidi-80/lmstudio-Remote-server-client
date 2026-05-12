import sys
import json
import asyncio
import threading
import markdown
import os
import ssl
import base64
from pathlib import Path

# رفع مشکل تاری در ویندوزهای قدیمی (High DPI Scaling) - باید قبل از ایمپورت‌های QGuiApplication باشد
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, 
                               QLabel, QTabWidget, QFrame)
from PySide6.QtCore import Qt, Signal, QThread, Slot
from PySide6.QtGui import QFont, QIcon, QDropEvent, QDragEnterEvent

import websockets
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# --- تنظیمات پایه ---
KEY = b'12345678901234567890123456789012' # کلید 32 بایتی استاندارد پروژه
SERVER_URI = "wss://lmstudio.chbk.dev/ws/mobile"
HISTORY_FILE = "chat_history.json"

# --- توابع رمزنگاری هماهنگ با کل پروژه (AES-ECB) ---
def encrypt_message(text: str) -> str:
    cipher = AES.new(KEY, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(text.encode('utf-8'), 16))).decode('utf-8')

def decrypt_message(enc_text: str) -> str:
    cipher = AES.new(KEY, AES.MODE_ECB)
    return unpad(cipher.decrypt(base64.b64decode(enc_text)), 16).decode('utf-8')

# --- مدیریت تاریخچه ---
class HistoryManager:
    @staticmethod
    def load():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    @staticmethod
    def save(history):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

# --- استایل حرفه‌ای Dark Mode ---
DARK_STYLESHEET = """
    QMainWindow { 
        background-color: #1e1e1e; 
    }
    QTabWidget::pane { 
        border: 1px solid #333333; 
        background: #1e1e1e; 
        border-radius: 8px; 
    }
    QTabBar::tab { 
        background: #252526; 
        color: #aaaaaa; 
        padding: 10px 20px; 
        border-top-left-radius: 8px; 
        border-top-right-radius: 8px; 
        margin-right: 2px;
        font-weight: bold;
    }
    QTabBar::tab:selected { 
        background: #1e1e1e; 
        color: #ffffff; 
        border-bottom: 2px solid #007acc; 
    }
    QTabBar::tab:hover { 
        background: #2d2d2d; 
    }
    QTextBrowser { 
        background-color: #1e1e1e; 
        border: none; 
        color: #d4d4d4; 
        font-size: 14px; 
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    QLineEdit { 
        background-color: #2d2d2d; 
        color: #ffffff; 
        padding: 14px; 
        border-radius: 8px; 
        border: 1px solid #3c3c3c; 
        font-size: 14px;
    }
    QLineEdit:focus {
        border: 1px solid #007acc;
    }
    QPushButton { 
        background-color: #007acc; 
        color: white; 
        border-radius: 8px; 
        padding: 10px 24px; 
        font-weight: bold; 
        font-size: 14px;
    }
    QPushButton:hover { 
        background-color: #0098ff; 
    }
    QPushButton:pressed {
        background-color: #005f9e;
    }
    /* اسکرول بار حرفه ای */
    QScrollBar:vertical {
        border: none;
        background: #1e1e1e;
        width: 10px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:vertical {
        background: #424242;
        min-height: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #4f4f4f;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }
"""

# --- مدیریت ارتباطات WebSockets ---
class BridgeManager(QThread):
    message_received = Signal(str)
    connection_status = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.ws = None
        self.is_connected = False

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.start_ws())

    async def start_ws(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        while True:
            try:
                async with websockets.connect(
                    SERVER_URI, 
                    ping_interval=10, 
                    ping_timeout=20, 
                    ssl=ssl_context
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.connection_status.emit(True)
                    
                    async for message in ws:
                        data = json.loads(message)
                        if "payload" in data:
                            try:
                                decrypted = decrypt_message(data["payload"])
                                self.message_received.emit(decrypted)
                            except Exception as e:
                                print(f"Decryption Error: {e}")
                                
                    self.ws = None
                    self.is_connected = False
                    self.connection_status.emit(False)
            except Exception as e:
                self.ws = None
                self.is_connected = False
                self.connection_status.emit(False)
                await asyncio.sleep(5) # تلاش مجدد

    def send_msg(self, text):
        if self.ws is not None and self.is_connected:
            try:
                encrypted = encrypt_message(text)
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({"payload": encrypted})), 
                    self.loop
                )
                return True
            except Exception as e:
                print(f"Send Error: {e}")
                return False
        return False

# --- ویجت چت با قابلیت Drag & Drop فایل ---
class DroppableChatBrowser(QTextBrowser):
    file_dropped = Signal(str, str) # Signals: content, extension

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setOpenExternalLinks(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            path_obj = Path(file_path)
            
            if path_obj.is_file():
                try:
                    # تلاش برای خواندن فایل متنی
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    ext = path_obj.suffix.lower().replace('.', '')
                    # اگر پسوند نداشت، فرض را بر txt میگذاریم
                    if not ext: ext = 'txt'
                    self.file_dropped.emit(content, ext)
                except Exception as e:
                    # نادیده گرفتن فایل‌های باینری
                    print(f"Cannot read file: {e}")

# --- پنجره اصلی برنامه ---
class ModernChatWindow(QMainWindow):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.history = HistoryManager.load()
        
        self.setWindowTitle("AI Bridge | Professional Client")
        self.setMinimumSize(600, 750)
        self.setStyleSheet(DARK_STYLESHEET)

        # ساختار اصلی
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # ایجاد تب‌ها
        self.tabs = QTabWidget()
        self.chat_tab = QWidget()
        self.about_tab = QWidget()
        
        self.tabs.addTab(self.chat_tab, "💬 محیط گفتگو")
        self.tabs.addTab(self.about_tab, "ℹ️ درباره سیستم")
        self.main_layout.addWidget(self.tabs)

        self.setup_chat_tab()
        self.setup_about_tab()

        # اتصال سیگنال‌ها
        self.bridge.message_received.connect(self.display_ai)
        self.bridge.connection_status.connect(self.update_status)
        
        # بارگذاری تاریخچه
        self.load_history_to_ui()

    def setup_chat_tab(self):
        layout = QVBoxLayout(self.chat_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # وضعیت اتصال
        self.status_label = QLabel("🔴 در حال اتصال به سرور...")
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(self.status_label)

        # صفحه نمایش چت (پشتیبانی از Drag & Drop)
        self.chat_display = DroppableChatBrowser()
        self.chat_display.file_dropped.connect(self.handle_file_drop)
        layout.addWidget(self.chat_display)

        # ناحیه ورودی
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("پیام خود را بنویسید... (یا یک فایل را روی چت رها کنید)")
        self.input_field.returnPressed.connect(self.send_message) # ارسال با دکمه Enter
        
        self.send_btn = QPushButton("ارسال")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def setup_about_tab(self):
        layout = QVBoxLayout(self.about_tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("AI Bridge Client")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #007acc; margin-bottom: 10px;")
        
        subtitle = QLabel("پلتفرم یکپارچه هوش مصنوعی")
        subtitle.setStyleSheet("font-size: 16px; color: #aaaaaa; margin-bottom: 30px;")

        description = QLabel(
            "این نرم‌افزار به عنوان یک پل ارتباطی امن (رمزنگاری شده با AES-256) "
            "بین دستگاه شما و سرور محلی LMStudio عمل می‌کند.<br><br>"
            "<b>ویژگی‌های کلیدی:</b><br>"
            "<ul>"
            "<li>رمزنگاری End-to-End اختصاصی</li>"
            "<li>ارتباط بی‌درنگ از طریق WebSockets</li>"
            "<li>پشتیبانی از فرمت‌های Markdown و کدهای برنامه‌نویسی</li>"
            "<li>قابلیت Drag & Drop برای تشخیص و ارسال کدهای منبع</li>"
            "</ul>"
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #d4d4d4; line-height: 1.6;")

        tech_stack = QLabel(
            "<br><b>تکنولوژی‌ها:</b><br>"
            "Python 3, PySide6 (Qt), WebSockets, Cryptography (AES-ECB)"
        )
        tech_stack.setStyleSheet("font-size: 13px; color: #4ec9b0;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(description)
        layout.addWidget(tech_stack)
        layout.addStretch()

        version = QLabel("نسخه 2.0.0 | توسعه یافته با ❤️")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #666666;")
        layout.addWidget(version)

    @Slot(str, str)
    def handle_file_drop(self, content, ext):
        """زمانی که فایلی رها می‌شود، آن را فرمت کرده و در باکس ورودی قرار می‌دهد"""
        formatted_code = f"بررسی این فایل:\n\n```{ext}\n{content}\n```"
        self.input_field.setText(formatted_code)
        self.input_field.setFocus()

    @Slot(bool)
    def update_status(self, connected):
        if connected:
            self.status_label.setText("🟢 متصل به سرور امن")
            self.status_label.setStyleSheet("color: #4ec9b0; font-weight: bold; margin-bottom: 5px;")
        else:
            self.status_label.setText("🔴 در حال اتصال به سرور...")
            self.status_label.setStyleSheet("color: #ff5252; font-weight: bold; margin-bottom: 5px;")

    def load_history_to_ui(self):
        for item in self.history:
            sender = item.get('sender', 'Unknown')
            text = item.get('text') or item.get('message', '')
            self._render_msg(sender, text, save=False)

    def _render_msg(self, sender, text, save=True):
        # تبدیل Markdown به HTML با پشتیبانی کامل از کد و جدول
        html_content = markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br'])
        
        # استایل‌های مدرن برای پیام‌ها
        if sender == "شما":
            msg_html = (
                f"<div style='margin-top:15px; text-align:right; font-family: Tahoma;'>"
                f"<span style='color:#569cd6; font-weight:bold; font-size:12px;'>شما</span><br>"
                f"<div style='display:inline-block; background-color:#264f78; color:white; "
                f"padding:10px 15px; border-radius:12px; margin-top:5px; text-align:right;'>"
                f"{html_content}</div></div>"
            )
        else:
            msg_html = (
                f"<div style='margin-top:15px; text-align:left; font-family: Tahoma; direction: ltr;'>"
                f"<span style='color:#4ec9b0; font-weight:bold; font-size:12px;'>هوش مصنوعی</span><br>"
                f"<div style='display:inline-block; background-color:#333333; color:#d4d4d4; "
                f"padding:10px 15px; border-radius:12px; margin-top:5px; border: 1px solid #444;'>"
                f"{html_content}</div></div>"
            )
        
        self.chat_display.append(msg_html)
        
        # اسکرول خودکار به پایین
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        if save:
            self.history.append({"sender": sender, "text": text})
            HistoryManager.save(self.history)

    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            success = self.bridge.send_msg(text)
            if success:
                self._render_msg("شما", text)
                self.input_field.clear()
            else:
                self._render_msg("سیستم", "⚠️ خطا در ارسال پیام. بررسی کنید آیا به سرور متصل هستید؟", save=False)

    @Slot(str)
    def display_ai(self, text):
        self._render_msg("AI", text)

# ابزار رنگی برای ترمینال
class Color:
    PURPLE = '\033[95m'; CYAN = '\033[96m'; GREEN = '\033[92m'; BOLD = '\033[1m'; END = '\033[0m'

if __name__ == "__main__":
    # فعال سازی High DPI Policy برای PySide6
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # تم فیوژن برای ظاهری مدرن در ویندوزهای قدیمی
    
    bridge = BridgeManager()
    bridge.start()
    
    window = ModernChatWindow(bridge)
    window.show()

    # Worker کامند لاین (اختیاری - در صورت نیاز به ترمینال)
    def cli_worker():
        while True:
            try:
                text = input(f"\n{Color.CYAN}You > {Color.END}")
                if text: 
                    bridge.send_msg(text)
                    print(f"\n{Color.PURPLE}{Color.BOLD}Sent.{Color.END}")
            except EOFError:
                break
            
    threading.Thread(target=cli_worker, daemon=True).start()
    
    sys.exit(app.exec())