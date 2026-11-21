# Builds portable --onedir Windows executables for microKeyboard Switcher & Hardware Flasher.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }

python -m PyInstaller --noconfirm --onedir --windowed `
    --name microKeyboard `
    --icon assets\microkeyboard.ico `
    --add-data "assets\microkeyboard.ico;assets" `
    --paths . `
    scripts\entry_switcher.py

python -m PyInstaller --noconfirm --onedir --windowed `
    --name microKeyboardFlasher `
    --icon assets\microkeyboard_flasher.ico `
    --add-data "assets\microkeyboard_flasher.ico;assets" `
    --paths . `
    scripts\entry_flasher.py

$pkgDir = Join-Path $root "dist\microKeyboard-v1.1.1-win64"
New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null
Move-Item "dist\microKeyboard" (Join-Path $pkgDir "microKeyboard")
Move-Item "dist\microKeyboardFlasher" (Join-Path $pkgDir "microKeyboardFlasher")

# Copy editable config/ alongside each .exe so settings persist
Copy-Item -Recurse -Force "config" (Join-Path $pkgDir "microKeyboard\config")
Copy-Item -Recurse -Force "config" (Join-Path $pkgDir "microKeyboardFlasher\config")
Copy-Item "README.md", "LICENSE" $pkgDir

$zipPath = Join-Path $root "dist\microKeyboard-v1.1.1-win64.zip"
Compress-Archive -Path "$pkgDir\*" -DestinationPath $zipPath -Force
Write-Host "Built: $zipPath"
