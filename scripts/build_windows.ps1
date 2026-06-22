param(
    [switch]$Clean,
    [switch]$ReuseCurrentPython
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

if ($ReuseCurrentPython) {
    $Python = "python"
} else {
    $VenvDir = Join-Path $Root ".venv-build"
    $Python = Join-Path $VenvDir "Scripts\python.exe"
    if (!(Test-Path -LiteralPath $Python)) {
        python -m venv $VenvDir
    }
}

Invoke-Checked $Python @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-build.txt")

$pyinstallerArgs = @("worktrace.spec", "--noconfirm")
if ($Clean) {
    $pyinstallerArgs += "--clean"
}

Invoke-Checked $Python (@("-m", "PyInstaller") + $pyinstallerArgs)

$distDir = Join-Path $Root "dist\WorkTrace"
Copy-Item -LiteralPath (Join-Path $Root "config.example.yaml") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $Root "config.lan.example.yaml") -Destination $distDir -Force

Write-Host "WorkTrace build written to $distDir"
Write-Host "Desktop app: $distDir\WorkTrace.exe"
Write-Host "CLI tools:    $distDir\WorkTrace-cli.exe config-show --config config.example.yaml"
