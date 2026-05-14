
#websockets



import sys, json, asyncio, threading, markdown, os , ssl

from PySide6.QtWidgets import *

from PySide6.QtCore import *

from cryptography.fernet import Fernet

import websockets



# تنظیمات

KEY = b'12345678901234567890123456789012'

CIPHER = Fernet(KEY)

SERVER_URI = "wss://lmstudio.chbk.dev/ws/mobile"

HISTORY_FILE = "chat_history.json"



# --- مدیریت تاریخچه ---

class HistoryManager:

    @staticmethod

    def load():

        if os.path.exists(HISTORY_FILE):

            with open(HISTORY_FILE, "r", encoding="utf-8") as f:

                return json.load(f)

        return []



    @staticmethod

    def save(history):

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:

            json.dump(history, f, ensure_ascii=False, indent=4)



# --- استایل حرفه‌ای Dark Mode ---

DARK_STYLESHEET = """

    QMainWindow { background-color: #1e1e1e; }

    QTextEdit { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 10px; padding: 15px; color: #e1e1e1; font-size: 14px; }

    QLineEdit { background-color: #3c3c3c; color: white; padding: 12px; border-radius: 10px; border: none; }

    QPushButton { background-color: #0e639c; color: white; border-radius: 10px; padding: 10px 20px; font-weight: bold; }

    QPushButton:hover { background-color: #1177bb; }

    QLabel { color: #aaaaaa; font-weight: bold; }

"""




class BridgeManager(QThread):

    message_received = Signal(str)

    

    def __init__(self):

        super().__init__()

        self.loop = asyncio.new_event_loop()

        self.ws = None



    def run(self):

        asyncio.set_event_loop(self.loop)

        self.loop.run_until_complete(self.start_ws())



    async def start_ws(self):

        # تنظیم SSL برای دور زدن محدودیت‌های ویندوز

        ssl_context = ssl.create_default_context()

        ssl_context.check_hostname = False

        ssl_context.verify_mode = ssl.CERT_NONE



        while True:

            try:

                # استفاده از ssl_context و تنظیمات پایدار ping

                async with websockets.connect(

                    SERVER_URI, 

                    ping_interval=5, 

                    ping_timeout=10, 

                    ssl=ssl_context

                ) as ws:

                    self.ws = ws

                    async for message in ws:

                        data = json.loads(message)

                        if "payload" in data:

                            decrypted = CIPHER.decrypt(data["payload"].encode()).decode()

                            self.message_received.emit(decrypted)

                    self.ws = None

            except Exception as e:

                self.ws = None

                await asyncio.sleep(5)



    def send_msg(self, text):

        # بررسی وجود سوکت بدون چک کردن ویژگی‌های متغیر (حذف ws.open)

        if self.ws is not None:

            try:

                encrypted = CIPHER.encrypt(text.encode()).decode()

                # استفاده از run_coroutine_threadsafe بدون نیاز به future.result() 

                # (این متد در ترد اصلی GUI بلوکه نمی‌شود)

                asyncio.run_coroutine_threadsafe(

                    self.ws.send(json.dumps({"payload": encrypted})), 

                    self.loop

                )

            except Exception as e:

                print(f"Send Error: {e}")





class ModernChatWindow(QMainWindow):

    def __init__(self, bridge):

        super().__init__()

        self.bridge = bridge

        self.history = HistoryManager.load()

        self.setWindowTitle("AI Bridge | Dark Mode Professional")

        self.setMinimumSize(500, 700)

        self.setStyleSheet(DARK_STYLESHEET)



        container = QWidget(); layout = QVBoxLayout(container); self.setCentralWidget(container)

        self.chat_display = QTextEdit(); self.chat_display.setReadOnly(True)

        layout.addWidget(QLabel("AI Bridge - Terminal & GUI Integrated")); layout.addWidget(self.chat_display)



        input_layout = QHBoxLayout()

        self.input_field = QLineEdit(); self.send_btn = QPushButton("ارسال")

        input_layout.addWidget(self.input_field); input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)



        self.send_btn.clicked.connect(self.send_message)

        self.bridge.message_received.connect(self.display_ai)

        

        # بارگذاری هیستوری با ایمنی کامل در برابر KeyError

        for item in self.history:

            sender = item.get('sender', 'Unknown')

            text = item.get('text') or item.get('message', '')

            self._render_msg(sender, text, save=False)



    def _render_msg(self, sender, text, save=True):

        html_content = markdown.markdown(text, extensions=['fenced_code', 'tables'])

        if sender == "شما":

            self.chat_display.append(f"<div style='margin-bottom:10px; text-align:right;'><b style='color:#569cd6;'>شما:</b><br><span style='color:white; background:#2d2d2d; padding:5px 10px; border-radius:5px;'>{text}</span></div>")

        else:

            self.chat_display.append(f"<div style='margin-bottom:10px; text-align:left;'><b style='color:#4ec9b0;'>AI:</b><br><div style='color:white; background:#333333; padding:10px; border-radius:5px;'>{html_content}</div></div>")

        

        if save:

            self.history.append({"sender": sender, "text": text})

            HistoryManager.save(self.history)



    def send_message(self):

        text = self.input_field.text()

        if text:

            self._render_msg("شما", text)

            self.bridge.send_msg(text)

            self.input_field.clear()



    @Slot(str)

    def display_ai(self, text):

        self._render_msg("AI", text)



class Color:

    PURPLE = '\033[95m'; CYAN = '\033[96m'; GREEN = '\033[92m'; BOLD = '\033[1m'; END = '\033[0m'



if __name__ == "__main__":

    app = QApplication(sys.argv)

    bridge = BridgeManager()

    bridge.start()

    window = ModernChatWindow(bridge)

    window.show()



    def cli_worker():

        while True:

            text = input(f"\n{Color.CYAN}You > {Color.END}")

            if text: 

                bridge.send_msg(text)

                print(f"\n{Color.PURPLE}{Color.BOLD}You > {Color.END}{text}")

            

    threading.Thread(target=cli_worker, daemon=True).start()

    sys.exit(app.exec())






