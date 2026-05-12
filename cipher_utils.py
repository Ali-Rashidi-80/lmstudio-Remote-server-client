
from Crypto.Cipher import AES

from Crypto.Util.Padding import pad, unpad

import base64



KEY = b'12345678901234567890123456789012' # 32 bytes



def encrypt(text):

    cipher = AES.new(KEY, AES.MODE_ECB)

    return base64.b64encode(cipher.encrypt(pad(text.encode(), 16))).decode()



def decrypt(enc_text):

    cipher = AES.new(KEY, AES.MODE_ECB)

    return unpad(cipher.decrypt(base64.b64decode(enc_text)), 16).decode()
