from fastapi import FastAPI

app = FastAPI(title="Saga Orchestrator Service")


@app.get("/")
def root():
    return {"message": "Saga Orchestrator Service radi"}