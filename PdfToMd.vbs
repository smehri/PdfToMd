' PdfToMd launcher.
'
' Starts the local server with no console window and lets the app open the
' browser itself. Double-click this file, or the desktop shortcut that
' scripts\install_shortcut.ps1 creates.

Option Explicit

Dim shell, fso, root, python, quotedCmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve paths relative to this script, so the folder can be moved or renamed.
root = fso.GetParentFolderName(WScript.ScriptFullName)
python = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(python) Then
    MsgBox "Could not find:" & vbCrLf & python & vbCrLf & vbCrLf & _
           "Set up the environment first:" & vbCrLf & vbCrLf & _
           "  python -m venv .venv" & vbCrLf & _
           "  .venv\Scripts\python.exe -m pip install -r requirements.txt", _
           vbExclamation, "PdfToMd"
    WScript.Quit 1
End If

shell.CurrentDirectory = root

' pythonw.exe has no console, so nothing flashes on screen. 0 = hidden window,
' False = do not wait, so the launcher exits while the server keeps running.
quotedCmd = """" & python & """ -m pdftomd"
shell.Run quotedCmd, 0, False
