
import uvicorn

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request

from fastapi.templating import Jinja2Templates

from fastapi.staticfiles import StaticFiles

import logging



logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("BridgeServer")



app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")



class ConnectionManager:

    def __init__(self):

        self.active_connections = {}



    async def connect(self, websocket: WebSocket, user_id: str):

        await websocket.accept()

        self.active_connections[user_id] = websocket

        logger.info(f"Client {user_id} connected.")



    def disconnect(self, user_id: str):

        if user_id in self.active_connections:

            del self.active_connections[user_id]

            logger.info(f"Client {user_id} disconnected.")



    async def broadcast(self, sender_id: str, message: dict):

        # اگر موبایل (یا وب) فرستاد -> به PC بفرست و بالعکس

        target = "pc" if sender_id in ["mobile", "web"] else "mobile"

        if target in self.active_connections:

            await self.active_connections[target].send_json(message)



manager = ConnectionManager()



@app.get("/")

async def get_chat(request: Request):

    return templates.TemplateResponse("index.html", {"request": request})



@app.websocket("/ws/{user_id}")

async def websocket_endpoint(websocket: WebSocket, user_id: str):

    await manager.connect(websocket, user_id)

    try:

        while True:

            data = await websocket.receive_json()

            if data.get("type") == "ping":

                await websocket.send_json({"type": "pong"})

                continue

            await manager.broadcast(user_id, data)

    except WebSocketDisconnect:

        manager.disconnect(user_id)

    except Exception as e:

        logger.error(f"Error: {e}")

        manager.disconnect(user_id)




if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8000)
