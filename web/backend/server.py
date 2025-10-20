"""
FastAPI server for real-time log broadcasting.
Serves the web UI and handles WebSocket connections.
"""
import sys
import os
from pathlib import Path
import signal
import socket

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import asyncio
import threading

from src.utils.logging import WebSocketManager, set_websocket_manager
from src.core.orchestrator import run_pipeline

app = FastAPI(title="MedDataOS Monitor")

# Global server reference for cleanup
_server = None

# Initialize WebSocket manager
ws_manager = WebSocketManager()
set_websocket_manager(ws_manager)

# Serve static files (frontend)
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


@app.get("/")
async def read_root():
    """Serve the main HTML page."""
    return FileResponse(str(frontend_path / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    ws_manager.connect(websocket)

    # Set the event loop for the WebSocket manager
    if ws_manager.loop is None:
        ws_manager.set_loop(asyncio.get_event_loop())

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "system",
            "message": "Connected to MedDataOS Monitor",
            "timestamp": ""
        })

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Echo back for keep-alive (optional)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


@app.post("/api/start")
async def start_pipeline(request: dict):
    """Start the agent pipeline with user query in a background thread."""
    user_query = request.get("query", "")

    if not user_query:
        return {"status": "error", "message": "Query is required"}

    def run_in_thread():
        run_pipeline(user_query)

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"status": "started", "query": user_query}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_connections": len(ws_manager.active_connections)
    }


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def kill_process_on_port(port: int):
    """Kill any process using the specified port."""
    import subprocess
    try:
        # Find process using the port
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                print(f"⚠️  Killing existing process on port {port} (PID: {pid})")
                subprocess.run(['kill', '-9', pid])
            import time
            time.sleep(0.5)  # Give it time to release
    except Exception as e:
        print(f"Could not kill process on port {port}: {e}")


def start_server(host: str = "127.0.0.1", port: int = 8080):
    """Start the FastAPI server with proper cleanup."""
    global _server

    print(f"\n🌐 Starting MedDataOS Web Monitor...")

    # Check if port is available, kill existing process if needed
    if not check_port_available(host, port):
        print(f"⚠️  Port {port} is already in use")
        kill_process_on_port(port)

        # Verify port is now available
        if not check_port_available(host, port):
            print(f"❌ Failed to free port {port}. Please manually kill the process.")
            print(f"   Run: lsof -ti :{port} | xargs kill -9")
            sys.exit(1)

    print(f"📡 WebSocket server: ws://{host}:{port}/ws")
    print(f"🖥️  Web UI: http://{host}:{port}")
    print(f"💡 Press Ctrl+C to stop (NOT Ctrl+Z)\n")

    # Configure uvicorn with proper socket reuse
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,  # Reduce noise
        server_header=False,
        date_header=False
    )

    _server = uvicorn.Server(config)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutting down MedDataOS Monitor...")
        if _server:
            _server.should_exit = True
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        _server.run()
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        print("✓ Server stopped cleanly")


if __name__ == "__main__":
    start_server()
