# Starts the local web demo: Neo4j in its own window, the API with the local Gemma 4
# model through Ollama, and the page at http://127.0.0.1:8000 in the default browser.
#   powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
# Ctrl+C stops the API; closing the Neo4j window stops the database.
param([int]$Port = 8000, [string]$Model = 'medkg-gemma4-26b')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

function Listening([int]$p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }
function OursOn([int]$p) {
    # True when this project's Neo4j installation already listens on the port.
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { return $false }
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)").CommandLine
    return [bool]($cmd -match 'neo4j-community')
}

try { $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 }
catch { throw 'Ollama is not running: open the Ollama app, then run this script again.' }
if (-not ($tags.models.name -contains "$Model`:latest")) { throw "Ollama has no model '$Model'." }
# Load the model before the first question: a cold load takes longer than a request may.
Write-Host "Loading $Model (up to a minute the first time)..."
Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -TimeoutSec 300 -ContentType 'application/json' `
    -Body (@{ model = $Model; keep_alive = '30m' } | ConvertTo-Json) | Out-Null
if (Listening $Port) { throw "Port $Port is in use; pass -Port with another one." }

# This project's Neo4j on 7687, or on 7688 when another Neo4j holds 7687.
if (OursOn 7687) { $bolt = 7687 }
elseif (OursOn 7688) { $bolt = 7688 }
else {
    $bolt = if (Listening 7687) { 7688 } else { 7687 }
    Write-Host "Starting Neo4j on port $bolt in its own window..."
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$repo\scripts\start_neo4j.ps1`"", '-BoltPort', $bolt)
    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Listening $bolt)) {
        if ((Get-Date) -gt $deadline) { throw 'Neo4j did not start; see its window.' }
        Start-Sleep -Seconds 2
    }
}

$env:NEO4J_URI = "bolt://127.0.0.1:$bolt"
$env:LLM_BASE_URL = 'http://127.0.0.1:11434/v1'
$env:LLM_API_KEY = 'ollama'
$env:LLM_MODEL = $Model
$env:LLM_THINKING_PARAM = 'reasoning_effort'
$env:LLM_COOLDOWN_S = '0'
# Ollama unloads an idle model after a few minutes; reloading it must not time out.
$env:LLM_TIMEOUT = '180'
$env:PYTHONIOENCODING = 'utf-8'

# Open the page once the API answers.
$url = "http://127.0.0.1:$Port"
Start-Job -ArgumentList $url -ScriptBlock {
    param($u)
    for ($i = 0; $i -lt 180; $i++) {
        try { Invoke-RestMethod "$u/ready" -TimeoutSec 2 | Out-Null; Start-Process $u; return }
        catch { Start-Sleep -Seconds 1 }
    }
} | Out-Null
Write-Host "Web demo: $url  (Neo4j on $bolt, model $Model). Ctrl+C stops the API."
& "$repo\.venv\Scripts\python.exe" -m uvicorn medkg.api.app:app --host 127.0.0.1 --port $Port
