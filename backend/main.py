from fastapi import FastAPI

from app.api import forecast, layer2

app = FastAPI()
app.include_router(forecast.router)
app.include_router(layer2.router)


@app.get("/health")
def health():
    return {"status": "ok"}
