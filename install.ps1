# Installs the safedata command for the current user (Windows):
# uv first if it is missing, then safedata as a uv tool. No administrator rights needed.
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.ps1 | iex"
#
# Running it again upgrades safedata. Set SAFEDATA_SOURCE to install from
# somewhere else (a local folder, a fork, a tag: git+https://...@v1.0.0).
$ErrorActionPreference = "Stop"

$source = if ($env:SAFEDATA_SOURCE) { $env:SAFEDATA_SOURCE } else { "git+https://github.com/BalzaniEdoardo/safedata" }

function Fail($message) {
    Write-Host "error: $message" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is not installed. Install it from https://git-scm.com and run this again."
}

# uv: use the one on PATH, or one installed earlier in its default folder, or install it.
$uvBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path (Join-Path $uvBin "uv.exe"))) {
        Write-Host "Installing uv (https://docs.astral.sh/uv/) ..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        if ($LASTEXITCODE -ne 0) { Fail "the uv installer failed." }
    }
    $env:Path = "$uvBin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv was installed but cannot be found. Open a new terminal and run this again."
}

Write-Host "Installing safedata from $source ..."
uv tool install --force $source
if ($LASTEXITCODE -ne 0) { Fail "uv could not install safedata." }

# Make sure the folder with the safedata command is on PATH in new terminals.
uv tool update-shell
if ($LASTEXITCODE -ne 0) { Fail "uv could not add the tools folder to PATH." }

$bin = (uv tool dir --bin).Trim()
& (Join-Path $bin "safedata.exe") --help > $null
if ($LASTEXITCODE -ne 0) { Fail "safedata was installed in $bin but does not run." }

Write-Host ""
Write-Host "safedata is installed in $bin."
Write-Host "Open a new terminal, then in a clone of your dataset repository run:  safedata install"
