# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.v1 import ocr, translate, tasks

app = FastAPI(title="AI Video Localizer API", version="1.0.0")

# CORS — cho phép WPF app gọi
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký routers
app.include_router(ocr.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "message": "Backend đang chạy"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
