# Audit esterno 18/07/2026 — trascrizione e stato lavori

Audit consegnato dall'utente il 18/07/2026 (verifica su commit ad239e8:
71 pagine React, 52 rotte, 533 pulsanti, 659 azioni UI). Questo file è la
trascrizione operativa: per il punto POS la logica PROPOSTA dall'audit è
stata SOSTITUITA dalla REGOLA CANONICA fissata dall'utente (sotto), che
prevale. Stato aggiornato onestamente: ✅ solo ciò che è stato fatto E
verificato su produzione.

## REGOLA CANONICA POS (utente, 18/07/2026 — sostituisce la proposta audit)

1. **Cassa DARE** = corrispettivo totale del giorno (XML registratore).
2. **Cassa AVERE "POS Verso Banca"** = il **POS REALE** trascritto la sera
   nella card delle chiusure manuali ("quello che esce dal terminale");
   fallback elettronico XML solo se la chiusura non è trascritta
   (`quota_pos_fonte`).
3. **Banca DARE** = la stessa cifra come puro **TRASFERIMENTO** cassa→banca
   (source `trasferimento_pos`, stesso `trasferimento_id`): una sola
   operazione su due registri, mai duplicazioni.
4. **L'accredito dell'estratto conto NON crea entrate**: riconcilia il
   trasferimento del giorno di vendita (causale NUMIA "DEL gg/mm/aa"),
   accumulando i circuiti, tolleranza 2%/5€.
5. **Coerenza POS**: XML elettronico = dato FISCALE; chiusura manuale =
   dato OPERATIVO reale. La differenza (reale − XML) è il **NON BATTUTO**,
   esposto con **saldo progressivo** per recuperarlo nei giorni successivi.
6. **Controllo di TRASCRIZIONE**: lo stesso XML verifica anche il
   corrispettivo battuto a mano la sera (totale/contanti): se manuale ≠ XML
   la cassa è sbilanciata e non reale → anomalia evidenziata (invariante
   `trascrizione_corrispettivo_manuale` nel collaudo).

La regola è codificata in: `app/services/scritture_contabili.py` (motore
unico), invarianti `trasferimento_pos_speculare` e
`trascrizione_corrispettivo_manuale` del collaudo, Coerenza POS
(non_battuto + progressivo), LOGICA_FUNZIONAMENTO.md e CLAUDE.md.

## P0

| # | Punto audit | Stato |
|---|---|---|
| P0-1 | Logica POS/Corrispettivi contraddittoria (3 flussi diversi) | ✅ FATTO — i tre flussi (import XML, sync scheduler, propagazione eventi) delegano tutti a `registra_corrispettivo` del motore unico secondo la regola canonica; migrazione del pregresso 2026 eseguita su prod (141 giorni, trasferimenti €294.286,70, 729 accrediti EC riconciliati) |
| P0-2 | Manca un motore unico di scrittura contabile (>50 writer diretti) | ✅ FATTO — TUTTI i flussi migrati (fatture, assegni, F24, PayPal, mutui, riconciliazioni, versamenti, rapido, sync EC): l'unico file che scrive in prima_nota_cassa/banca è `app/services/scritture_contabili.py`, con validazione obbligatoria (data/importo>0/tipo/categoria/source); il test-guardia vieta qualsiasi nuovo insert diretto. Bonus: scoperto e isolato uno schema alieno di partita doppia che fiscalita_italiana scriveva in prima_nota_cassa (ora in collezione dedicata) |
| P0-3 | Il collaudo POS usava XML contro banca | ✅ FATTO — gerarchia corretta: chiusura manuale = operativo, XML = fiscale (+ controllo trascrizione), EC = accredito reale che riconcilia il trasferimento, attribuzione al giorno di vendita dalla causale |

## P1 Sicurezza

