<#
.SYNOPSIS
    Build the botamusique Docker image locally using wslc (WSL container CLI),
    without needing Docker Desktop.

.DESCRIPTION
    Equivalent of: docker build --build-arg GIT_COMMIT=<short-sha> -t botamusique:local .
    Requires wslc (https://github.com/MicrosoftDocs/wsl/blob/main/WSL/wsl-container.md).

.PARAMETER Tag
    Image tag to build. Defaults to "botamusique:local".

.EXAMPLE
    ./wslc-build.ps1
    ./wslc-build.ps1 -Tag botamusique:dev
#>
param(
    [string]$Tag = "botamusique:local"
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$gitCommit = (git -C $repoRoot rev-parse --short HEAD).Trim()

Write-Host "Building $Tag (GIT_COMMIT=$gitCommit) with wslc..." -ForegroundColor Cyan

wslc build --build-arg "GIT_COMMIT=$gitCommit" -t $Tag $repoRoot

if ($LASTEXITCODE -ne 0) {
    throw "wslc build failed with exit code $LASTEXITCODE"
}

Write-Host "Built image: $Tag" -ForegroundColor Green
