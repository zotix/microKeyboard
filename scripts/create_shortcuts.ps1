# Generates local Windows shortcuts (.lnk) pointing to this repository and pythonw.exe.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pyw = (Get-Command pythonw.exe).Source
$ws = New-Object -ComObject WScript.Shell

$shortcuts = @(
    @{
        Name = "microKeyboard GUI.lnk"
        Args = "-m microkeyboard.gui"
        Icon = Join-Path $root "assets\microkeyboard.ico"
        Desc = "microKeyboard Switcher"
    },
    @{
        Name = "microKeyboard Tray.lnk"
        Args = "-m microkeyboard.gui --minimized"
        Icon = Join-Path $root "assets\microkeyboard.ico"
        Desc = "microKeyboard Switcher (System Tray)"
    },
    @{
        Name = "microKeyboard Flasher.lnk"
        Args = "-m microkeyboard.flash_gui"
        Icon = Join-Path $root "assets\microkeyboard_flasher.ico"
        Desc = "microKeyboard Hardware Flasher"
    }
)

foreach ($sc in $shortcuts) {
    $path = Join-Path $root $sc.Name
    $lnk = $ws.CreateShortcut($path)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = $sc.Args
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$($sc.Icon),0"
    $lnk.Description = $sc.Desc
    $lnk.Save()
    Write-Host "Created $path"
}
