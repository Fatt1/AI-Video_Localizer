# backend/core/task_manager.py
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, AsyncGenerator
import json


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = ""
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self._cancel_flag = False
        self._subscribers: list[asyncio.Queue] = []

    def is_cancelled(self) -> bool:
        return self._cancel_flag

    def cancel(self):
        self._cancel_flag = True
        self.status = TaskStatus.CANCELLED

    async def update(self, progress: int, message: str, status: TaskStatus = None):
        self.progress = progress
        self.message = message
        if status:
            self.status = status
        event = {
            "type": "progress",
            "task_id": self.task_id,
            "progress": progress,
            "message": message,
            "status": self.status.value
        }
        for queue in self._subscribers:
            await queue.put(event)

    async def complete(self, result=None):
        self.status = TaskStatus.COMPLETED
        self.progress = 100
        self.result = result
        event = {
            "type": "complete",
            "task_id": self.task_id,
            "progress": 100,
            "message": "Hoàn thành!",
            "status": TaskStatus.COMPLETED.value,
            "result": result
        }
        for queue in self._subscribers:
            await queue.put(event)
            await queue.put(None)  # Signal kết thúc stream

    async def fail(self, error: str):
        self.status = TaskStatus.FAILED
        self.error = error
        event = {
            "type": "error",
            "task_id": self.task_id,
            "progress": self.progress,
            "message": error,
            "status": TaskStatus.FAILED.value
        }
        for queue in self._subscribers:
            await queue.put(event)
            await queue.put(None)

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._subscribers:
            self._subscribers.remove(queue)


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create_task(self, task_type: str) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(task_id, task_type)
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.cancel()
            return True
        return False

    async def stream_task(self, task_id: str) -> AsyncGenerator[str, None]:
        task = self._tasks.get(task_id)
        if not task:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Task không tồn tại'})}\n\n"
            return
        queue = task.subscribe()
        try:
            while True:
                try:
                    # Chờ event tối đa 20s (FastAPI / Uvicorn đôi khi ngắt kết nối tĩnh)
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    if event is None:  # Nút chặn Stream kết thúc
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Gửi keepalive để tránh bị trình duyệt / httpClient ngắt kết nối, rồi LẶP LẠI
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
        finally:
            task.unsubscribe(queue)


# Singleton instance dùng chung cho toàn bộ app
task_manager = TaskManager()
