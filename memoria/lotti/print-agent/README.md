# Lotti — Print Agent locale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Stampa **automatica** dei documenti di Lotti sulla stampante giusta, per categoria
(etichette → stampante etichette, ricette/manuale → stampante ufficio), senza
finestra di stampa.

## Perché serve
Il browser non può scegliere la stampante da solo e il backend (cloud, Render)
non raggiunge le stampanti della tua rete locale. L'agente gira sul **PC del
negozio**, preleva i lavori dalla coda dell'app e li manda alla stampante Windows
mappata a quella categoria.

## Come funziona
1. Nell'app → **Impostazioni → Stampanti**: per ogni stampante imposti
   - i **tipi di documento** che gestisce (Etichette, Ricette, Manuale, …);
   - il **nome esatto della stampante in Windows** (es. `EPSON ET-5170 Series`).
2. Quando stampi dall'app, il documento entra in una **coda**.
3. Questo agente, in ascolto, lo preleva e lo stampa sulla stampante giusta.

## Installazione (Windows)
1. Installa **Python 3.9+** (https://python.org) e **SumatraPDF**
   (https://www.sumatrapdfreader.org) — serve per la stampa silenziosa dei PDF.
   Metti `SumatraPDF.exe` nel PATH, oppure indica il percorso in `agent_config.json`.
   (Per i documenti HTML serve anche Google Chrome o Edge, di solito già presenti.)
2. Copia `agent_config.example.json` in **`agent_config.json`** e compila:
   - `backend_url`: l'indirizzo del backend (già impostato di default);
   - `pin`: il PIN di un operatore dedicato (creane uno "Stampa" in Impostazioni →
     Personale). L'agente usa quel PIN per autenticarsi;
   - `reparto`: lascia vuoto per stampare tutto, oppure `rosticceria` / `pasticceria`
     se il PC serve un solo reparto;
   - `sumatra_path`: percorso di SumatraPDF.exe se non è nel PATH;
   - `stampante_default`: stampante da usare se un documento non ha mappatura.
3. Avvia: apri il Prompt dei comandi nella cartella e lancia
   ```
   python agent.py
   ```
   Lascia la finestra aperta. (Per avvio automatico all'accensione, crea un
   collegamento in `shell:startup` oppure un'attività in Utilità di pianificazione.)

## Sicurezza
L'agente si autentica col **PIN operatore** (stesso meccanismo del tablet): riceve
un token firmato e lo rinnova da solo. Nessuna credenziale in chiaro nel codice,
nessun endpoint reso pubblico.

## Verifica
Stampa qualcosa dall'app: nella finestra dell'agente vedrai
`→ stampo '…' su '…'` e `[OK] stampato`. In **Impostazioni → Stampanti** lo
storico coda (`GET /api/stampanti/coda`) mostra l'esito di ogni lavoro.
