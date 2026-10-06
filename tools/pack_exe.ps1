$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$versionFile = Join-Path $repo "tmdl_lens\version.py"
$match = Select-String -Path $versionFile -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $match) { throw "cannot read __version__ from tmdl_lens/version.py" }
$version = $match.Matches[0].Groups[1].Value
Write-Host ("version: " + $version)

$dist = Join-Path $repo "dist"
$bundle = Join-Path $dist "tmdl-lens"
$zipPath = Join-Path $dist ("tmdl-lens.v" + $version + ".zip")

Push-Location $repo
try {
    if (Test-Path -LiteralPath $bundle) { Remove-Item -LiteralPath $bundle -Recurse -Force }
    pyinstaller tmdl-lens.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed with exit code " + $LASTEXITCODE }
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath $zipPath -Force
} finally {
    Pop-Location
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName })
    $top = @($names | Where-Object { $_ -notmatch "\\" })
    $hasConfig = @($names | Where-Object { $_ -eq "config.json" }).Count -gt 0
    $hasExe = $names -contains "tmdl-lens.exe"
    Write-Host ("entries: " + $names.Count)
    Write-Host ("top level: " + ($top -join ", "))
    Write-Host ("config.json inside: " + $hasConfig)
    if ($hasConfig) { throw "the zip contains config.json and must not be published" }
    if (-not $hasExe) { throw "tmdl-lens.exe is missing from the zip" }
    Write-Host ("ok: " + $zipPath)
} finally {
    $zip.Dispose()
}