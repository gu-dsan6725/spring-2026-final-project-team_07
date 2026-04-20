from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from personal_nutritionist.agents.orchestrator.agent import create_orchestrator

load_dotenv()

_agents: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _agents.clear()


app = FastAPI(title="Personal Nutritionist", lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    user_id: str
    response: str


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    if body.user_id not in _agents:
        _agents[body.user_id] = create_orchestrator(user_id=body.user_id)
    response = _agents[body.user_id](body.message)
    return ChatResponse(user_id=body.user_id, response=str(response))


@app.delete("/chat/{user_id}")
def reset_session(user_id: str):
    _agents.pop(user_id, None)
    return {"status": "ok", "user_id": user_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
