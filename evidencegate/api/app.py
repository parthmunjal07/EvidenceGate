from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from typing import List

app = FastAPI(title="SIH26145 EvidenceGate", version="0.1.0")

class HealthResponse(BaseModel):
    status: str

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}

@app.get("/results")
async def get_results(cursor: str = None, limit: int = 100):
    # Durable REST/SQLite cursor query placeholder
    return {"results": [], "next_cursor": None}

@app.websocket("/live")
async def live_updates(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Bounded summaries only. 
            # In MVP, we just ping or wait for results from a broadcast channel.
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")
    except Exception:
        pass
    finally:
        pass
