<#
Add the Rewatchables site to your Start Menu: "Rewatchables Explorer" opens it
in its own window (starting the Observable Framework dev server on port 8577 if
needed) and "Stop Rewatchables Explorer" stops the server.

    powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -Python C:\path\to\python.exe
    powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -Uninstall

Per-user (no admin). Re-run after moving the repo or changing Python: the shortcuts
hold absolute paths. Both run launch_app.pyw under pythonw.exe, so no console
window opens.
#>
param(
    [string]$Python = "",
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

$Here = $PSScriptRoot
$Root = Split-Path -Parent $Here
$Launcher = Join-Path $Here "launch_app.pyw"
$Programs = [Environment]::GetFolderPath("Programs")   # %APPDATA%\Microsoft\Windows\Start Menu\Programs
$OpenLnk = Join-Path $Programs "Rewatchables Explorer.lnk"
$StopLnk = Join-Path $Programs "Stop Rewatchables Explorer.lnk"

if ($Uninstall) {
    foreach ($lnk in $OpenLnk, $StopLnk) {
        if (Test-Path $lnk) { Remove-Item $lnk; Write-Host "removed $lnk" }
    }
    return
}

# The Python that runs the launcher (and, through Framework, the site's data
# loader): the one on PATH unless -Python says otherwise.
if (-not $Python) { $Python = (& python -c "import sys; print(sys.executable)").Trim() }
# (Windows PowerShell turns any stderr line, even a deprecation warning, into an error
# under "Stop", so only the exit code decides.)
$ErrorActionPreference = "Continue"
& $Python -W ignore -c "import sys; assert sys.version_info >= (3, 11)" 2>$null
$ok = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"
if (-not $ok) {
    throw "$Python isn't Python 3.11+ -- pass -Python"
}
$Pythonw = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { throw "no pythonw.exe next to $Python" }

$Shell = New-Object -ComObject WScript.Shell
function New-Shortcut($Path, $Arguments, $Icon, $Description) {
    $s = $Shell.CreateShortcut($Path)
    $s.TargetPath = $Pythonw
    $s.Arguments = $Arguments
    $s.WorkingDirectory = $Root
    $s.IconLocation = "$(Join-Path $Here $Icon),0"
    $s.Description = $Description
    $s.Save()
    Write-Host "wrote $Path"
}

New-Shortcut $OpenLnk "`"$Launcher`"" "rewatchables.ico" "Open the Rewatchables site (starts its local dev server if it isn't running)"
New-Shortcut $StopLnk "`"$Launcher`" --stop" "rewatchables_stop.ico" "Stop the Rewatchables site's local dev server on port 8577"
