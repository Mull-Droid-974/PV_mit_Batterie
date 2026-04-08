from fastapi import FastAPI
from backend.routers import data

app = FastAPI()

app.include_router(data.router)
