# PowerShell helper: run the container with the sample CSV and save a local trace.
# Usage: .\scripts\podman_e2e.ps1
param(
    [string]$Question = "找出總營收最高的商品類別，並說明該類別在哪個地區營收最高。",
    [string]$Image = "data-analysis-agent:hw2"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    if (-not (Test-Path ".env")) {
        throw "找不到 .env，請先由 .env.example 建立並設定 OPENAI_API_KEY。"
    }
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    podman run --rm --env-file .env -v "${PWD}/logs:/app/logs" `
        $Image --csv data/sample_sales.csv --question $Question `
        --trace-file logs/openai_podman_trace.json
    $agentExit = $LASTEXITCODE
    if (Test-Path "logs/openai_podman_trace.json") {
        Write-Host "`n--- Container Trace Summary ---"
        & .\.venv\Scripts\python.exe scripts/trace_report.py logs/openai_podman_trace.json
    } else {
        Write-Warning "沒有找到 Trace。請檢查掛載權限並參考 README 的 podman cp 方案。"
    }
    exit $agentExit
} finally {
    Pop-Location
}
