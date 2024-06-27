from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import subprocess
import tempfile
import os
import uuid
import json

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Store active connections and rooms
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.rooms = set()  # Store created room IDs
        self.users = {}  # Store user information

    async def connect(self, websocket: WebSocket, room_id: str, username: str):
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        self.users[websocket] = {"username": username, "room_id": room_id}

    def disconnect(self, websocket: WebSocket):
        room_id = self.users[websocket]["room_id"]
        self.active_connections[room_id].remove(websocket)
        del self.users[websocket]

    async def broadcast(self, message: dict, room_id: str):
        for connection in self.active_connections[room_id]:
            await connection.send_json(message)

    def create_room(self):
        room_id = str(uuid.uuid4())
        self.rooms.add(room_id)
        return room_id

    def room_exists(self, room_id: str):
        return room_id in self.rooms

manager = ConnectionManager()

@app.get("/")
async def get():
    with open("static/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/create-room")
async def create_room():
    room_id = manager.create_room()
    return JSONResponse(content={"room_id": room_id})

@app.get("/join-room/{room_id}")
async def join_room(room_id: str):
    if not manager.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    return JSONResponse(content={"status": "success"})

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    if not manager.room_exists(room_id):
        await websocket.close(code=4000)
        return
    
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        username = data.get("username", "Anonymous")
        
        await manager.connect(websocket, room_id, username)
        await manager.broadcast({"type": "status", "content": f"{username} joined the room"}, room_id)
        
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            content = data.get("content")
            if message_type == "code":
                await manager.broadcast({"type": "code", "content": content, "username": username}, room_id)
            elif message_type == "run":
                output = compile_and_run_java(content)
                await manager.broadcast({"type": "output", "content": output}, room_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast({"type": "status", "content": f"{username} left the room"}, room_id)

def compile_and_run_java(code):
    with tempfile.TemporaryDirectory() as tmpdir:
        java_file = os.path.join(tmpdir, "Main.java")
        with open(java_file, "w") as f:
            f.write(code)

        compile_command = f"javac {java_file}"
        compile_process = subprocess.run(compile_command, shell=True, capture_output=True, text=True)
        
        if compile_process.returncode != 0:
            return f"Compilation Error:\n{compile_process.stderr}"

        run_command = f"java -cp {tmpdir} Main"
        run_process = subprocess.run(run_command, shell=True, capture_output=True, text=True, timeout=10)
        
        if run_process.returncode != 0:
            return f"Runtime Error:\n{run_process.stderr}"
        
        return run_process.stdout

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)