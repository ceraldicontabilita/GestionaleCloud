# Verifica di conformità — Sottosistema Documenti

_Loop /goal, 13/07/2026. Sola lettura per l'analisi; corretto solo il residuo
HACCP `scheda_tecnica` (già autorizzato). Contro `LOGICA_FUNZIONAMENTO.md`
(§2, §7, §13, §14), `CLAUDE.md`, `INDEX.md`._

**Esito**: 2 P0 (F24 email in collection sbagliata → "persi"; allegati email non
scaricabili dal link generico), 5 P1, vari P2. Il residuo HACCP è stato rimosso
in questo commit.

## Tabella area → stato → evidenza

| # | Area | Stato | Evidenza |
|---|------|-------|----------|
| 1 | Tassonomia tipi documento | DUBBIO (4 tassonomie parallele) | `email_full_download.py:36-49`; `drive_documenti_ingest.py:27-46`; `documenti_fiscali.py:28-32`; `documents_inbox_classify.py:33-54` |
| 1b | Residuo `scheda_tecnica` (HACCP) | RISOLTO in questo commit | `email_document_downloader.py:38,68-75` (rimossi) |
| 2 | Canali Drive on/off | CONFORME | `config.py:140-150` |
| 2b | F24/Verbali email (§13 = spento) | NON CONFORME | `scheduler.py:396-415,683-690`; `post_download_pipeline.py:653-672` |
| 3 | Frequenze scansione | DUBBIO (parametrico) | `scheduler.py:554-601,615-673` |
| 4 | Mittenti attendibili | DUBBIO (2 collection) | `documenti_non_associati.py:97` vs `verbali_gmail_scanner.py:59` |
| 5 | Dedup per impronta | CONFORME (con lacuna cross-canale) | `email_full_download.py:285-312`; `drive_documenti_ingest.py:126-131` |
| 6 | Associazione documento→entità | CONFORME | `documenti_non_associati.py:322-408` |
| 7 | Download/visualizzazione | NON CONFORME | `documenti.py:386-414` (solo `documents_inbox`) |

## P0
- **P0-1 — F24 email instradato alla collection sbagliata.** `processa_f24_da_email`
  salva in `f24_commercialista` (`post_download_pipeline.py:103`); `documenti.py:440`
  mappa "f24" a `f24_commercialista`; il classificatore inbox usa `f24_tributi`
  (`documents_inbox_classify.py:11`). Canonica è `f24_unificato` (CLAUDE.md, §7).
  Un F24 arrivato via email **non compare** nel modulo F24 principale → "perso"
  per l'utente. Aggravato dal fatto che il canale F24 email dovrebbe essere spento.
- **P0-2 (rischio) — Allegati email non scaricabili dal link generico.**
  `GET /documento/{id}/download` cerca solo in `documents_inbox`
  (`documenti.py:392`); gli allegati email vivono in `*_email_attachments` →
  il "Vai a"/download restituisce 404 per quei documenti.

## P1
- **P1-1 — Canali F24 email e Verbali email attivi nel codice ma "Spento" nel
  documento** (§13, §7). Nessun interruttore: girano ogni ora se ci sono
  credenziali IMAP (`connect()` non verifica `ENABLE_GMAIL_IMAP`,
  `config.py:167=False`). Serve un flag `ENABLE_*` che rispetti lo stato dichiarato,
  o aggiornare il documento. **[Parametro/canale → scelta utente]**
- **P1-2 — Residuo HACCP `scheda_tecnica`**: RIMOSSO in questo commit
  (`email_document_downloader.py`, `email_full_download.py`).
- **P1-3 — Nuovi canali Drive fiscali** (dichiarazione IVA/cartelle/avvisi) assenti
  dalla tabella §2/§13 del documento (presenti in `drive_documenti_ingest.py:27-46`,
  spenti di default). Aggiungerli al documento come "spento (in attesa cartelle)".
- **P1-4 — Frammentazione tassonomia/collection**: stesso tipo instradato in
  collection diverse per canale. Serve mappa unica tipo→collection da
  `db_collections.py`.
- **P1-5 — Divergenza frequenza Fatture Drive**: doc §2 "ogni ora" vs codice "ogni
  15 min" (`scheduler.py:556`, commento "scelta utente 10/07"). Allineare il
  documento (valore parametrico, non modificare). **[Scelta utente]**

## P2 — robustezza
- P2-1 dedup non incrociata tra `*_email_attachments` e `documents_inbox`
  (possibile doppione cross-canale a parità di impronta).
- P2-2 due collection mittenti (`mittenti_email` vs `mittenti_attendibili`).
- P2-3 campi tassonomia ridondanti (`category`/`categoria`/`tipo_documento`).
- P2-4 `gmail_full_scan_task` ignora `ENABLE_GMAIL_IMAP`.

## Conformi
Canali Drive on/off (§13) ✔; dedup per canale ✔; associazione documento→entità e
instradamento eventi ✔; tassonomia `dichiarazione_iva`/`avviso_bonario` presente
nei nomi ✔.

## Note
Valori parametrici (frequenze, mittenti, cartelle, canali on/off) riportati senza
proporne il cambio (CLAUDE.md). Rischio principale: frammentazione di collection e
tassonomie + assenza di gate on/off per i canali email F24/Verbali.
