<#
.SYNOPSIS
  Prépare dans TON Outlook les notifications diplo_es. RIEN n'est envoyé :
  tu relis, puis tu envoies toi-même.

.DESCRIPTION
  1. git pull : récupère data/outbox.json (rempli par le workflow GitHub).
  2. Pour chaque notification pas encore traitée sur ce PC :
     - si Outlook classique est disponible : crée un BROUILLON (dossier Brouillons) ;
     - sinon (nouvel Outlook, Outlook web...) : génère une page locale avec, pour chaque
       notification, un lien qui ouvre un nouveau mail (destinataires + objet remplis)
       et un bouton "Copier le texte".
  3. Note ce qui a été traité dans .drafted_ids.txt (local, non versionné).

.PARAMETER NoPull
  Ne fait pas de git pull avant.
.PARAMETER Page
  Force la page HTML même si Outlook classique est disponible.
.PARAMETER Redo
  Ignore .drafted_ids.txt : recrée tout ce qui est dans l'outbox (30 derniers jours), SAUF ce qui
  figure dans deja_envoyes.csv. Demande confirmation. Pour refaire un seul mail : -Refaire "Nom".
.PARAMETER Depuis
  Ne prépare que les notifications mises en file dans les N derniers jours (ex. -Depuis 4).
  Le paramètre days_back du workflow ne règle que ce qui est LU dans le BOE ; l'outbox,
  elle, garde 30 jours de notifications, et ce script prépare tout ce qu'il n'a pas déjà traité.
.PARAMETER MarquerTraite
  Ne crée AUCUN brouillon : marque comme « déjà envoyées » toutes les notifications actuellement
  dans l'outbox (et les inscrit dans suivi_envois.csv). À utiliser une fois quand tu as déjà
  envoyé ces mails par un autre chemin et que le script ne le sait pas.
.PARAMETER Refaire
  Recrée UNIQUEMENT la ou les notifications dont le nom contient ce texte (ex. -Refaire "Poirier"),
  en ignorant les mémoires. Remplace l'usage de -Redo, qui est dangereux.
.PARAMETER Yes
  Mode page : marque directement les notifications comme traitées, sans poser la question.
