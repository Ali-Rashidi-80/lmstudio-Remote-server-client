import sys
import json
import asyncio
import markdown
import html
import os
import ssl
import uuid
import random
from dotenv import load_dotenv
import websockets
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, 
                               QLabel, QFrame)
from PySide6.QtCore import Qt, Signal, QThread, Slot, QTimer
from cipher_utils import encrypt_message, decrypt_message

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

load_dotenv()
CLIENT_ID = f"gui_{uuid.uuid4().hex[:8]}"
BASE_WS_URL = os.getenv("BRIDGE_WS_URL", "ws://127.0.0.1:8000/ws")
SERVER_URI = f"{BASE_WS_URL}/client/{CLIENT_ID}"

DARK_STYLESHEET = """
    QMainWindow { background-color: #0d0d0f; }
    QTextBrowser { background-color: #0d0d0f; border: none; color: #ececf1; font-size: 15px; font-family: 'Segoe UI', Tahoma, sans-serif; }
    QLineEdit { background-color: #1a1b1e; color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #2b2c31; font-size: 15px; }
    QLineEdit:focus { border: 1px solid #10a37f; }
    QPushButton { background-color: #10a37f; color: white; border-radius: 12px; padding: 10px 20px; font-weight: bold; font-size: 15px;}
    QPushButton:hover { background-color: #0d8a6b; }
    QPushButton:disabled { background-color: #2b2c31; color: #888888; }
    QFrame#Header { background-color: #1a1b1e; border-bottom: 1px solid #2b2c31; }
    QLabel#ChipGPU { background-color: #76b900; color: white; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 10px;}
    QLabel#ChipCPU { background-color: #007acc; color: white; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 10px;}
"""

class BridgeManager(QThread):
    packet_received = Signal(str, str)
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
        self.kill_socket.connect(self._force_kill_socket)

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.start_ws())

    @Slot()
    def _force_kill_socket(self):
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)

    async def start_ws(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        kwargs = {"ping_interval": 10, "ping_timeout": 20}
        if SERVER_URI.startswith("wss://"): kwargs["ssl"] = ssl_context

        while self.running:
            try:
                async with websockets.connect(SERVER_URI, **kwargs) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.connection_status.emit(True)
                    
                    async for message in ws:
                        if not self.running: break
                        try:
                            data = json.loads(message)
                            if data.get("type") == "ping":
                                await ws.send(json.dumps({"type": "pong"}))
                                continue
                                
                            if "payload" in data:
                                self.reconnect_attempts = 0 
                                decrypted = decrypt_message(data["payload"])
                                packet = json.loads(decrypted)
                                p_type = packet.get("type", "unknown")
                                p_content = packet.get("content", "")
                                
                                if p_type == "sys_status":
                                    self.sys_status.emit(p_content == "online", packet.get("hw", "CPU"))
                                else:
                                    self.packet_received.emit(p_type, p_content)
                        except Exception: pass
                    self.ws = None; self.is_connected = False; self.connection_status.emit(False)
            except Exception:
                self.ws = None; self.is_connected = False; self.connection_status.emit(False)
                if self.running:
                    delay = min(30.0, (2 ** self.reconnect_attempts) + random.random())
                    self.reconnect_attempts += 1
                    await asyncio.sleep(delay)

    def send_msg(self, text):
        if self.ws and self.is_connected:
            try:
                payload = json.dumps({"type": "chat", "text": text})
                asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps({"payload": encrypt_message(payload)})), self.loop)
                return True
            except Exception: pass
        return False

    def stop(self):
        self.running = False; self.is_connected = False
        if self.ws: asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        
        # گارانتی بسته شدن امن Event Loop
        for task in asyncio.all_tasks(self.loop):
            task.cancel()
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError: pass

