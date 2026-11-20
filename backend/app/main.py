"""Drama Studio 后端入口：uvicorn app.main:app --port 8766"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import BASE_DIR
from .db import init_db

init_db()

# 系统预置提示词模板（幂等写入，全局 scope）
from .db import SessionLocal  # noqa: E402
from .services.prompt_templates import seed_templates  # noqa: E402

with SessionLocal() as _s:
    seed_templates(_s, project_id=None)

# 僵尸任务收尸：进程重启后遗留的 running/pending 任务不可能再被执行（asyncio 任务
# 随旧进程消失），启动时统一标 failed，避免接口永远等一个卡死的任务。
from sqlalchemy import select as _select  # noqa: E402
from .db import TaskRecord  # noqa: E402

with SessionLocal() as _s:
    _stale = _s.scalars(_select(TaskRecord).where(
        TaskRecord.status.in_(["running", "pending"]))).all()
    for _t in _stale:
        _t.status = "failed"
        _t.error = "进程重启中断（启动收尸）"
    _s.commit()

app = FastAPI(title="Drama Studio", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return {"name": "Drama Studio API", "version": "0.2.0"}


# 前端构建产物（frontend/dist）静态托管；必须放在 /api 路由之后挂载，
# 且不能挡住后注册的 /api/health（根前缀 mount 会按注册顺序先匹配）。
_dist = BASE_DIR.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
