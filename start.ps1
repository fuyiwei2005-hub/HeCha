param([int]$Port = 8000, [switch]$ApiOnly, [switch]$Redis)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '先执行 python -m venv .venv，然后用 .venv\Scripts\python.exe -m pip install -r backend\requirements.txt 安装依赖。'
}
$serverArgs = @((Join-Path $projectRoot 'tools\dev_server.py'), '--port', "$Port")
if ($ApiOnly) { $serverArgs += '--api-only' }
if ($Redis) { $serverArgs += '--redis' }
$env:PESTGUARD_OPEN_BROWSER = '1'
& $pythonPath @serverArgs
exit $LASTEXITCODE
