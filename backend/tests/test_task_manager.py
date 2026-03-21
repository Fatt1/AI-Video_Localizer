# backend/tests/test_task_manager.py
import asyncio
import pytest
from core.task_manager import TaskManager, TaskStatus


@pytest.fixture
def manager():
    return TaskManager()


def test_create_task(manager):
    task = manager.create_task("ocr")
    assert task.task_id is not None
    assert task.task_type == "ocr"
    assert task.status == TaskStatus.PENDING


def test_get_task(manager):
    task = manager.create_task("translate")
    found = manager.get_task(task.task_id)
    assert found is task


def test_get_task_not_found(manager):
    assert manager.get_task("nonexistent-id") is None


def test_cancel_task_not_running(manager):
    task = manager.create_task("ocr")
    # Task PENDING → cancel thất bại (chỉ cancel khi RUNNING)
    result = manager.cancel_task(task.task_id)
    assert result is False


def test_cancel_task_running(manager):
    task = manager.create_task("ocr")
    task.status = TaskStatus.RUNNING
    result = manager.cancel_task(task.task_id)
    assert result is True
    assert task.is_cancelled() is True
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_task_update_progress(manager):
    task = manager.create_task("ocr")
    queue = task.subscribe()
    await task.update(50, "Đang xử lý...")
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["progress"] == 50
    assert event["message"] == "Đang xử lý..."
    assert event["type"] == "progress"


@pytest.mark.asyncio
async def test_task_complete(manager):
    task = manager.create_task("ocr")
    queue = task.subscribe()
    await task.complete(result={"srt_path": "/tmp/ocr.srt"})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["type"] == "complete"
    assert event["progress"] == 100
    assert task.status == TaskStatus.COMPLETED
    # None signal (stream kết thúc)
    end_signal = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert end_signal is None


@pytest.mark.asyncio
async def test_task_fail(manager):
    task = manager.create_task("ocr")
    queue = task.subscribe()
    await task.fail("Lỗi FFmpeg!")
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["type"] == "error"
    assert event["message"] == "Lỗi FFmpeg!"
    assert task.status == TaskStatus.FAILED
