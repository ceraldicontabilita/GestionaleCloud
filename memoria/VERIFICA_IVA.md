# Verifica di conformità — Motore IVA

_Loop /goal, 13/07/2026. Sola lettura, contro `SPECIFICA_IVA.md` e
`LOGICA_FUNZIONAMENTO.md §8`. Nessuna modifica al codice._

**Esito sintetico**: nessun difetto P0 (nessuna doppia detrazione né calcolo
errato). 2 scostamenti P1, vari P2/robustezza.

## Tabella regola → stato → evidenza

| # | Regola | Stato | Evidenza |
|---|--------|-------|----------|
| 1 | Regola 12 giorni (controllo documentale, non determina il periodo) | CONFORME (logica) / NON INTEGRATA (flusso) | `iva_engine.py:90-108` (soglia `>12` a :100); nessun chiamante |
| 2 | Regola giorno 15 + confine dic→gen | CONFORME | `iva_engine.py:82`; confine anno `:68` |
| 3 | Attribuzione periodo per competenza | CONFORME con riserva (fallback data_ricezione) | `iva_fatture.py:41-51,68`; `iva_engine.py:51-87` |
| 4 | `iva_utilizzata` / anti-doppia-detrazione | CONFORME | `liquidazione_iva_engine.py:107`; conferma atomica `routers/iva.py:320-321` |
| 5 | Ricalcolo/pregresso senza doppie detrazioni | CONFORME (no doppia) con dubbio | `routers/iva.py:78-99`; `iva_fatture.py:56-73` |
| 6 | Liquidazione mensile (stati/versioni, credito riportato) | CONFORME | `routers/iva.py:249-361`; saldo `liquidazione_iva_engine.py:140` |
| 7 | Riepilogo/calcolo annuale | CONFORME con dubbio (formula §17) | `riepilogo_iva_engine.py:30-123` |
| 8 | Dichiarazione IVA | PARZIALE (calcolo annuale sì; nessun modello generato) | `riepilogo_iva_engine.py:83-123` |

## Scostamenti

### P0 — nessuno
Il meccanismo `iva_utilizzata` + conferma atomica + esclusione in selezione è
coerente e testato.

### P1
**P1-a — Controllo 12 giorni e `data_trasmissione_sdi` non integrati nel flusso.**
`controllo_emissione_12_giorni` (`iva_engine.py:90`) esiste e funziona ma non è
richiamato; `iva_fatture.py` non valorizza `data_trasmissione_sdi` (obbligatorio
§7); `rileva_anomalie` non emette l'avviso "emessa oltre 12 giorni" (§18).
Impatto basso sul calcolo (controllo documentale), ma regola prevista e oggi assente.

**P1-b — Il ricalcolo riscrive `periodo_iva_attribuito` anche su fatture già
confermate.** `campi_iva_da_fattura` ricalcola sempre `periodo_iva_attribuito`
(`iva_fatture.py:49-51,68`), mentre `periodo_iva_utilizzato` resta fisso → su una
fattura confermata l'attribuito può divergere dall'utilizzato, e la dashboard
mensile (`routers/iva.py:515,528`) mostra quadri incoerenti. NON genera doppia
detrazione (il flag protegge). Fix: quando `iva_utilizzata is True`, preservare
anche `periodo_iva_attribuito`.

### P2 — robustezza
- **P2-a (impatto potenzialmente alto)**: fallback `data_ricezione = created_at`
  (`iva_fatture.py:41-46`). Per fatture storiche importate in blocco, `created_at`
  è la data di import → mis-attribuzione massiva nel "Calcola pregresso". Fix:
  preferire `data_documento`/`data_operazione` quando la ricezione reale manca.
- **P2-b**: `TIPI_NOTA_CREDITO` (`TD04`,`TD08`) duplicato in 5 punti (valori
  coerenti oggi). Consolidare su costante condivisa.
- **P2-c**: soglia "non utilizzata da mesi" hardcoded (3) in
  `riepilogo_iva_engine.py:172` — parametro non configurabile (concordare
  con l'utente prima di modifiche, regola CLAUDE.md).
- **P2-d**: fatture `DA_VERIFICARE` con periodo nullo escluse dal riepilogo
  annuale (`routers/iva.py:489-499`).
- **P2-e**: `calcolo_annuale` non sottrae esplicitamente rettificata/indetraibile
  (coerente per costruzione, formula non esplicita).
- **P2-f / P2-g**: ordine classificazione in `riepilogo_categorie`; nessuna
  deduplica liquidazioni confermate per periodo (edge difensivo).

## Azioni consigliate (ordine)
1. Preservare `periodo_iva_attribuito` sulle confermate nel ricalcolo (P1-b).
2. Integrare o dichiarare fuori-scope controllo 12 giorni + `data_trasmissione_sdi` (P1-a).
3. Rivedere il fallback `created_at` per il pregresso (P2-a).

Valori parametrici (15, 12, 3 mesi, TD04/TD08) coerenti con la specifica dove
questa li fissa; il "3 mesi" e il consolidamento vanno concordati con l'utente.
