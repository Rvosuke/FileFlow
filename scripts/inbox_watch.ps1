param(
    [Parameter(Mandatory = $true)]
    [string]$InboxPath,

    [Parameter(Mandatory = $true)]
    [string]$StateDir,

    [int]$PollSeconds = 15
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

$logPath = Join-Path $StateDir "events.log"
$latestPath = Join-Path $StateDir "latest_tail.txt"
$pidPath = Join-Path $StateDir "watch.pid"

Set-Content -Path $pidPath -Value $PID -Encoding ascii

$lastWriteTicks = ""
if (Test-Path $InboxPath) {
    $lastWriteTicks = (Get-Item $InboxPath).LastWriteTimeUtc.Ticks
    Add-Content -Path $logPath -Value "[$(Get-Date -Format s)] watcher started: $InboxPath" -Encoding utf8
}

while ($true) {
    try {
        if (Test-Path $InboxPath) {
            $item = Get-Item $InboxPath
            $currentTicks = $item.LastWriteTimeUtc.Ticks

            if ($currentTicks -ne $lastWriteTicks) {
                $lastWriteTicks = $currentTicks
                $tail = Get-Content $InboxPath -Tail 30 -Encoding utf8
                $header = "[$(Get-Date -Format s)] inbox changed"
                Add-Content -Path $logPath -Value $header -Encoding utf8
                Add-Content -Path $logPath -Value ($tail -join [Environment]::NewLine) -Encoding utf8
                Add-Content -Path $logPath -Value "" -Encoding utf8
                Set-Content -Path $latestPath -Value ($tail -join [Environment]::NewLine) -Encoding utf8
            }
        }
    } catch {
        Add-Content -Path $logPath -Value "[$(Get-Date -Format s)] watcher error: $($_.Exception.Message)" -Encoding utf8
    }

    Start-Sleep -Seconds $PollSeconds
}
