# Verifica funzionale motori — Riepilogo unificato

_Loop /goal, 13/07/2026. Verifica di conformità dei 5 motori contro le
specifiche. Report di dettaglio: `VERIFICA_IVA.md`, `VERIFICA_F24.md`,
`VERIFICA_CONTABILITA.md`, `VERIFICA_DOCUMENTI.md`, `VERIFICA_CHAT.md`._

## Quadro complessivo

| Motore | P0 | P1 | P2 | Nucleo |
|---|---|---|---|---|
| IVA | 0 | 2 | 7 | Conforme e testato (no doppia detrazione) |
| F24 | 0 | 5 | 9 | Regola cardine "saldo≠costo" rispettata |
| Contabilità | 1 (latente) | 3 | 5 | F24-non-costo, ricavi=corrispettivi, POS: conformi |
| Documenti | 2 | 5 | 4 | Ingest/dedup/associazione ok; instradamento incoerente |
| Chat | 0 | 2 | 6 | Tracciabile, anti-allucinazione, motivata |

**Nessun errore di calcolo fiscale.** I difetti gravi sono di **instradamento
dati** (documento/F24 nella collection sbagliata) e **doppio conteggio latente**
(POS), non di formule.

## P0 — da chiarire/correggere (priorità massima)

1. **[Contabilità] Doppio conteggio POS in prima nota banca (LATENTE).** L'accredito
   NUMIA non chiude la entrata sintetica "Corrispettivi POS" → il POS può contare
   due volte nel Bilancio. Condizionato all'attivazione del canale Estratti Conto
   (oggi spento) o all'upload manuale di un estratto. **Da provare su un estratto
   reale prima di riaccendere il canale.**
2. **[Documenti] F24 da email in `f24_commercialista` invece di `f24_unificato`.**
   Un F24 arrivato via email non compare nel modulo F24 principale.
3. **[Documenti] Allegati email non scaricabili dal link generico** (`/documento/
   {id}/download` cerca solo in `documents_inbox`) → 404 sul "Vai a".

## P1 — regole implementate ma non pienamente agganciate

- **[IVA]** controllo 12 giorni + `data_trasmissione_sdi` non integrati; ricalcolo
  riscrive `periodo_iva_attribuito` su fatture già confermate.
- **[F24]** DM10↔RC01 capitale INPS non conteggiato nel doppio pagamento; controlli
  di legame senza matricola/sede; alert bloccante "F24 mancante" cancellabile da
  `/riconcilia-tutto`; ravvedimento elimina invece di fascicolo; associazione
  cedolini parziale.
- **[Contabilità]** filtri duri riconciliazione ±2€/±5gg non implementati e
  auto-conferma senza verifica data; riconciliazione manuale senza guard 409 e non
  marca l'EC; soglia 516,46€ per keyword senza verifica importo.
- **[Documenti]** canali F24/Verbali email senza interruttore (girano se ci sono
  credenziali) mentre §13 li dà spenti; nuovi canali Drive fiscali assenti dal
  documento; frammentazione tassonomia.
- **[Chat]** tool Quietanze e Documenti puntano a collection sbagliate → temi muti.

## Fix a basso rischio già applicabili subito (bug netti, non parametri)
- **Chat/Quietanze**: `db["quietanze"]` → `quietanze_f24` (collezione univoca).
- **Residuo HACCP `scheda_tecnica`**: già rimosso in questo commit.

## Fix che richiedono una scelta (parametri/canali/dati) — da confermare
- Canali F24/Verbali email accesi o spenti (introdurre flag `ENABLE_*`).
- Collection documenti per la Chat: `documents_inbox` o `documenti_classificati`.
- Consolidamento F24 su `f24_unificato` (tocca il flusso email → dati).
- Allineamento documento su frequenza Fatture Drive (15 min vs "ogni ora").
- Soglia "3 mesi" IVA e tolleranze riconciliazione.

## Nota
Tutte le verifiche sono in sola lettura tranne la rimozione del residuo HACCP
`scheda_tecnica` (già dentro la rimozione HACCP autorizzata). I valori parametrici
sono riportati senza modificarli, come da CLAUDE.md.

## STATO CORREZIONI (13/07/2026 — "procedi con tutto")

Tutti i P0/P1 tecnici sono stati CORRETTI e sono in produzione (232 test verdi):

| Voce | Stato | Commit/nota |
|---|---|---|
| P0-1 POS doppio conteggio | ✅ risolto | accrediti POS non duplicano l'entrata "Corrispettivi POS" |
| P0 Documenti — F24 email in collection sbagliata | ✅ risolto | unificato su `f24_unificato` (+ migrazione dry-run) |
| P0-2 Documenti — allegati email non scaricabili | ✅ risolto | download risolve anche `*_email_attachments` |
| IVA P1-a (12 giorni + data_trasmissione_sdi) | ✅ risolto | avviso `emessa_oltre_12_giorni` |
| IVA P1-b (ricalcolo su confermate) | ✅ risolto | preserva `periodo_iva_attribuito` |
| F24 P1-A/B (DM10↔RC01 capitale INPS + matricola) | ✅ risolto | capitale INPS conteggiato; posizioni diverse non collegate |
| F24 P1-C (alert bloccante cancellabile) | ✅ risolto | `/riconcilia-tutto` rigenera l'alert |
| F24 P1-D (ravvedimento elimina) | ✅ risolto | fascicolo: storicizza + collega, non elimina |
| F24 P1-E (associazione cedolini) | ✅ risolto | coerenza causali + matricola |
| Contabilità P1-1 (auto-conferma senza data) | ✅ risolto | conferma media richiede data plausibile |
| Contabilità P1-2 (riconciliazione manuale) | ✅ risolto | guard 409 + marca l'EC |
| Contabilità P1-3 (516,46 sull'importo) | ✅ risolto | flag `sopra_soglia_516` + confidence bassa |
| Chat P1 (collezioni sbagliate) | ✅ risolto | `quietanze_f24` / `documents_inbox` |

Restano P2 minori (robustezza/coerenza documentale) e le scelte parametriche
già applicate (canali email, frequenza, collezioni). Il P0-1 POS va comunque
provato su un estratto conto reale con accredito NUMIA prima di riaccendere il
canale Estratti Conto.