class ModernChatWindow(QMainWindow):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.setWindowTitle("AI Workspace")
        self.setMinimumSize(650, 800)
        self.setStyleSheet(DARK_STYLESHEET)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0,0,0,0)

        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        self.status_label = QLabel("🔴 آفلاین")
        self.status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
        
        title = QLabel("AI Workspace")
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: #fff;")
        title.setAlignment(Qt.AlignCenter)
        
        pc_info_layout = QHBoxLayout()
        self.pc_status_label = QLabel("🖥️ سرور: نامشخص")
        self.pc_status_label.setStyleSheet("color: #9ca3af; font-weight: bold; font-size: 13px;")
        self.hw_chip = QLabel("OFF")
        self.hw_chip.setObjectName("ChipCPU")
        self.hw_chip.setVisible(False)
        pc_info_layout.addWidget(self.pc_status_label)
        pc_info_layout.addWidget(self.hw_chip)
        
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(title, 1)
        header_layout.addLayout(pc_info_layout)
        main_layout.addWidget(header)

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(20, 20, 20, 0)
        
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.document().setDefaultStyleSheet("""
            pre { background-color: #0d1117; padding: 15px; border-radius: 8px; border: 1px solid #30363d; color: #e6edf3; font-family: 'Consolas'; font-size: 13.5px; margin: 15px 0;}
            code { background-color: #2b2b2b; color: #ff7b72; padding: 3px 6px; border-radius: 4px; font-family: 'Consolas'; font-size: 13px;}
            table { border-collapse: collapse; width: 100%; margin: 15px 0;}
            th, td { border: 1px solid #30363d; padding: 10px; text-align: right;}
            th { background-color: #161b22; color: #f3f4f6;}
            a { color: #10a37f; text-decoration: none; }
        """)
        chat_layout.addWidget(self.chat_display)
        main_layout.addWidget(chat_container)

        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(20, 15, 20, 20)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("پیام خود را بنویسید...")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("ارسال")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setFixedWidth(80)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        main_layout.addWidget(input_container)

        self.chat_history = []
        self.current_ai_text = ""
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

    def reset_watchdog(self):
        if self.is_streaming or self.is_thinking:
            self.watchdog_timer.start(60000) 
        else:
            self.watchdog_timer.stop()
            
    def watchdog_timeout(self):
        self.handle_packet("error", "تایم‌اوت ارتباط با سرور.")
        self.bridge.kill_socket.emit()

    def update_thinking_anim(self):
        self.dots = (self.dots + 1) % 4
        self.update_ui()

    def update_ui(self):
        full_html = ""
        for i, msg in enumerate(self.chat_history):
            sender = msg["role"]
            is_last = (i == len(self.chat_history) - 1)
            
            if sender == "sys":
                 full_html += f"<div style='text-align:center; margin-top:15px;'><span style='background:#1a1b1e; padding:5px 15px; border-radius:15px; color:#9ca3af; border:1px solid #2b2c31; font-size:12px;'>{msg['content']}</span></div><br>"
                 continue

            if sender == "user":
                content = markdown.markdown(msg["content"], extensions=['fenced_code', 'tables', 'nl2br'])
                full_html += f"""
                <div style='text-align:right; margin-bottom: 20px;'>
                    <span style='color:#9ca3af; font-size:12px; font-weight:bold;'>شما</span><br>
                    <div style='display:inline-block; background-color:#2d2e33; border: 1px solid #2b2c31; padding:12px 18px; border-radius:16px; border-top-right-radius:4px; text-align:right; max-width:85%;'>
                        {content}
                    </div>
                </div>
                """
            elif sender == "ai":
                content_html = ""
                if is_last and self.is_thinking:
                    content_html = "در حال پردازش" + ("." * self.dots)
                elif is_last and self.is_streaming:
                    content_html = html.escape(msg["content"]).replace('\n', '<br>')
                else:
                    content_html = markdown.markdown(msg["content"], extensions=['fenced_code', 'tables', 'nl2br'])
                
                full_html += f"""
                <div style='text-align:left; margin-bottom: 20px; direction:rtl;'>
                    <span style='color:#10a37f; font-size:12px; font-weight:bold;'>هوش مصنوعی</span><br>
                    <div style='display:block; width:100%;'>
                        {content_html}
                    </div>
                </div>
                """
        
        self.chat_display.setHtml(full_html)
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str, str)
    def handle_packet(self, msg_type, content):
        if msg_type == "status" and content == "thinking":
            self.is_thinking = True
            self.think_timer.start(500)
            self.chat_history.append({"role": "ai", "content": ""})
            self.update_ui(); self.reset_watchdog()
            
        elif msg_type == "chunk":
            if not content: return
            if self.is_thinking:
                self.is_thinking = False; self.think_timer.stop()
            if not self.is_streaming:
                self.is_streaming = True
                if self.chat_history[-1]["role"] == "ai": self.chat_history[-1]["content"] = content
                else: self.chat_history.append({"role": "ai", "content": content})
            else: self.chat_history[-1]["content"] += content
            self.update_ui(); self.reset_watchdog()
            
        elif msg_type == "done" or msg_type == "full":
            self.is_streaming = False; self.is_thinking = False; self.think_timer.stop(); self.watchdog_timer.stop()
            if msg_type == "full":
                if self.chat_history and self.chat_history[-1]["role"] == "ai" and self.chat_history[-1]["content"] == "":
                    self.chat_history[-1]["content"] = content
                else: self.chat_history.append({"role": "ai", "content": content})
            self.unlock_inputs(); self.update_ui()
            
        elif msg_type == "queue":
            if self.chat_history and self.chat_history[-1]["content"] == content: return
            self.chat_history.append({"role": "sys", "content": content}); self.update_ui()
            
        elif msg_type == "error":
            self.is_streaming = False; self.is_thinking = False; self.think_timer.stop(); self.watchdog_timer.stop()
            err_msg = f"❌ {content}"
            if self.chat_history and self.chat_history[-1]["role"] == "ai" and self.chat_history[-1]["content"] == "":
                self.chat_history.pop()
            if self.chat_history and self.chat_history[-1]["content"] == err_msg:
                self.unlock_inputs(); return
            self.chat_history.append({"role": "sys", "content": err_msg})
            self.unlock_inputs(); self.update_ui()

    @Slot(bool)
    def update_status(self, connected):
        if connected:
            self.status_label.setText("🟢 آنلاین")
            self.status_label.setStyleSheet("color: #10a37f; font-weight: bold; font-size: 13px;")
        else:
            self.status_label.setText("🔴 آفلاین")
            self.status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            self.pc_status_label.setText("🖥️ سرور: قطع ارتباط")
            self.pc_status_label.setStyleSheet("color: #9ca3af; font-weight: bold; font-size: 13px;")
            self.hw_chip.setVisible(False)

    @Slot(bool, str)
    def update_pc_status(self, is_online, hw_mode):
        if is_online:
            self.pc_status_label.setText("🖥️ سرور: آماده")
            self.pc_status_label.setStyleSheet("color: #10a37f; font-weight: bold; font-size: 13px;")
            self.hw_chip.setVisible(True)
            self.hw_chip.setText(hw_mode)
            self.hw_chip.setObjectName("ChipGPU" if hw_mode == "GPU" else "ChipCPU")
            self.hw_chip.style().unpolish(self.hw_chip)
            self.hw_chip.style().polish(self.hw_chip)
        else:
            self.pc_status_label.setText("🖥️ سرور: خاموش")
            self.pc_status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            self.hw_chip.setVisible(False)

    def lock_inputs(self):
        self.input_field.setDisabled(True); self.send_btn.setDisabled(True)

    def unlock_inputs(self):
        self.input_field.setDisabled(False); self.send_btn.setDisabled(False)
        self.input_field.setFocus()

    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            if self.bridge.send_msg(text):
                self.chat_history.append({"role": "user", "content": text})
                self.lock_inputs(); self.update_ui(); self.input_field.clear()
            else:
                if not (self.chat_history and self.chat_history[-1]["content"] == "ارتباط قطع است."):
                    self.chat_history.append({"role": "sys", "content": "ارتباط قطع است."})
                self.update_ui()

    def closeEvent(self, event):
        self.bridge.stop(); self.bridge.wait(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    bridge = BridgeManager()
    bridge.start()
    window = ModernChatWindow(bridge)
    window.show()
    sys.exit(app.exec())