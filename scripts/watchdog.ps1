# 客服 Agent 服务：24 小时长驻的健康检查与自动重启
# 用法（手动）: powershell -ExecutionPolicy Bypass -File scripts\watchdog.ps1
# 用法（后台）: Start-Process powershell -ArgumentList '-NoProfile','-WindowStyle','Hidden','-File','<本文件绝对路径>' -WindowStyle Hidden
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$IntervalSec = 300,
    [string]$Url = "http://127.0.0.1:8099/health",
    [string]$Python = "D:\bangong\venv-w2\Scripts\python.exe",
    [int]$Port = 8099
)

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "watchdog.log"

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $log -Value $line -Encoding UTF8
}

function Test-Health {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Start-Service {
    Write-Log "健康检查失败，重启服务（端口 $Port）"
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { $conn | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } ; Start-Sleep -Seconds 2 }
    Start-Process -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port", "--log-level", "warning" `
        -WorkingDirectory $Root -WindowStyle Hidden
    Start-Sleep -Seconds 8
    if (Test-Health) { Write-Log "重启成功" } else { Write-Log "重启后仍不可用，等下一轮" }
}

Write-Log "看门狗启动：每 $IntervalSec 秒检查 $Url"
$fail = 0
while ($true) {
    if (Test-Health) {
        if ($fail -gt 0) { Write-Log "恢复（连续失败 $fail 次）" }
        $fail = 0
    } else {
        $fail++
        Write-Log "健康检查失败第 $fail 次"
        if ($fail -ge 2) { Start-Service; $fail = 0 }
    }
    Start-Sleep -Seconds $IntervalSec
}
