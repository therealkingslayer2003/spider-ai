# Windows PowerShell pre-push hook
# Installation: Copy this file to .git/hooks/pre-push (no extension on Windows)

Write-Host "🔍 Running pre-push format check..." -ForegroundColor Cyan

# Run format check
uv run ruff format --check app/ tests/

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Format check failed. Please run 'uv run ruff format app/ tests/' to fix formatting." -ForegroundColor Red
    Write-Host "Then stage and push again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "✅ Format check passed. Proceeding with push." -ForegroundColor Green
exit 0
