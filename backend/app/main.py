"""Drama Studio 后端入口：uvicorn app.main:app --port 8766"""
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import BASE_DIR
from .db import init_db

init_db()

# 系统预置提示词模板（幂等写入）：全局 scope + 逐项目 scope 都要同步——
# 项目创建时会复制一份 project 级系统模板，只同步全局的话旧项目永远用旧措辞。
from .db import SessionLocal, Project  # noqa: E402
from .services.prompt_templates import seed_templates  # noqa: E402
from sqlalchemy import select as _sa_select  # noqa: E402

with SessionLocal() as _s:
    seed_templates(_s, project_id=None)
    for _p in _s.scalars(_sa_select(Project)).all():
        seed_templates(_s, project_id=_p.id)

# 僵尸任务收尸：进程重启后遗留的 running/pending 任务不可能再被执行（asyncio 任务
# 随旧进程消失）。这里不再一刀切标 failed——长任务（H3 单条 15-30 分钟）每次重启都
# 变成一条红色失败记录，队列里"失败进程一直出现"，但其中大部分只是被重启打断、
# 重跑一次就好的任务。改标 interrupted（前端灰色「已中断」+ 继续按钮），
# 用「继续」按原 params 重新派发；真正执行报错的任务仍走 failed。
from sqlalchemy import select as _select  # noqa: E402
from .db import TaskRecord  # noqa: E402

with SessionLocal() as _s:
    _stale = _s.scalars(_select(TaskRecord).where(
        TaskRecord.status.in_(["running", "pending"]))).all()
    for _t in _stale:
        _t.status = "interrupted"
        _t.error = "服务重启导致中断，点「继续」按原参数重跑"
    _s.commit()
# 上次进程有没有留下 running：有则 ComfyUI 队列里那些 prompt 一定没人认领，
# 启动后清一次（否则它们继续占 GPU，重启后的新任务排队等到超时）。
_had_stale = bool(_stale)

app = FastAPI(title="Drama Studio", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(router)


async def _purge_comfy_orphans():
    """清掉上次进程留在 ComfyUI 队列里的孤儿 prompt（中断当前 + 删 pending）。"""
    from .adapters.comfyui_adapter import ComfyUIAdapter
    n = await ComfyUIAdapter().purge_queue()
    if n:
        print(f"[startup] 已清理 ComfyUI 孤儿 prompt {n} 条（上次进程崩溃/重启残留）")


@app.on_event("startup")
async def _capture_main_loop():
    # 登记主事件循环：export/stitch 等工作线程里的进度更新要经它投递 SSE
    from .scheduler import queue as _q
    _q.set_main_loop(asyncio.get_running_loop())
    # 长任务兜底：running 但长时间无进度 → interrupted（防"假运行"堵住 GPU 锁）
    _q.spawn_bg(_q.watchdog())
    if _had_stale:
        _q.spawn_bg(_purge_comfy_orphans())


@app.get("/api/health")
def health():
    return {"name": "Drama Studio API", "version": "0.2.0"}


# 前端构建产物（frontend/dist）静态托管；必须放在 /api 路由之后挂载，
# 且不能挡住后注册的 /api/health（根前缀 mount 会按注册顺序先匹配）。
_dist = BASE_DIR.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
