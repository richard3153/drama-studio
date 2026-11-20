@echo off
REM Drama Studio 一键启动（M1：后端 API；浏览器打开 http://127.0.0.1:8766/docs）
cd /d "%~dp0backend"
if not exist .venv (
  echo [init] 创建 Python 虚拟环境...
  python -m venv .venv
  call .venv\Scripts\pip install -r requirements.txt
) else (
  call .venv\Scripts\python -m pip install -q -r requirements.txt
)
echo [run] http://127.0.0.1:8766/docs
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
