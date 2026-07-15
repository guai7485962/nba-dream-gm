param(
  [switch]$Serve,
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$PortablePython = Join-Path $Root '..\..\.tools\python-3.12.10\python.exe'
$Candidates = @(
  @{ Exe = $PortablePython; Prefix = @() },
  @{ Exe = 'py'; Prefix = @('-3') },
  @{ Exe = 'python'; Prefix = @() }
)

$Python = $null
foreach ($Candidate in $Candidates) {
  try {
    $Version = & $Candidate.Exe @($Candidate.Prefix) --version 2>&1
    if ($LASTEXITCODE -eq 0) {
      $Python = $Candidate
      break
    }
  } catch {}
}

if (-not $Python) {
  throw 'Python 3 was not found. Install Python 3.10+, or provide .tools/python-3.12.10/python.exe in the workspace.'
}

Push-Location $Root
try {
  Write-Host "Using $Version"
  & $Python.Exe @($Python.Prefix) build_static.py
  if ($LASTEXITCODE -ne 0) { throw 'build_static.py failed.' }

  node -e "const fs=require('fs');const h=fs.readFileSync('static/index.html','utf8');const s=h.slice(h.indexOf('<script>')+8,h.lastIndexOf('</script>'));new Function(s);console.log('JavaScript syntax OK');"
  if ($LASTEXITCODE -ne 0) { throw 'JavaScript syntax check failed.' }

  if ($Serve) {
    Write-Host "Local preview: http://127.0.0.1:$Port/"
    Write-Host 'Press Ctrl+C to stop the server.'
    & $Python.Exe @($Python.Prefix) -m http.server $Port --bind 127.0.0.1 --directory dist
  } else {
    Write-Host 'Verification complete. Preview with: powershell -ExecutionPolicy Bypass -File .\verify.ps1 -Serve'
  }
} finally {
  Pop-Location
}
