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
# 后台任务强引用集合：asyncio 事件循环只对 Task 持弱引用，
# 无引用任务会被 GC 中途销毁（asyncio 文档明确警告）——表现为任务跑着跑着悄悄消失，
# 且与页面刷新/内存抖动时机相关。所有 fire-and-forget 任务必须经 spawn_bg 持引用。
_bg_tasks: set[asyncio.Task] = set()
# 任务 id → 运行中的 asyncio.Task（取消运行中任务用）
_run_map: dict[int, asyncio.Task] = {}
# 主事件循环（启动时登记）：工作线程的进度更新经它投递回 SSE
_main_loop: asyncio.AbstractEventLoop | None = None


def spawn_bg(coro) -> asyncio.Task:
    """fire-and-forget 派发：强引用防 GC 中途销毁，完成自动清引用。"""
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


def register_runner(task_id: int, at: asyncio.Task):
    """登记任务执行协程，供 cancel 按 task_id 定位；结束自动摘除。"""
    _run_map[task_id] = at
    at.add_done_callback(lambda _: _run_map.pop(task_id, None))


def cancel_running(task_id: int) -> bool:
    """取消运行中（含排队等锁）任务的执行协程；没有在跑的返回 False。"""
    at = _run_map.get(task_id)
    if at is not None and not at.done():
        at.cancel()
        return True
    return False


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
    """执行任务并全程推送 SSE 进度；heavy 任务持互斥锁保证 GPU 串行。

    暂停语义：排队期间（等锁前/等锁中）状态被标 paused → 拿到锁后直接让位不执行，
    等待「继续」重新派发；已进入 GPU 推理的任务不支持暂停（只能取消）。
    """
    if t.status in ("paused", "cancelled"):   # 派发前已被暂停/取消：不启动
        await publish("task_update", {"task": task_to_dict(t)})
        return
    _set(db, t, status="running", started_at=now())
    await publish("task_update", {"task": task_to_dict(t)})
    try:
        if heavy:
            async with _heavy_lock:
                if t.status == "paused":      # 排队期间被暂停：持锁即让位
                    await publish("task_update", {"task": task_to_dict(t)})
                    return
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
        db.refresh(t)
        if t.status != "paused":
            # 排队等锁的任务被「暂停」时走 cancel 协程收尾——此时保留 paused，
            # 不被覆写成 cancelled（否则「继续」按钮消失，暂停语义失效）
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
    # 进度实时推送：任务开始/结束之外，中途 stage/百分比也推给 SSE 订阅者。
    # 大部分调用方在 async 上下文（直接 create_task 投递）；stitch/export 等在
    # 工作线程里跑（无 running loop），投递回启动时登记的主循环。
    d = task_to_dict(t)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(publish("task_update", {"task": d}))
    except RuntimeError:
        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(publish("task_update", {"task": d}),
                                             _main_loop)


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """启动时登记主事件循环（供工作线程里的进度更新投递 SSE）。"""
    global _main_loop
    _main_loop = loop
