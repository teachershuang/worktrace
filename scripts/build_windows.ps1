param(
    [switch]$Clean,
    [switch]$ReuseCurrentPython
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($ReuseCurrentPython) {
    $Python = "python"
} else {
    $VenvDir = Join-Path $Root ".venv-build"
    $Python = Join-Path $VenvDir "Scripts\python.exe"
    if (!(Test-Path -LiteralPath $Python)) {
        python -m venv $VenvDir
    }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt -r requirements-build.txt

$pyinstallerArgs = @("worktrace.spec", "--noconfirm")
if ($Clean) {
    $pyinstallerArgs += "--clean"
}

& $Python -m PyInstaller @pyinstallerArgs

$distDir = Join-Path $Root "dist\WorkTrace"
Copy-Item -LiteralPath (Join-Path $Root "config.example.yaml") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $Root "config.lan.example.yaml") -Destination $distDir -Force

Write-Host "WorkTrace build written to $distDir"
Write-Host "Run: $distDir\WorkTrace.exe config-show --config config.example.yaml"
