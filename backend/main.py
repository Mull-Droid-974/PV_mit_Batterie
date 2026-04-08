from fastapi import FastAPI
from backend.routers import data, simulate

app = FastAPI()

app.include_router(data.router)
app.include_router(simulate.router)
