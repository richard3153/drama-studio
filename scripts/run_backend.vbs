' Drama Studio backend autostart - hidden console, no window.
' Invoked by scheduled task DramaStudio-Backend (wscript.exe, window style 0).
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\WFMJ\drama-studio\backend"
sh.Run "cmd /c .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8766 >> uvicorn_out.log 2>> uvicorn_err.log", 0, False
