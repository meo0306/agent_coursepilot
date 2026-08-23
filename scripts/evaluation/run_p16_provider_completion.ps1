param(
    [DateTimeOffset]$NotBefore = [DateTimeOffset]::Parse("2026-08-21T12:10:00+08:00")
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$outputDirectory = Join-Path $repositoryRoot "storage_eval\p16_provider_completion"
$statusPath = Join-Path $outputDirectory "scheduled_status.json"
$providerLog = Join-Path $outputDirectory "provider.log"
$renderLog = Join-Path $outputDirectory "render.log"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

function Write-CompletionStatus {
    param(
        [string]$Status,
        [int]$ProviderExitCode = -1,
        [int]$RenderExitCode = -1,
        [string]$ErrorMessage = ""
    )
    $payload = [ordered]@{
        status = $Status
        updated_at = [DateTimeOffset]::Now.ToString("o")
        not_before = $NotBefore.ToString("o")
        provider_exit_code = $ProviderExitCode
        render_exit_code = $RenderExitCode
        error = $ErrorMessage
    }
    $temporary = "$statusPath.tmp"
    $payload | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $temporary
    Move-Item -Force -Path $temporary -Destination $statusPath
}

Push-Location $repositoryRoot
try {
    Write-CompletionStatus -Status "waiting_for_not_before"
    while ([DateTimeOffset]::Now -lt $NotBefore) {
        Start-Sleep -Seconds 30
    }

    $env:PYTHONPATH = "src"
    $env:COURSEPILOT_GENERATION_MODE = "llm"
    $env:COURSEPILOT_MODEL_GATEWAY_MODE = "evaluation"
    $env:COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK = "true"
    $env:COURSEPILOT_LLM_MAX_RETRIES = "0"
    $env:COURSEPILOT_MODEL_PROFILE_PATH = "resources/model_profiles/p16_provider_completion_v1.yaml"

    Write-CompletionStatus -Status "provider_running"
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & ".\.venv\Scripts\python.exe" -m evaluation.p16_provider_completion `
        --output-dir storage_eval/p16_provider_completion `
        --external-data-authorized 1>> $providerLog 2>> $providerLog
    $providerExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($providerExitCode -ne 0) {
        Write-CompletionStatus -Status "provider_failed" -ProviderExitCode $providerExitCode
        exit $providerExitCode
    }

    Write-CompletionStatus -Status "render_running" -ProviderExitCode 0
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker compose -f compose.eval-pptx.yaml run --rm p16-pptx-qa `
        python -m evaluation.p16_closure `
        --output-dir storage_eval/p16_provider_completion_closure `
        --r3-report storage_eval/p16_provider_completion/report.json `
        1>> $renderLog 2>> $renderLog
    $renderExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($renderExitCode -ne 0) {
        Write-CompletionStatus -Status "render_failed" -ProviderExitCode 0 `
            -RenderExitCode $renderExitCode
        exit $renderExitCode
    }

    Write-CompletionStatus -Status "completed" -ProviderExitCode 0 -RenderExitCode 0
    Write-Output "P16_PROVIDER_COMPLETION_AND_RENDER_COMPLETED"
}
catch {
    Write-CompletionStatus -Status "failed" -ErrorMessage $_.Exception.Message
    throw
}
finally {
    Pop-Location
}