#>
param(
    [switch]$NoPull,
    [switch]$Page,
    [switch]$Redo,
    [int]$Depuis = 0,
    [switch]$MarquerTraite,
    [string]$Refaire = "",
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

if (-not $NoPull) {
    Write-Host "== git pull ==" -ForegroundColor Cyan
    git pull --rebase
    if ($LASTEXITCODE -ne 0) { throw "git pull a échoué. Résous ça d'abord, ou relance avec -NoPull." }
}

$OutboxPath = Join-Path $Repo "data/outbox.json"
if (-not (Test-Path $OutboxPath)) {
    Write-Host "Pas de data/outbox.json : rien à préparer."
    exit 0
}

$parsed = Get-Content $OutboxPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @()
if ($null -ne $parsed) { $items = @($parsed) }

if ($Depuis -gt 0) {
    $limite = (Get-Date).Date.AddDays(-$Depuis)
    $avant = $items.Count
    $items = @($items | Where-Object {
        $d = $null
        try { $d = [datetime]::ParseExact([string]$_.created, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) } catch { }
        ($null -eq $d) -or ($d -ge $limite)
    })
    Write-Host "Option -Depuis $Depuis : $($avant - $items.Count) notification(s) plus ancienne(s) ignorée(s) (mises en file avant le $($limite.ToString('yyyy-MM-dd')))." -ForegroundColor Cyan
}

# --- Liste des mails DÉJÀ ENVOYÉS (deja_envoyes.csv : Nom;Evenement;...) ---
# Jamais re-préparés, même avec -Redo. Seul -Refaire "Nom" peut les refaire.
function Get-Key([string]$Name, [string]$Event) {
    $t = $Name.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', ''
    $t = ($t.ToLower() -replace '[^a-z0-9]+', ' ').Trim()
    return ($t + "|" + $Event.Trim().ToLower())
}
$EnvoyesFile = Join-Path $Repo "deja_envoyes.csv"
$envoyes = New-Object 'System.Collections.Generic.HashSet[string]'
if (Test-Path $EnvoyesFile) {
    try {
        foreach ($r in @(Import-Csv -Path $EnvoyesFile -Delimiter ";" -Encoding UTF8)) {
            if ($r.Nom) { [void]$envoyes.Add((Get-Key ([string]$r.Nom) ([string]$r.Evenement))) }
        }
    } catch { Write-Host "deja_envoyes.csv illisible : ignoré." -ForegroundColor Yellow }
}
if ($Refaire) {
    $items = @($items | Where-Object { $_.meta -and ([string]$_.meta.name) -like ("*" + $Refaire + "*") })
    $Redo = $true
    $envoyes.Clear()
    Write-Host "Option -Refaire '$Refaire' : $($items.Count) notification(s) concernée(s)." -ForegroundColor Cyan
} elseif ($envoyes.Count -gt 0) {
    $avant = $items.Count
    $items = @($items | Where-Object { -not ($_.meta -and $envoyes.Contains((Get-Key ([string]$_.meta.name) ([string]$_.meta.event)))) })
    Write-Host "deja_envoyes.csv : $($avant - $items.Count) notification(s) déjà envoyée(s) écartée(s)." -ForegroundColor Cyan
}
if (($Redo) -and (-not $Refaire) -and (-not $Yes)) {
    $ok = Read-Host "-Redo recrée tout l'outbox (sauf deja_envoyes.csv) : risque de doublons dans Brouillons. Continuer ? (o/N)"
    if ($ok -notmatch '^(o|oui|y|yes)$') { Write-Host "Annulé."; exit 0 }
}

$DoneFile = Join-Path $Repo ".drafted_ids.txt"
$done = New-Object 'System.Collections.Generic.HashSet[string]'
if ((Test-Path $DoneFile) -and (-not $Redo)) {
    foreach ($line in (Get-Content $DoneFile -Encoding UTF8)) {
        if ($line) { [void]$done.Add($line.Trim()) }
    }
}
# Deuxième mémoire : ce qui figure déjà dans suivi_envois.csv (colonne Id) compte comme traité,
# même si .drafted_ids.txt a été perdu (nouveau dossier, nouveau zip, autre PC...).
$TrackFile = Join-Path $Repo "suivi_envois.csv"
if ((Test-Path $TrackFile) -and (-not $Redo)) {
    try {
        foreach ($r in @(Import-Csv -Path $TrackFile -Delimiter ";" -Encoding UTF8)) {
            if ($r.Id) { [void]$done.Add(([string]$r.Id).Trim()) }
        }
    } catch { Write-Host "suivi_envois.csv illisible (ouvert dans Excel ?) : ignoré pour cette fois." -ForegroundColor Yellow }
}
$todo = @($items | Where-Object { -not $done.Contains([string]$_.id) })
$alreadyDone = $items.Count - $todo.Count
Write-Host "Outbox : $($items.Count) notification(s) au total, dont $alreadyDone déjà préparée(s) sur ce PC."

if ($todo.Count -eq 0) {
    if ($items.Count -eq 0) {
        Write-Host "L'outbox est VIDE : le workflow n'a rien mis en file d'attente." -ForegroundColor Yellow
        Write-Host "  Causes possibles : aucune nomination nouvelle (déjà dans data/seen.json), dry_run coché,"
        Write-Host "  ou run en échec (regarde l'étape 'Run' puis 'Vérifie...' dans GitHub Actions)."
    } else {
        Write-Host "Tout est déjà préparé sur ce PC (le script s'en souvient via .drafted_ids.txt)." -ForegroundColor Yellow
        Write-Host "  Pour recréer les brouillons : relance avec -Redo (ça refait toute l'outbox, 30 derniers jours)."
        Write-Host "  Attention : supprime d'abord les anciens brouillons d'Outlook, sinon tu auras des doublons."
    }
    exit 0
}
Write-Host "$($todo.Count) notification(s) à préparer."

function ConvertTo-Crlf([string]$Text) { return ($Text -replace "`r?`n", "`r`n") }
function Get-ToList($n, [string]$Sep) { return (@($n.to) -join $Sep) }
function Add-Done([string]$Id) { Add-Content -Path $DoneFile -Value $Id -Encoding UTF8 }

# --- Suivi : fichier suivi_envois.csv (s'ouvre dans Excel), local, jamais versionné ---
# Une ligne par notification préparée. Les colonnes "Envoyé le" et "Remarques" sont à toi :
# le script ne les écrase jamais, il ne fait qu'ajouter les nouvelles lignes (pas de doublon sur "Id").
$TrackPath = Join-Path $Repo "suivi_envois.csv"
$script:TrackRows = New-Object System.Collections.ArrayList
function Add-TrackRow($n, [string]$Statut) {
    $m = $n.meta
    $jid = ([string]$n.id -split ":")[0]
    $link = ""; if ($m -and $m.link) { $link = [string]$m.link }
    $ev = "Alerte BOE"
    $branch = "AGS Spain"
    [void]$script:TrackRows.Add([pscustomobject][ordered]@{
        "Prepare le"   = (Get-Date -Format "yyyy-MM-dd")
        "Evenement"    = $ev
        "Nom"          = $(if ($m) { [string]$m.name } else { "" })
        "Lieu"         = $(if ($m) { [string]$m.location } else { "" })
        "Branche AGS"  = $branch
        "Destinataires" = (Get-ToList $n ", ")
        "Objet"        = [string]$n.subject
        "Statut"       = $Statut
        "Envoye le"    = ""
        "Remarques"    = ""
        "Lien BOE"    = $link
        "Id"           = [string]$n.id
    })
}
function Save-Track {
    if ($script:TrackRows.Count -eq 0) { return }
    $existing = @()
    if (Test-Path $TrackPath) { $existing = @(Import-Csv -Path $TrackPath -Delimiter ";" -Encoding UTF8) }
    $ids = @{}; foreach ($e in $existing) { $ids[[string]$e.Id] = $true }
    $new = @($script:TrackRows | Where-Object { -not $ids.ContainsKey([string]$_.Id) })
    $all = @($existing) + $new
    try {
        $all | Export-Csv -Path $TrackPath -Delimiter ";" -Encoding UTF8 -NoTypeInformation
        Write-Host "Suivi : $($new.Count) ligne(s) ajoutée(s) dans $TrackPath ($($all.Count) au total)." -ForegroundColor Green
    } catch {
        $alt = Join-Path $Repo ("suivi_envois_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".csv")
        $new | Export-Csv -Path $alt -Delimiter ";" -Encoding UTF8 -NoTypeInformation
        Write-Host "suivi_envois.csv est ouvert dans Excel : ferme-le. Les nouvelles lignes sont dans $alt (à recopier)." -ForegroundColor Yellow
    }
}

# --- Rattrapage : marquer comme déjà envoyées, sans rien créer ---
if ($MarquerTraite) {
    foreach ($n in $todo) { Add-Done ([string]$n.id); Add-TrackRow $n "Déjà envoyé (marqué à la main)" }
    Save-Track
    Write-Host "OK : $($todo.Count) notification(s) marquée(s) comme déjà traitées. Aucun brouillon créé." -ForegroundColor Green
    exit 0
}

# --- Garde-fou : beaucoup de notifications d'un coup = probablement d'anciens mails déjà envoyés ---
if (($todo.Count -gt 15) -and (-not $Yes)) {
    Write-Host ""
    Write-Host "ATTENTION : $($todo.Count) notifications vont être préparées. Répartition par date de mise en file :" -ForegroundColor Yellow
    $todo | Group-Object { [string]$_.created } | Sort-Object Name | ForEach-Object { Write-Host ("  {0} : {1}" -f $_.Name, $_.Count) }
    Write-Host "  Si tu les as déjà envoyées : réponds N, puis lance avec -MarquerTraite (ou limite avec -Depuis 4)."
    $go = Read-Host "Préparer ces $($todo.Count) notifications quand même ? (o/N)"
    if ($go -notmatch '^(o|oui|y|yes)$') { Write-Host "Annulé, rien n'a été créé."; exit 0 }
}

# --- Voie 1 : Outlook classique (COM) -> brouillons ---
$outlook = $null
if (-not $Page) {
    try { $outlook = New-Object -ComObject Outlook.Application } catch { $outlook = $null }
}

if ($null -ne $outlook) {
    $count = 0
    foreach ($n in $todo) {
        $mail = $outlook.CreateItem(0)          # 0 = message
        $mail.To = Get-ToList $n ";"
        $mail.Subject = [string]$n.subject
        $mail.Body = ConvertTo-Crlf ([string]$n.body)
        $mail.Save()                            # Save = brouillon, PAS d'envoi
        Add-Done ([string]$n.id)
        Add-TrackRow $n "Brouillon créé"
        $count++
    }
    Save-Track
    Write-Host "OK : $count brouillon(s) créé(s) dans Outlook > Brouillons. Relis-les et envoie-les toi-même." -ForegroundColor Green
    exit 0
}

# --- Voie 2 : page locale (marche avec n'importe quel Outlook) ---
Write-Host "Outlook classique indisponible (ou -Page demandé) : je prépare une page à ouvrir dans le navigateur." -ForegroundColor Yellow

$css = 'body{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#222}' +
       '.card{border:1px solid #ccd;border-radius:8px;padding:12px 16px;margin:16px 0}' +
       'h2{font-size:16px;margin:0 0 8px}textarea{width:100%;height:260px;font-family:Consolas,monospace;font-size:13px}' +
       '.btn,button{display:inline-block;padding:6px 12px;border:1px solid #446;border-radius:6px;background:#eef;color:#113;text-decoration:none;font-size:14px;cursor:pointer}' +
       '.hint{color:#555}'
$js = 'function cp(id){var t=document.getElementById(id);t.select();t.setSelectionRange(0,99999);try{navigator.clipboard.writeText(t.value);}catch(e){document.execCommand("copy");}}'

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Alertes diplo_es</title><style>' + $css + '</style></head><body>')
[void]$sb.AppendLine('<h1>Alertes diplo_es (' + $todo.Count + ')</h1>')
[void]$sb.AppendLine('<p class="hint">Rien n''est envoyé depuis cette page. Pour chaque carte : « Ouvrir un nouveau mail » (destinataires et objet déjà remplis), puis « Copier le texte » et colle-le dans le mail. Relis, puis envoie toi-même.</p>')

$i = 0
foreach ($n in $todo) {
    $i++
    $toComma = Get-ToList $n ","
    $mailto = "mailto:" + $toComma + "?subject=" + [System.Uri]::EscapeDataString([string]$n.subject)
    $label = [string]$n.id
    if ($n.meta) { $label = "[" + $n.meta.event + "] " + $n.meta.name + " - " + $n.meta.location }
    [void]$sb.AppendLine('<div class="card">')
    [void]$sb.AppendLine('<h2>' + [System.Net.WebUtility]::HtmlEncode($label) + '</h2>')
    [void]$sb.AppendLine('<p><b>À :</b> ' + [System.Net.WebUtility]::HtmlEncode((Get-ToList $n ", ")) + '<br><b>Objet :</b> ' + [System.Net.WebUtility]::HtmlEncode([string]$n.subject) + '</p>')
    [void]$sb.AppendLine('<textarea readonly id="b' + $i + '">' + [System.Net.WebUtility]::HtmlEncode([string]$n.body) + '</textarea>')
    [void]$sb.AppendLine('<p><a class="btn" href="' + [System.Net.WebUtility]::HtmlEncode($mailto) + '">Ouvrir un nouveau mail</a> <button onclick="cp(''b' + $i + ''')">Copier le texte</button></p>')
    [void]$sb.AppendLine('</div>')
}
[void]$sb.AppendLine('<script>' + $js + '</script></body></html>')

$PagePath = Join-Path $Repo "data/notifications_du_jour.html"
[System.IO.File]::WriteAllText($PagePath, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Page prête : $PagePath"
if (($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows) { Start-Process $PagePath }

if ($Yes) { $ans = "o" } else { $ans = Read-Host "Une fois les mails envoyés : marquer ces $($todo.Count) notification(s) comme traitées ? (o/N)" }
if ($ans -match '^(o|oui|y|yes)$') {
    foreach ($n in $todo) { Add-Done ([string]$n.id); Add-TrackRow $n "Page ouverte, à envoyer" }
    Save-Track
    Write-Host "Marquées comme traitées."
} else {
    Write-Host "Non marquées : elles réapparaîtront au prochain lancement."
}
