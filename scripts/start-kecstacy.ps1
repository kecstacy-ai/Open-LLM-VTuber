# Launch Open-LLM-VTuber server with CUDA 12 / cuDNN 9 DLLs from the venv on PATH.
# OPENROUTER_API_KEY is read from the user environment (never stored in the repo).
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
if (-not $env:OPENROUTER_API_KEY) { $env:OPENROUTER_API_KEY = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User') }
if (-not $env:OPENROUTER_API_KEY) { Write-Error 'OPENROUTER_API_KEY not set. Run: setx OPENROUTER_API_KEY "sk-or-..."'; exit 1 }
$repo = Split-Path $PSScriptRoot -Parent
$nv = Join-Path $repo '.venv\Lib\site-packages\nvidia'
$env:Path = (Join-Path $nv 'cublas\bin') + ';' + (Join-Path $nv 'cudnn\bin') + ';' + $env:Path
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $repo
uv run run_server.py @args
