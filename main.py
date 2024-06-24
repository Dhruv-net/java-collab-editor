from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import subprocess
import tempfile
import os
import uuid

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        self.active_connections[room_id].remove(websocket)

    async def broadcast(self, message: str, room_id: str):
        for connection in self.active_connections[room_id]:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/")
async def get():
    with open("static/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("CODE:"):
                code = data[5:]
                output = compile_and_run_java(code)
                await manager.broadcast(f"OUTPUT:{output}", room_id)
            else:
                await manager.broadcast(f"CODE:{data}", room_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

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