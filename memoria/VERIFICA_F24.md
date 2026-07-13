# Verifica di conformità — Motore F24 / Tributi

_Loop /goal, 13/07/2026. Sola lettura, contro
`SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md`, `LOGICA_FUNZIONAMENTO.md §7`,
`CLAUDE.md`. Nessuna modifica al codice._

**Esito**: nessun P0 (la regola cardine "saldo F24 mai automaticamente costo"
è rispettata). 5 scostamenti P1, vari P2.

## Quadro d'insieme — due motori paralleli
- **Motore "specifica" (conforme, ben testato)**: `tributi_engine.py` +
  `fiscale_engine.py`, esposto da `f24_analisi.py`, test in
  `test_tributi_fiscale_engine.py`. Puro e aderente alla specifica.
- **Motore "operativo" (preesistente)**: `parser_f24.py`/`f24_parser.py`,
  `quietanze_import.py`, `f24/f24_riconciliazione.py`, `f24_alert_system.py`,
  `calcolo_imposte.py`. È quello collegato al flusso quotidiano, con logiche più
  vecchie e in alcuni punti divergenti.
La maggior parte degli scostamenti nasce dal fatto che il motore "specifica" è
**debolmente agganciato** al flusso operativo.

## Tabella regola → stato → evidenza

| # | Regola | Stato | Evidenza |
|---|--------|-------|----------|
| 1 | Parser sezioni e codici tributo | CONFORME con riserve | `parser_f24.py:96-608`, `f24_parser.py:161-267` |
| 2 | Quietanza senza F24 (Caso 3) → alert bloccante, no ricostruzione | CONFORME (rischio P1-C) | `quietanze_import.py:307-336` |
| 3 | RC01 = regolarizzazione periodo precedente | CONFORME | `tributi_engine.py:81-84,217-225,319-323` |
| 4 | DM10 ↔ RC01: non sommare due volte | PARZIALE | `tributi_engine.py:354-396` → P1-A |
| 5 | CXX / INAIL | CONFORME | `tributi_engine.py:78-92`, `parser_f24.py:294-418` |
| 6 | Classificazione codici (costo/non costo) | CONFORME | `tributi_engine.py:33-137` |
| 7 | Scadenza naturale 16 + giorni ritardo | CONFORME (16 coerente) | `tributi_engine.py:174-196` |
| 8 | Stato pagamento | CONFORME | `tributi_engine.py:182-196` |
| 9 | Doppio pagamento | CONFORME impianto, P1 sul calcolo quota | `tributi_engine.py:408-452` |
| 10 | Fascicolo F24 | MATERIALIZZATO (collezione `fascicoli_f24`) | `services/fascicolo_f24.py`, endpoint `/api/f24/fascicolo/*` |
| 11 | Saldo F24 mai automaticamente costo | CONFORME | `fiscale_engine.py:53-97`, `calcolo_imposte.py:290-304` |
| 12 | Associazione F24-cedolini (periodo/causale/posizione/soggetto) | CONFORME con riserve | `tributi_engine.py:289-343` → P1-E |

Valori parametrici: scadenza **16** (`tributi_engine.py:174-179`, coerente §20);
ABI attendibili hardcoded (`f24_parser.py:153`); tolleranze €0,50
(`quietanze_import.py:245`) e €1/€2 (`f24_alert_system.py:102,168`) — riportati,
non giudicati; da concordare con l'utente se si vuole uniformarli.

## P0 — nessuno
Nessun ramo deduce automaticamente il saldo F24 come costo. `calcola_costo_personale`
accetta solo voci esplicite e ignora le non-costo (`fiscale_engine.py:55-59,74`);
IRAP non sottrae l'intero F24 (`:160-191`); `calcolo_imposte.py` ricostruisce i
costi dai conti, non dal saldo F24.

## P1
- **P1-A — DM10↔RC01: capitale INPS duplicato non rilevato.** I "comuni" escludono
  esplicitamente `DM10`/`RC01` (`tributi_engine.py:378`), quindi la quota di
  capitale contributivo INPS non entra mai in `quota_potenzialmente_duplicata`; se
  due modelli condividono solo DM10/RC01 risultano `collegati=False`. Il caso §16
  passa i test solo perché c'è anche il codice 1001 condiviso.
- **P1-B — Verifica di legame povera.** `confronta_dm10_rc01` confronta solo CF,
  periodo e codici comuni; mancano matricola INPS e codice sede (§21 punti 3-4).
- **P1-C — L'alert bloccante "F24 mancante" può essere cancellato.**
  `/riconcilia-tutto` fa `delete_many({"tipo":"quietanza_senza_match"})`
  (`f24_riconciliazione.py:1242`) senza rigenerarlo per le quietanze ancora orfane.
- **P1-D — Ravvedimento: elimina invece di fascicolo.** All'upload propone di
  eliminare l'F24 originario (`f24_riconciliazione.py:115-130,656-697`), mentre la
  §21 chiede di collegarli in un fascicolo mensile storicizzato.
- **P1-E — Associazione cedolini parziale.** `valuta_associazione_cedolini` verifica
  soggetto+periodo+RC01 ma non posizione/causali né i cedolini reali dal DB
  (`tributi_engine.py:289-343`, `f24_analisi.py:187-200`).

## P2 — robustezza
- P2-A parser quietanza legato all'ABI `05034` (`f24_parser.py:133-150`).
- P2-B formati `periodo_riferimento` divergenti tra i due parser.
- P2-C liste codici ravvedimento non allineate tra moduli.
- P2-D `f24_alert_system` usa la data di versamento come scadenza e stato `paid`
  su collezione `db.f24` (disallineato dal flusso `pagato`/`f24_commercialista`).
- P2-E doppio vocabolario stato + più collezioni F24 (`f24`, `f24_commercialista`,
  `f24_unificato`).
- P2-F "fascicolo F24" §21 — RISOLTO: materializzato in `fascicoli_f24`
  (`services/fascicolo_f24.py`), endpoint `/api/f24/fascicolo/costruisci` e
  `/api/f24/fascicolo/{cf}/{mese}/{anno}`. Collega F24 (DM10/RC01), quietanze e
  cedolini del periodo con totali classificati; non crea documenti mancanti.
- P2-G `3847/3848` etichettati "IMU" nella costante (impatto limitato).
- P2-H TODO fallback AI parsing non implementato (`f24_riconciliazione.py:79-82`).
- P2-I alert "F24 mancante" emesso anche quando l'F24 esiste ma non combacia.

## Raccomandazioni (nessuna modifica applicata)
1. P1-A/B: includere capitale INPS DM10↔RC01 nel doppio pagamento + matricola/sede.
2. P1-C: non cancellare (o rigenerare) gli alert bloccanti in `/riconcilia-tutto`.
3. P1-D: fascicolo storicizzato al posto dell'eliminazione.
4. P1-E: agganciare l'associazione ai cedolini reali + posizione/causale.
5. P2-A/B/C: normalizzare periodo, unificare codici ravvedimento, parser
   quietanza indipendente dall'ABI.
