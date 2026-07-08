<#
.SYNOPSIS
    Run the botamusique Docker image locally using wslc (WSL container CLI),
    without needing Docker Desktop.

.DESCRIPTION
    Equivalent of a `docker run` invocation (compose is not yet implemented for
    this project, so this script covers the same ground by hand):
      - mounts ./configuration.ini read-only into the container
      - mounts ./music_folder for the music library
      - mounts ./data for the settings/music SQLite databases (survives restarts)
      - publishes the web interface port (default 8181)

    Requires wslc (https://github.com/MicrosoftDocs/wsl/blob/main/WSL/wsl-container.md)
    and an image already built with wslc-build.ps1.

.PARAMETER Tag
    Image tag to run. Defaults to "botamusique:local".

.PARAMETER ConfigPath
    Path to configuration.ini on the host. Defaults to ./configuration.ini.

.PARAMETER MusicFolder
    Path to the music library folder on the host. Defaults to ./music_folder.

.PARAMETER DataDir
    Path to a folder on the host for persisting the settings/music SQLite databases.
    Defaults to ./data.

.PARAMETER WebPort
    Host port to publish the web interface on. Defaults to 8181.

.PARAMETER Detach
    Run the container in the background instead of attaching to it.

.EXAMPLE
    ./wslc-run.ps1
    ./wslc-run.ps1 -Detach -WebPort 8080
#>
param(
    [string]$Tag = "botamusique:local",
    [string]$ConfigPath = "./configuration.ini",
    [string]$MusicFolder = "./music_folder",
    [string]$DataDir = "./data",
    [int]$WebPort = 8181,
    [switch]$Detach
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$configPath = Resolve-Path (Join-Path $repoRoot $ConfigPath) -ErrorAction Stop

$musicFolder = Join-Path $repoRoot $MusicFolder
New-Item -ItemType Directory -Force -Path $musicFolder | Out-Null
$musicFolder = Resolve-Path $musicFolder

$dataDir = Join-Path $repoRoot $DataDir
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$dataDir = Resolve-Path $dataDir

$runArgs = @(
    "run"
    "--name", "botamusique"
    "-p", "${WebPort}:8181"
    "-v", "${configPath}:/botamusique/configuration.ini:ro"
    "-v", "${musicFolder}:/botamusique/music_folder"
    "-v", "${dataDir}:/botamusique/data"
)

if ($Detach) {
    $runArgs += "-d"
} else {
    $runArgs += @("--rm", "-it")
}

$runArgs += @(
    $Tag
    "uv", "run", "--locked", "--no-dev", "--no-sync", "botamusique"
    "--config", "configuration.ini"
    "--db", "data/settings.db"
    "--music-db", "data/music.db"
)

Write-Host "Running $Tag with wslc (web interface on http://127.0.0.1:$WebPort)..." -ForegroundColor Cyan

& wslc @runArgs

if ($LASTEXITCODE -ne 0 -and -not $Detach) {
    throw "wslc run failed with exit code $LASTEXITCODE"
}
