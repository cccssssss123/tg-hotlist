' ===================================================================
'  tg-hotlist + exDesktop silent autostart  (no console windows)
'  - Starts tg-hotlist backend with pythonw (no black window)
'  - Uses --no-fallback: if 8765 is already taken (backend already
'    running) the new copy exits quietly, so no duplicate instances
'  - Then starts exDesktop
'  Intentionally ASCII-only (wscript reads .vbs as ANSI).
' ===================================================================
Option Explicit

Dim fso, sh, here, root, pyw, app, exd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)   ' ...\exdesktop
root = fso.GetParentFolderName(here)                     ' ...\default-workspace

pyw = root & "\tg-hotlist\.venv\Scripts\pythonw.exe"
app = root & "\tg-hotlist\web_app.py"
exd = here & "\app\Telegram.exe"

If Not fso.FileExists(pyw) Then
  MsgBox "Cannot find pythonw.exe:" & vbCrLf & pyw, 16, "tg-hotlist"
  WScript.Quit 1
End If
If Not fso.FileExists(exd) Then
  MsgBox "Cannot find exDesktop:" & vbCrLf & exd, 16, "tg-hotlist"
  WScript.Quit 1
End If

' Start backend silently. If already running, the new instance exits.
sh.Run """" & pyw & """ -X utf8 """ & app & """ --no-fallback", 0, False
WScript.Sleep 3500

' Start exDesktop
sh.Run """" & exd & """", 1, False
