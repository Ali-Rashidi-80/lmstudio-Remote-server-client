
import asyncio, json, logging, httpx, websockets, ssl, base64

from Crypto.Cipher import AES

from Crypto.Util.Padding import pad, unpad



# کلید باید دقیقاً 32 بایت باشد (مشابه کلیدی که در HTML گذاشتید)

KEY = b'12345678901234567890123456789012' 

LMSTUDIO_URL = "http://192.169.1.63:1234/v1/chat/completions"

SERVER_URI = "wss://lmstudio.chbk.dev/ws/pc"



logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("PC-Client")



def encrypt(text):

    cipher = AES.new(KEY, AES.MODE_ECB)

    return base64.b64encode(cipher.encrypt(pad(text.encode('utf-8'), 16))).decode('utf-8')



def decrypt(enc_text):

    cipher = AES.new(KEY, AES.MODE_ECB)

    return unpad(cipher.decrypt(base64.b64decode(enc_text)), 16).decode('utf-8')



async def fetch_ai_response(prompt: str) -> str:

    async with httpx.AsyncClient(timeout=120.0) as client:

        try:

            resp = await client.post(LMSTUDIO_URL, json={"messages": [{"role": "user", "content": prompt}]})

            return resp.json()['choices'][0]['message']['content']

        except Exception as e:

            return f"خطا در مدل: {e}"



async def pc_worker():

    ssl_context = ssl.create_default_context()

    ssl_context.check_hostname = False

    ssl_context.verify_mode = ssl.CERT_NONE



    while True:

        try:

            logger.info("Connecting to server...")

            async with websockets.connect(SERVER_URI, ssl=ssl_context, ping_interval=20, ping_timeout=10) as ws:

                logger.info("Connected successfully.")

                async for raw_data in ws:

                    msg = json.loads(raw_data)

                    

                    if "payload" in msg:

                        # رمزگشایی پیام دریافتی از وب

                        decrypted_text = decrypt(msg["payload"])

                        logger.info(f"Received: {decrypted_text}")

                        

                        # دریافت پاسخ از AI

                        ai_answer = await fetch_ai_response(decrypted_text)

                        

                        # رمزنگاری و ارسال به سرور

                        encrypted_resp = encrypt(ai_answer)

                        await ws.send(json.dumps({"type": "response", "payload": encrypted_resp}))

                        

        except Exception as e:

            logger.warning(f"Connection error: {e}. Retrying in 5s...")

            await asyncio.sleep(5)



if __name__ == "__main__":

    asyncio.run(pc_worker())






















# import asyncio, json, logging, httpx, websockets, ssl

# from cryptography.fernet import Fernet

# from config import get_encryption_key



# logging.basicConfig(level=logging.INFO)

# logger = logging.getLogger("PC-Client")

# CIPHER = Fernet(get_encryption_key())

# LMSTUDIO_URL = "http://192.169.1.63:1234/v1/chat/completions"

# SERVER_URI = "wss://lmstudio.chbk.dev/ws/pc"



# async def fetch_ai_response(prompt: str) -> str:

#     async with httpx.AsyncClient(timeout=120.0) as client:

#         try:

#             resp = await client.post(LMSTUDIO_URL, json={"messages": [{"role": "user", "content": prompt}]})

#             return resp.json()['choices'][0]['message']['content']

#         except Exception as e:

#             return f"خطا: {e}"



# async def pc_worker():

#     ssl_context = ssl.create_default_context()

#     ssl_context.check_hostname = False

#     ssl_context.verify_mode = ssl.CERT_NONE



#     while True:

#         try:

#             async with websockets.connect(SERVER_URI, ssl=ssl_context, ping_interval=2, ping_timeout=10) as ws:

#                 logger.info("Connected to Server.")

#                 async for raw_data in ws:

#                     msg = json.loads(raw_data)

#                     if "payload" in msg:

#                         decrypted_text = CIPHER.decrypt(msg["payload"].encode()).decode()

#                         ai_answer = await fetch_ai_response(decrypted_text)

#                         await ws.send(json.dumps({"type": "response", "payload": CIPHER.encrypt(ai_answer.encode()).decode()}))

#         except Exception as e:

#             logger.warning(f"Connection error: {e}. Retrying...")

#             await asyncio.sleep(5)



# if __name__ == "__main__":

#     asyncio.run(pc_worker())
