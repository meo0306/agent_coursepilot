param(
    [switch]$KeepVolume
)

$ErrorActionPreference = "Stop"
$project = "coursepilot_p12_gate"
$composeFiles = @(
    "-f", "compose.yaml",
    "-f", "compose.eval-data.yaml"
)
$composePrefix = @("--env-file", ".env.eval", "-p", $project) + $composeFiles

if (-not (Test-Path ".env.eval")) {
    throw ".env.eval is required for the isolated P12 PostgreSQL gate"
}

# Load only the process environment. Values are never printed or written to a
# tracked file; the checked-in .env.example remains secret-free.
Get-Content ".env.eval" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $name, $value = $line.Split("=", 2)
        Set-Item -Path ("Env:" + $name.Trim()) -Value $value
    }
}

$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = "55432"
$env:COURSEPILOT_RECOVERABLE_WORKFLOWS_ENABLED = "true"
$env:COURSEPILOT_P12_POSTGRES_GATE = "1"
$env:COURSEPILOT_CHECKPOINT_SCHEMA = "coursepilot_checkpoints"

docker compose @composePrefix up -d postgres
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker compose @composePrefix exec -T postgres pg_isready -U $env:POSTGRES_USER -d $env:POSTGRES_DB | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        throw "PostgreSQL did not become ready within 60 seconds"
    }
    $env:UV_CACHE_DIR = "D:\project\agent_coursepilot\tmp\uv-cache"
    $env:PYTHONPATH = "src"
    uv run python -m alembic upgrade head
    uv run python -m alembic downgrade 0016_coursepilot_runtime_foundation
    uv run python -m alembic upgrade head
    uv run pytest -q tests/coursepilot/runtime/test_p12_postgres_integration.py
    uv run python -m evaluation.p12_interrupt_recovery
}
finally {
    if ($KeepVolume) {
        docker compose @composePrefix stop postgres
    }
    else {
        docker compose @composePrefix down
    }
}
