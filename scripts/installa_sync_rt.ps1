# Installa sul PC del titolare la copia serale dei corrispettivi RT verso Drive.
#
# Via SUPPLEMENTARE: la primaria resta l'import degli XML (Documenti > Import o
# cartella unica). Il PC deve stare nella stessa rete del registratore.
#
# Uso (PowerShell, dalla cartella del repository):
#   powershell -ExecutionPolicy Bypass -File scripts\installa_sync_rt.ps1 `
#       -Inbox "G:\Il mio Drive\GESTIONALE\DATI SOCIETA CERALDI\DA ELABORARE"
#
# Crea l'attivita' pianificata «Ceraldi - RT verso Drive»: ogni sera alle 23:40
# e all'accensione del PC (recupera le giornate perse mentre era spento).
# Le variabili RT_LOCAL_BASE_URL e RT_DRIVE_INBOX restano sul PC: mai su Render.

param(
    [Parameter(Mandatory = $true)][string]$Inbox,
    [string]$RtUrl = "http://192.168.1.19/www/dati-rt/",
    [string]$Ora = "23:40",
    [string]$Dal = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\sync_rt_to_drive.py"
if (-not (Test-Path $script)) { throw "Non trovo $script" }
if (-not (Test-Path $Inbox)) { throw "La cartella $Inbox non esiste: Drive Desktop e' acceso?" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Python non e' installato su questo PC" }

[Environment]::SetEnvironmentVariable("RT_LOCAL_BASE_URL", $RtUrl, "User")
[Environment]::SetEnvironmentVariable("RT_DRIVE_INBOX", $Inbox, "User")
$env:RT_LOCAL_BASE_URL = $RtUrl
$env:RT_DRIVE_INBOX = $Inbox

Write-Host "Prova senza scrivere nulla (--preview)..."
$argsProva = @("`"$script`"", "--preview")
if ($Dal) { $argsProva += @("--dal", $Dal) }
& $python @argsProva
if ($LASTEXITCODE -ne 0) { throw "Il registratore $RtUrl non risponde da questo PC" }

$argomenti = "`"$script`""
if ($Dal) { $argomenti += " --dal $Dal" }
$azione = New-ScheduledTaskAction -Execute $python -Argument $argomenti -WorkingDirectory $repo
$trigger = @(
    (New-ScheduledTaskTrigger -Daily -At $Ora),
    (New-ScheduledTaskTrigger -AtLogOn)
)
$impostazioni = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Ceraldi - RT verso Drive" -Action $azione -Trigger $trigger `
    -Settings $impostazioni -Description "Copia le giornate RT non ancora copiate in DATI SOCIETA CERALDI\DA ELABORARE" -Force | Out-Null

Write-Host "Installato. Primo giro adesso..."
Start-ScheduledTask -TaskName "Ceraldi - RT verso Drive"
Write-Host "Fatto: i file arrivano in $Inbox e il gestionale li registra al prossimo giro della cartella unica."