| # | Punto | Stato |
|---|---|---|
| P1-1 | Token JWT stampato nei log browser (WebSocket) | ✅ FATTO — l'URL non viene più loggato |
| P1-2 | Cookie senza flag Secure | ✅ FATTO — Secure in produzione (Render/https) su login, PIN e session_active |
| P1-3 | ADMIN_PIN in chiaro ammesso | ✅ FATTO — supporto rimosso, resta solo PIN_HASH_ADMIN (config prod verificata). NOTA: l'hash resta SHA-256, debole per un PIN corto — mitigato dal blocco tentativi (5/5min); upgrade a KDF lento = lavoro futuro |
| P1-4 | Verbali email: funzioni non implementate (return None) | ✅ FATTO — le 4 funzioni riusano i motori esistenti (quietanze via `trova_pagamento_verbale`/PayPal-PagoPA-EC, PDF dagli allegati, nuovi verbali dallo scanner Gmail, nuove quietanze associate ai verbali); orchestratore agganciato al job orario e a un endpoint admin on-demand; verificato su prod (`POST /api/verbali-riconciliazione/scan-email`, deploy e7757bc) |

## Interfaccia

| Punto | Stato |
|---|---|
| Movimenti Banca: celle descrizione ~800px | ✅ FATTO (a capo, overflowWrap) |
| Mittenti Email: select oltre il contenitore | ✅ FATTO (maxWidth 100%) |
| Mappa gestionale: sezioni compresse | ✅ FATTO (minmax(min(270px,100%))) |
| Assegni: campi filtro senza etichetta | ✅ FATTO (aria-label dai placeholder — 8 campi; restanti da verificare a video) |
| Impostazioni F24: bottoni senza nome | ✅ FATTO (aria-label sui bottoni icona) |
| Bottoni < 36px su molte pagine | ✅ FATTO (20/07: minimo touch 36×36 su mobile + guardia automatica su tutte le rotte statiche) |
| Viewer condiviso usato solo da 4 pagine | ✅ FATTO (viewer canonico esteso; chiusi i residui Scadenze, Prima Nota/corrispettivi e Dettaglio Verbale) |

## Buoni brevi

| Punto | Stato |
|---|---|
| Rimuovere log URL WebSocket | ✅ |
| encoding="utf-8" nei 4 test | ✅ |
| PYTHONUTF8=1 nel workflow backend | ✅ |
| Cookie Secure in produzione | ✅ |
| Eliminare ADMIN_PIN in chiaro | ✅ |
| Nome repository nel README | ✅ (già corretto: "Ceraldi ERP") |
| Etichette bottoni F24 | ✅ |
| Etichette filtri Assegni | ✅ |
| Select mobile Mittenti Email | ✅ |
| Descrizioni adattive Movimenti Banca | ✅ |
| Sezioni strette Mappa gestionale | ✅ |
| Pagina Admin "Esito ultimo collaudo" | ✅ FATTO (tab "🧪 Collaudo" in Admin: ultimo report, dettaglio 12 invarianti, storico, bottone "Esegui ora") |
| Audit layout esteso da 19 a 52 rotte | ✅ FATTO (20/07: 84 rotte statiche lette automaticamente dalla route table; mobile+desktop verdi) |
| Test vieta nuovi writer diretti | ✅ (test_motore_unico_scritture) |
| Test vieta corrispettivo_pos come accredito | ✅ (2 test-guardia) |

## Lavori non riducibili

| Punto | Stato |
|---|---|
| Motore unico di scrittura | ✅ completato (vedi P0-2) |
| Corrispettivi → Cassa → POS → Banca definitivo | ✅ regola canonica applicata e migrata |
| Migrazione righe sintetiche POS | ✅ eseguita (104 convertite + 37 create, EC riconciliati) |
| Verbali → driver → trattenuta cedolino | ✅ ricerca pagamento/PDF/nuovi-verbali completata (P1-4); trattenuta in busta resta proposta+conferma manuale (§11 LOGICA_FUNZIONAMENTO.md, per scelta) |
| Collaudo E2E con database di prova (bottoni distruttivi premuti davvero) | ✅ FATTO (20/07) — browser reale + router applicativi reali + MongoDB usa-e-getta in memoria: annullamento preserva il record, conferma lo elimina davvero, tentativo di reset amministrativo da ruolo operatore riceve 403 e lascia i dati invariati. Workflow automatico `E2E distruttivo isolato`; nessun accesso ad Atlas/produzione. |
