from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from core.task_manager import task_manager

router = APIRouter()

@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    """SSE endpoint — WPF app subscribe vào đây để nhận progress realtime"""
    return StreamingResponse(
        task_manager.stream_task(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    success = task_manager.cancel_task(task_id)
    if success:
        return {"status": "ok", "message": f"Đã hủy task {task_id}"}
    return {"status": "error", "message": "Không thể hủy task"}

@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        return {"status": "error", "message": "Task không tồn tại"}
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "progress": task.progress,
        "message": task.message,
        "result": task.result,
        "error": task.error
    }