' ComfyUI auto-start (hidden window, idempotent).
' Skips when 8188 already answers or a ComfyUI python process exists.
' Logs append to backend\_comfy_boot.log
Option Explicit

Dim sh, base, py, logPath, cmd
Set sh = CreateObject("WScript.Shell")

base = "D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI"
py = base & "\ComfyUI\.venv\Scripts\python.exe"
logPath = "D:\WFMJ\drama-studio\backend\_comfy_boot.log"

If IsUp() Or IsRunning() Then
  WScript.Quit 0
End If

sh.CurrentDirectory = base
cmd = "cmd /c """ & py & """ -u -s ComfyUI\main.py --enable-manager " & _
      "--extra-model-paths-config ""D:\Comfy-Desktop\extra_paths.yaml"" " & _
      "--user-directory ""D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\user"" " & _
      ">> """ & logPath & """ 2>&1"
sh.Run cmd, 0, False
WScript.Quit 0

' 8188 already answers -> skip
Function IsUp()
  Dim h, code
  IsUp = False
  On Error Resume Next
  Set h = CreateObject("MSXML2.XMLHTTP")
  h.Open "GET", "http://127.0.0.1:8188/system_stats", False
  h.Send
  code = h.Status
  If Err.Number = 0 And code = 200 Then IsUp = True
  Err.Clear
End Function

' A ComfyUI process is alive (maybe still loading nodes, port not up yet) -> do not start a second one
Function IsRunning()
  Dim svc, procs, p
  IsRunning = False
  On Error Resume Next
  Set svc = GetObject("winmgmts:\\.\root\cimv2")
  Set procs = svc.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='python.exe'")
  For Each p In procs
    If InStr(1, p.CommandLine, "ComfyUI\main.py", vbTextCompare) > 0 Then
      IsRunning = True
      Exit For
    End If
  Next
  Err.Clear
End Function
