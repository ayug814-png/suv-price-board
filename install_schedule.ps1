# Registers a Windows scheduled task that rebuilds the price board every `refresh_minutes` (config.json)
# while you're signed in. Re-run it after moving the folder or changing the interval.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$taskName = "SUV Price Board"
$minutes = (Get-Content (Join-Path $root "config.json") -Raw | ConvertFrom-Json).refresh_minutes

# pythonw.exe runs without flashing a console window every 15 minutes.
function Find-Pythonw {
    foreach ($launcher in @("py", "python")) {
        try {
            $exe = & $launcher -c "import sys; print(sys.executable)" | Select-Object -First 1
            if ($exe) {
                $candidate = Join-Path (Split-Path $exe.Trim()) "pythonw.exe"
                if (Test-Path $candidate) { return $candidate }
            }
        } catch {}
    }
    $installed = Get-ChildItem "$env:LOCALAPPDATA\Python\pythoncore-*\pythonw.exe", "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe" `
        -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    if ($installed) { return $installed[0].FullName }
    throw "Couldn't find pythonw.exe. Install Python 3.11 or newer and run this script again."
}
$pythonw = Find-Pythonw

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$(Join-Path $root 'run.py')`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $minutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes ($minutes - 1))
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Scans AutoTrader.ca, CarGurus.ca, Kijiji and Carpages.ca and rebuilds $root\board.html" -Force | Out-Null
"Scheduled '$taskName' every $minutes minutes using $pythonw"
"Board: $(Join-Path $root 'board.html')"
