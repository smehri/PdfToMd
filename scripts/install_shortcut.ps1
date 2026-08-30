<#
    Creates a "PdfToMd" shortcut with the app icon.

    Usage (from the repo root):
        powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1

    Options:
        -StartMenu   also add it to the Start Menu
        -Remove      delete the shortcuts again
#>

param(
    [switch]$StartMenu,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$root     = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "PdfToMd.vbs"
$icon     = Join-Path $root "assets\app.ico"

$targets = @([IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "PdfToMd.lnk"))
if ($StartMenu) {
    $programs = [Environment]::GetFolderPath("Programs")
    $targets += [IO.Path]::Combine($programs, "PdfToMd.lnk")
}

if ($Remove) {
    foreach ($t in $targets) {
        if (Test-Path $t) { Remove-Item $t -Force; Write-Host "Removed $t" }
    }
    return
}

foreach ($p in @($launcher, $icon)) {
    if (-not (Test-Path $p)) { throw "Missing required file: $p" }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($target in $targets) {
    $parent = Split-Path -Parent $target
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }

    $sc = $shell.CreateShortcut($target)
    # wscript runs the .vbs with no console window of its own.
    $sc.TargetPath       = Join-Path $env:WINDIR "System32\wscript.exe"
    $sc.Arguments        = '"{0}"' -f $launcher
    $sc.WorkingDirectory = $root
    $sc.IconLocation     = "$icon,0"
    $sc.Description      = "Convert PDFs to Markdown"
    $sc.WindowStyle      = 7   # minimised, so nothing flashes
    $sc.Save()

    Write-Host "Created $target"
}

Write-Host ""
Write-Host "Double-click the PdfToMd icon to start the app."
