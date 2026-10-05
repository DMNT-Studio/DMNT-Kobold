# Baut DMNT-Kobold zum Ausliefern: EXE-Ordner (PyInstaller), Setup (Inno Setup),
# Portable-ZIP und SHA256SUMS.txt. Ergebnis in dist\.
#
# Lokal auf dem PC in PowerShell, im Repo-Ordner:
#   .\packaging\bauen.ps1                 alles
#   .\packaging\bauen.ps1 -OhneSetup      ohne Inno Setup (nur EXE-Ordner und ZIP)
# Auf GitHub ruft release.yml dasselbe Skript auf.
param([switch]$OhneSetup)

$ErrorActionPreference = "Stop"
$wurzel = Split-Path -Parent $PSScriptRoot
Set-Location $wurzel

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$version = & $python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or -not $version) { throw "Version aus pyproject.toml nicht lesbar" }
$zahlen = ($version -split "-")[0]
Write-Host "DMNT-Kobold $version bauen"

$vorhanden = & $python -c "import importlib.util;print(importlib.util.find_spec('PyInstaller') is not None)"
if ($vorhanden -ne "True") {
    Write-Host "PyInstaller fehlt, wird installiert"
    & $python -m pip install --quiet "pyinstaller>=6.16"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller-Installation fehlgeschlagen" }
}

# 1. EXE-Ordner
foreach ($alt in "dist", "build\pyinstaller", "build\portable") {
    if (Test-Path $alt) { Remove-Item $alt -Recurse -Force }
}
& $python -m PyInstaller packaging\kobold.spec --noconfirm --clean `
    --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }
$app = "dist\DMNT-Kobold"
if (-not (Test-Path "$app\DMNT-Kobold.exe")) { throw "DMNT-Kobold.exe fehlt im Build" }

# Sulfi (Minecraft-Figur) darf nie ausgeliefert werden
$verboten = Get-ChildItem $app -Recurse | Where-Object { $_.FullName -match "(?i)sulfi" }
if ($verboten) { throw "Sulfi-Dateien im Build gefunden: $($verboten[0].FullName)" }

# 2. Portable-ZIP: derselbe Ordner plus portable.txt (Daten liegen dann neben der EXE)
$portable = "build\portable\DMNT-Kobold"
New-Item -ItemType Directory -Force (Split-Path $portable) | Out-Null
Copy-Item $app $portable -Recurse
Set-Content "$portable\portable.txt" "Portable-Version: Die Daten liegen im Ordner 'daten' neben der EXE." -Encoding ascii
Compress-Archive -Path $portable -DestinationPath "dist\DMNT-Kobold-Portable.zip" -CompressionLevel Optimal

# 3. Setup
if (-not $OhneSetup) {
    $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } |
                 Select-Object -First 1
    }
    if (-not $iscc) { throw "Inno Setup 6 nicht gefunden (ISCC.exe). Installieren oder -OhneSetup benutzen." }
    & $iscc /Q "/DAppVersion=$version" "/DNumVersion=$zahlen" packaging\DMNT-Kobold.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup fehlgeschlagen" }
}

# 4. Prüfsummen (UTF-8 ohne BOM, Zeilenende LF)
$zeilen = Get-ChildItem dist -File | Where-Object { $_.Extension -in ".exe", ".zip" } | Sort-Object Name |
    ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name }
[IO.File]::WriteAllText((Join-Path $wurzel "dist\SHA256SUMS.txt"), (($zeilen -join "`n") + "`n"),
                        (New-Object Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Fertig: dist\" -ForegroundColor Green
Get-ChildItem dist -File | ForEach-Object { "  {0,-28} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }
