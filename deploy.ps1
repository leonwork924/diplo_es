# deploy.ps1
#
# Se place automatiquement dans SON PROPRE dossier (celui où ce fichier vit),
# peu importe d'où tu le lances -- pas de chemin codé en dur cette fois,
# donc ça marche même si tu clones ce repo ailleurs que tender-radar.
#
# Usage :
#   .\deploy.ps1 -Zip "chemin\vers\nouveau.zip" -Message "mon message"
#   .\deploy.ps1 -Message "mon message"   (sans zip, commit ce qui est déjà là)

param(
    [string]$Zip,
    [string]$Message = "Update from Claude"
)

$ErrorActionPreference = "Stop"

$RepoPath = $PSScriptRoot
Set-Location $RepoPath
Write-Host "== Dossier actif : $(Get-Location) ==" -ForegroundColor DarkGray

if (-not (Test-Path ".git")) {
    Write-Error "$RepoPath n'est pas un repo git. Ce script doit rester à la racine du repo diplo_es."
    exit 1
}

Write-Host "== git fetch + rebase ==" -ForegroundColor Cyan
git fetch origin
git rebase origin/main

if ($Zip) {
    if (-not (Test-Path $Zip)) {
        Write-Error "Zip introuvable : $Zip"
        exit 1
    }
    Write-Host "== Extraction directe de $Zip sur $RepoPath ==" -ForegroundColor Cyan
    Expand-Archive -Path $Zip -DestinationPath $RepoPath -Force
}

Write-Host "== git status ==" -ForegroundColor Cyan
git status --short

$changes = git status --porcelain
if (-not $changes) {
    Write-Host "Rien à commiter." -ForegroundColor Yellow
    exit 0
}

git add -A
git commit -m $Message

$maxAttempts = 5
for ($i = 1; $i -le $maxAttempts; $i++) {
    Write-Host "== git push (tentative $i/$maxAttempts) ==" -ForegroundColor Cyan
    git push
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Poussé avec succès." -ForegroundColor Green
        exit 0
    }
    Write-Host "Push rejeté -- rebase et nouvel essai." -ForegroundColor Yellow
    git fetch origin
    git rebase origin/main -X ours
    Start-Sleep -Seconds 3
}

Write-Error "Échec après $maxAttempts tentatives."
exit 1
