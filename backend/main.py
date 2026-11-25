from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app.api import forecast, layer2, simulation

app = FastAPI()
# Compresses large responses when the browser accepts gzip (/api/shapes: about 2.3 MB down to 460 KB).
app.add_middleware(GZipMiddleware)
app.include_router(forecast.router)
app.include_router(layer2.router)
app.include_router(simulation.router)


@app.get("/health")
def health():
    return {"status": "ok"}
