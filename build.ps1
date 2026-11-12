$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name MiceArrow `
    --specpath "$PSScriptRoot\build" `
    --icon "$PSScriptRoot\ICON-MiceArrow.ico" `
    --add-data "$PSScriptRoot\Pointers;Pointers" `
    --distpath "$PSScriptRoot\dist" `
    --workpath "$PSScriptRoot\build" `
    "$PSScriptRoot\mice_arrow.py"
