import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List

app = FastAPI()

class ChatServer:
    def __init__(self):
        # Комнаты -> список подключенных сокетов
        self.rooms: Dict[str, List[WebSocket]] = {}
        # История сообщений по комнатам (последние 50 сообщений)
        self.history: Dict[str, List[dict]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        await websocket.accept()
        if room not in self.rooms:
            self.rooms[room] = []
            self.history[room] = []
        self.rooms[room].append(websocket)
        
        # Отправляем историю сообщений новому пользователю
        for msg in self.history[room]:
            await websocket.send_json(msg)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)

    async def broadcast(self, room: str, message_data: dict):
        # Сохраняем в историю
        if room in self.history:
            self.history[room].append(message_data)
            if len(self.history[room]) > 50:
                self.history[room].pop(0)

        # Пересылаем всем в этой комнате
        if room in self.rooms:
            for connection in self.rooms[room]:
                try:
                    await connection.send_json(message_data)
                except Exception:
                    pass

manager = ChatServer()

@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await manager.connect(websocket, room)
    try:
        while True:
            data = await websocket.receive_text()
            message_json = json.loads(data)
            await manager.broadcast(room, message_json)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
