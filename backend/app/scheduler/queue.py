"""串行任务队列 + SSE 事件总线（低显存调度约束 1/2/6）。"""
import asyncio
import json
import traceback
from typing import Awaitable, Callable

from ..db import SessionLocal, TaskRecord, task_to_dict, now

# SSE 订阅者集合（每个元素一个 asyncio.Queue）
_subscribers: set[asyncio.Queue] = set()
# 重模型互斥：同一时刻仅一个重任务（TTS/ASR/拼接等走 parallel 通道）
_heavy_lock = asyncio.Lock()


async def publish(event: str, data: dict):
    msg = json.dumps({"event": event, **data}, ensure_ascii=False)
    for q in list(_subscribers):
        try:
            q.put_nowait(msg)
        except Exception:
            _subscribers.discard(q)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue):
    _subscribers.discard(q)


def create_task(db, type_: str, params: dict, model_key: str = "", vram_gb: float = 0.0) -> TaskRecord:
    t = TaskRecord(type=type_, params_json=json.dumps(params, ensure_ascii=False),
                   model_key=model_key, vram_gb=vram_gb)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _set(db, t: TaskRecord, **fields):
    for k, v in fields.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)


async def run_task(db, t: TaskRecord, fn: Callable[[], Awaitable[dict]],
                   *, heavy: bool = True):
    """执行任务并全程推送 SSE 进度；heavy 任务持互斥锁保证 GPU 串行。"""
    _set(db, t, status="running", started_at=now())
    await publish("task_update", {"task": task_to_dict(t)})
    try:
        if heavy:
            async with _heavy_lock:
                result = await fn()
        else:
            result = await fn()
        _set(db, t, status="done", progress=1.0,
             result_json=json.dumps(result, ensure_ascii=False),
             finished_at=now())
        await publish("task_update", {"task": task_to_dict(t)})
        return result
    except asyncio.CancelledError:
        db.rollback()  # 丢弃 fn() 留下的半截事务，防止标状态时把未完成的删除/写入一并提交
        _set(db, t, status="cancelled", finished_at=now())
        await publish("task_update", {"task": task_to_dict(t)})
        raise
    except Exception as e:
        db.rollback()  # 闭环保护：任务失败必须回滚半截事务，否则异常前的删除会被下面 commit 提交掉
        _set(db, t, status="failed", error=f"{e}\n{traceback.format_exc()[-1500:]}",
             finished_at=now())
        await publish("task_update", {"task": task_to_dict(t)})


def update_progress(db, t: TaskRecord, progress: float, stage: str = ""):
    _set(db, t, progress=max(0.0, min(1.0, progress)), stage=stage)
    # 进度推送走同步上下文异步发布：调度器在 async 函数内调用此方法
