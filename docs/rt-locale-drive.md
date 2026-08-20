# Acquisizione serale RT locale

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Render non puo raggiungere `192.168.1.19`, perche e un indirizzo della rete privata del locale.
Il raccoglitore deve girare su un PC collegato alla stessa LAN e deve solo trasferire i file
originali nella cartella Drive `Corrispettivi/Da elaborare`.

Variabili locali, mai da inserire su Render:

- `RT_LOCAL_BASE_URL=http://192.168.1.19/www/dati-rt/`
- `RT_DRIVE_INBOX=C:\...\Il mio Drive\GESTIONALE\Corrispettivi\Da elaborare`
- facoltativa `RT_SYNC_STATE_FILE`, se si desidera spostare il registro degli hash

Esecuzione di prova:

```powershell
python scripts\sync_rt_to_drive.py --preview
```

Esecuzione reale:

```powershell
python scripts\sync_rt_to_drive.py
```

Lo script seleziona la cartella giornaliera piu recente, ignora gli XML `ESITO`, calcola SHA-256
e copia atomicamente solo i file nuovi. La pipeline Drive del gestionale esegue parsing e seconda
deduplica, poi sposta i documenti in `Elaborate` o `Errori`.

Per l'esecuzione ogni sera usare Utilita di pianificazione di Windows sul PC del locale. Le
credenziali MongoDB e Google non servono allo script: Google Drive Desktop sincronizza la cartella.
