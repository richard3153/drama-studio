' Drama Studio backend autostart - hidden console, no window, idempotent.
' Invoked by scheduled task DramaStudio-Backend (wscript.exe, window style 0)
' and re-invoked every minute as a poor-man's watchdog: if 8766 already answers
' it exits immediately, so it never fights with a live process for the port.
' Why: running the 26GB Ideogram 4 fp8 pair on an 8G card (weight offload to RAM)
' has twice taken the uvicorn process down mid-generation with no Python
' traceback and no Windows Application Error event - the queue then sits on
' "running" until someone restarts by hand.
'
' 2026-11-28: 这里**不要**用 WMI 查进程来判断"是否正在启动"——实测从计划任务
' 里跑 wscript 时那条查询会把脚本卡住 5 分钟（任务状态 Running、后续每分钟的
' 触发全被 IgnoreNew 拒掉，后端始终没人拉起）。改用纯文件时间戳：启动后 90 秒
' 内的重复触发直接退出。两次触发挤在一起时，抢输的那个也不会变成僵尸实例。
Option Explicit

Dim sh, fso, base, logPath, marker, http, cmd

base = "D:\WFMJ\drama-studio\backend"
logPath = base & "\uvicorn_out.log"
marker = base & "\_backend_starting.lock"

Function IsUp()
  Dim h
  On Error Resume Next
  Set h = CreateObject("MSXML2.XMLHTTP")
  h.Open "GET", "http://127.0.0.1:8766/api/system", False
  h.Send
  IsUp = (Err.Number = 0 And h.Status = 200)
  Err.Clear
  On Error GoTo 0
End Function

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

If IsUp() Then
  WScript.Quit 0
End If

If fso.FileExists(marker) Then
  If DateDiff("s", fso.GetFile(marker).DateLastModified, Now) < 45 Then
    WScript.Quit 0
  End If
End If

' 打时间戳（已存在就改写内容，mtime 随之刷新）
Dim f
Set f = fso.OpenTextFile(marker, 2, True)
f.Write Now
f.Close

' 日志超过 8MB 就轮转一次，避免无限增长拖慢写入
If fso.FileExists(logPath) Then
  If fso.GetFile(logPath).Size > 8 * 1024 * 1024 Then
    fso.MoveFile logPath, base & "\uvicorn_out.log.old"
  End If
End If

sh.CurrentDirectory = base
sh.Run "cmd /c .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8766 >> uvicorn_out.log 2>> uvicorn_err.log", 0, False
