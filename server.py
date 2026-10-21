import asyncio
import json
import sqlite3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
from fastapi import HTTPException
from pydantic import BaseModel

app = FastAPI()

# Инициализация базы данных SQLite без дефолтных комнат
def init_db():
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)
    # Таблица чатов/комнат
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            name TEXT PRIMARY KEY
        )
    """)
    # Таблица друзей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            username TEXT,
            friend_name TEXT,
            PRIMARY KEY (username, friend_name)
        )
    """)
    conn.commit()
    conn.close()

init_db()

class ChatServer:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
        self.history: Dict[str, List[dict]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        await websocket.accept()
        if room not in self.rooms:
            self.rooms[room] = []
            self.history[room] = []
        self.rooms[room].append(websocket)
        
        # Отправляем историю чата
        for msg in self.history[room]:
            await websocket.send_json(msg)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)

    async def broadcast(self, room: str, message_data: dict):
        if room in self.history:
            self.history[room].append(message_data)
            if len(self.history[room]) > 50:
                self.history[room].pop(0)

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

class AuthData(BaseModel):
    username: str
    password: str

@app.post("/api/register")
def register(data: AuthData):
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (data.username, data.password))
        conn.commit()
        return {"status": "ok"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    finally:
        conn.close()

@app.post("/api/login")
def login(data: AuthData):
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (data.username, data.password))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Неверный логин или пароль")

@app.get("/api/rooms")
def get_rooms():
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM rooms")
    rooms = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rooms

class RoomData(BaseModel):
    name: str

@app.post("/api/rooms")
def create_room(data: RoomData):
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO rooms (name) VALUES (?)", (data.name,))
        conn.commit()
        return {"status": "ok"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Комната уже существует")
    finally:
        conn.close()

@app.get("/api/friends/{username}")
def get_friends(username: str):
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    cursor.execute("SELECT friend_name FROM friends WHERE username = ?", (username,))
    friends = [row[0] for row in cursor.fetchall()]
    conn.close()
    return friends

class FriendData(BaseModel):
    username: str
    friend_name: str

@app.post("/api/friends")
def add_friend(data: FriendData):
    conn = sqlite3.connect("messenger.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (data.friend_name,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    try:
        cursor.execute("INSERT INTO friends (username, friend_name) VALUES (?, ?)", (data.username, data.friend_name))
        conn.commit()
        return {"status": "ok"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Уже в друзьях")
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
