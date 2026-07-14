# VERIFICA DI CONFORMITÀ — Registri contabili vs normativa e prassi

Data: 2026-07-14. Richiesta utente: verificare che tutte le logiche applicate
alla contabilità rispecchino quanto richiesto dalle fonti (art. 2214-2220 c.c.,
DPR 600/73 art. 22, L. 383/2001, prassi software Zucchetti/TeamSystem/GB/ViaLibera).

## Matrice requisito → implementazione

| # | Requisito (fonte) | Stato | Dove nel gestionale |
|---|---|---|---|
| 1 | **Cronologicità giorno per giorno** — il libro giornale indica giorno per giorno le operazioni (art. 2216 c.c.) | ✅ | Il giornale ordina per `data_documento`; ogni scrittura porta data documento, data registrazione e data competenza (motore §6.1) |
| 2 | **Registrazione analitica, operazione per operazione** (art. 2216, dottrina) | ✅ | Una scrittura per documento/evento: fattura, corrispettivo, TFR (accantonamento/liquidazione/ritenute/acconti), ammortamenti annuali |
| 3 | **Partita doppia: ogni scrittura quadra (DARE=AVERE)** (prassi, OIC) | ✅ | `registra_scrittura_semplice` e il motore rifiutano scritture sbilanciate; badge di quadratura su giornale e mastro; test dedicati |
| 4 | **Numerazione unica e progressiva delle operazioni** (DPR 600/73 art. 22 per sistemi meccanografici) | ✅ | `numero_registrazione` unico, progressivo, immutabile (protocollo definitivo). Nota: progressivo globale, non per anno — la norma chiede "unica e progressiva", soddisfatta; l'export riporta l'anno di ogni scrittura |
| 5 | **Stato provvisorio vs definitivo** (prassi software: provvisorio = modificabile, fuori dal registro; definitivo = protocollo automatico immutabile) | ✅ | Prima Nota Provvisoria = registro provvisorio (operazioni definitive ma non certe, modificabili, NON compaiono nel giornale); alla conferma → flussi canonici → protocollo definitivo. Le scritture protocollate non hanno API di modifica |
| 6 | **Registrazioni entro 60 giorni** (DPR 600/73 art. 22) | ✅ (aggiunto 2026-07-14) | Nuovo controllo `GET /api/contabilita-gestionale/libro-giornale/controllo-60-giorni` + banner nella pagina Libro Giornale: segnala fatture/corrispettivi oltre 60gg non ancora registrati |
| 7 | **Libro mastro = scrittura ausiliaria derivata** (art. 2214: obbligatorio per natura/dimensione; niente numerazione/bollo/vidimazione) | ✅ | Il mastro è DERIVATO dal giornale (aggregazione delle righe per conto), mai scritto a mano: coerenza garantita per costruzione |
| 8 | **Bollatura/vidimazione libro giornale: ABOLITA** (L. 383/2001 art. 8; resta numerazione + imposta di bollo in stampa/conservazione) | ✅ n/a | Nessuna bollatura da gestire nel software; l'imposta di bollo è adempimento del commercialista in fase di stampa/conservazione sostitutiva (fuori perimetro applicativo, annotato) |
| 9 | **Conservazione 10 anni dall'ultima registrazione** (art. 2220 c.c.; digitale ex art. 2215-bis) | ✅ (strumento) | Export JSON autosufficiente del registro per anno (protocolli, righe, date, fonte documento) + reimport idempotente Admin-only: la RICOSTRUZIONE "pari pari" è garantita. La conservazione fisica del file (10 anni) resta responsabilità organizzativa |
| 10 | **Ricostruibilità della contabilità dal registro** (requisito utente, coerente con la funzione probatoria del giornale) | ✅ | `POST /libro-giornale/import`: anche dopo cancellazione totale, le operazioni rinascono con protocollo, date e importi originali (dedup per id e protocollo+anno) |
| 11 | **Date multiple: registrazione / documento / competenza** (prassi software) | ✅ | Il motore salva `data`, `data_documento`, `data_registrazione`, `data_competenza` (per l'IVA vale la regola del 15 già implementata nel modulo IVA) |
| 12 | **Registri IVA collegati** (DPR 633/72, prassi) | ✅ (modulo dedicato) | Liquidazioni IVA persistite con stati/versioni, anti doppia detrazione, riepilogo annuale (FASE IVA §10) — fuori dal libro giornale ma coerenti con esso |

## Scostamenti/note (nessuno bloccante)

- **Numerazione per anno**: la prassi di molti software azzera il protocollo a
  inizio anno ("1/2026"); noi usiamo un progressivo globale. Entrambi
  soddisfano la norma; cambiare ora richiederebbe una migrazione dei protocolli
  esistenti — se lo vorrai, è una decisione da prendere esplicitamente.
- **Imposta di bollo e conservazione sostitutiva a norma** (firma digitale/
  marca temporale ex art. 2215-bis): adempimenti esterni al software, in capo
  al commercialista. L'export JSON è lo strumento, non la conservazione a norma.
- **Retroattività**: le scritture nate PRIMA del motore unico (senza righe
  DARE/AVERE) restano leggibili dai loro flussi; entrano nel giornale solo le
  scritture protocollate. La ricostruzione completa del pregresso passa dalla
  registrazione contabile (Piano dei Conti → Registra fatture/corrispettivi).

## Fonti

- Art. 2214, 2216, 2220 c.c. (Brocardi, La Legge per Tutti, Bollettino Legislazione Tecnica)
- DPR 600/73 art. 22 — Tenuta e conservazione delle scritture contabili (trovalegge, Agenzia Entrate)
- L. 383/2001 art. 8 — abolizione bollatura libro giornale/inventari (Notariato, Altalex, CCIAA Molise/Modena)
- Tuttocamere — Numerazione, bollatura e tenuta delle scritture contabili; Libri digitali art. 2215-bis
- Prassi software: Zucchetti (Primanota), TeamSystem (Prima nota), GBsoftware, ViaLibera (ST-03), Siware
