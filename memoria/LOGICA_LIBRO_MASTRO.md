# LOGICA — Libro Giornale, Libro Mastro e ricostruzione della contabilità

> Fonte concettuale: contabilità generale italiana in **partita doppia** (metodo
> Fibonacci/Pacioli, recepito dal Codice Civile artt. 2214-2220 e principi OIC).
> Ricerca web di riferimento in fondo.

## 1. I concetti (cosa intende il commercialista)

**Partita doppia.** Ogni operazione economica (comprare, pagare, incassare,
liquidare l'IVA…) si registra come **scrittura contabile** che movimenta almeno
**due conti**: una parte in **DARE** e una in **AVERE**, per importi uguali.
Regola d'oro: in ogni scrittura **totale DARE = totale AVERE** (la scrittura
"quadra"). Se non quadra, è sbagliata.

**Libro giornale** (art. 2216 c.c.). Registro **cronologico**: annota tutte le
scritture nell'ordine in cui avvengono, con data, numero progressivo, causale
(descrizione), conti in Dare/Avere e il **documento di origine** (la fattura,
la quietanza, l'estratto conto…).

**Libro mastro.** Le stesse scritture **riclassificate per conto**. Ogni conto
ha la sua scheda, il **mastrino**: intestazione (es. *Debiti v/fornitori*,
*Banca c/c*, *IVA ns/credito*, *Acquisti merci*) e le righe Dare/Avere che lo
riguardano, con il **saldo** progressivo.

**Perché conta (obiettivo dell'utente).** Leggendo il libro mastro il
commercialista **ricostruisce la contabilità dell'azienda**: saldi dei conti,
crediti/debiti aperti, IVA a credito/debito, costi/ricavi, e da lì
Stato Patrimoniale + Conto Economico = **Bilancio**. Il mastro è la memoria
completa: se hai le scritture, hai la contabilità.

## 2. Esempi di scritture (le operazioni tipiche del gestionale)

Ricevo una fattura d'acquisto da 122 € (100 imponibile + 22 IVA):

| Conto | DARE | AVERE |
|---|---|---|
| Acquisti merci (80.01) | 100 | |
| IVA ns/credito (30.10) | 22 | |
| Debiti v/fornitori (60.01) | | 122 |

Pago la fattura in banca:

| Conto | DARE | AVERE |
|---|---|---|
| Debiti v/fornitori (60.01) | 122 | |
| Banca c/c (40.02) | | 122 |

Il **debito v/fornitori** nasce (Avere) con la fattura e si chiude (Dare) col
pagamento: il saldo del mastrino torna a zero → il fornitore è pagato. L'IVA
ns/credito si accumula nel suo mastrino e confluisce nella **liquidazione IVA**.

## 3. Come è mappato nel gestionale (fonti di verità nel codice)

Il motore in partita doppia **esiste già**:

- `app/services/contabilita_generale.py`
  - `ScritturaContabile` — testata + righe `{conto, conto_nome, dare, avere}` con
    **validazione di quadratura** (Dare == Avere).
  - Generatori standard: `scrittura_acquisto_merce`, `scrittura_pagamento_fornitore`,
    `scrittura_nota_credito_fornitore`, `scrittura_vendita_merce`, ecc.
  - Piano dei conti con codici (60.01 Debiti v/fornitori, 40.02 Banca, 30.10 IVA
    ns/credito, 80.01 Acquisti merci…).
- `app/services/accounting_engine.py` → `AccountingEnginePersistence`
  - **Libro giornale** persistito nella collezione **`scritture_contabili`**
    (`salva_scrittura` con dedup per `hash`, `get_scritture`,
    `get_scrittura_by_fattura`, `storna_scrittura`).
- **Libro mastro** = aggregazione delle righe di `scritture_contabili` per conto
  → saldo per mastrino.

### 3-bis. Il collegamento che rende tutto ricostruibile (chiave stabile)

Ogni scrittura generata da una fattura porta la **chiave stabile della fattura**
`invoice_key` (= numero + P.IVA fornitore + data). Questo è il perno:

- le scritture vivono in `scritture_contabili`, **collezione separata** da
  `invoices`: **azzerare le fatture NON cancella il libro giornale**;
- inoltre `storia_fatture` (registro cronologico per `invoice_key`, vedi
  `app/services/storia_fatture.py`) conserva lo **stato derivato** (pagamento,
  IVA, centro di costo, riconciliazioni) e uno **snapshot pre-azzeramento**;
- al **reimport** dello stesso XML la fattura è riconosciuta per `invoice_key`,
  lo stato derivato viene riapplicato e le scritture NON vengono duplicate
  (dedup per hash / `get_scrittura_by_fattura`).

Risultato: **cancella tutto e reimporta → la contabilità si ricostruisce da
sola**, perché il libro giornale/mastro e la storia sopravvivono all'azzeramento
e sono agganciati alla chiave stabile.

## 4. Quando si genera una scrittura (eventi → libro giornale)

| Evento nel gestionale | Scrittura (partita doppia) | Generatore |
|---|---|---|
| Import fattura d'acquisto | Acquisti + IVA credito / Debiti v/fornitori | `scrittura_acquisto_merce` |
| Pagamento fattura (cassa/banca) | Debiti v/fornitori / Cassa o Banca | `scrittura_pagamento_fornitore` |
| Nota di credito da fornitore | Debiti / rettifica costi + IVA | `scrittura_nota_credito_fornitore` |
| Corrispettivo / vendita | Cassa+Banca / Ricavi + IVA debito | `scrittura_vendita_merce` |
| Liquidazione IVA | IVA debito / IVA credito / Erario | motore IVA |

Ogni scrittura viene **salvata in `scritture_contabili`** (libro giornale) con:
`data`, `numero`, `causale`, `righe[]`, `documento` (tipo+riferimento),
`invoice_key`, `hash` (dedup). In parallelo l'evento viene annotato nella
**storia della fattura** (`storia_fatture.registra`) in ordine cronologico, così
"dietro la fattura" si legge tutto ciò che è successo.

## 5. Regole cardine (da non violare)

1. **Ogni scrittura quadra** (Dare = Avere): la validazione è in
   `ScritturaContabile._valida_quadratura`. Una scrittura che non quadra non si
   salva.
2. **Niente doppioni**: dedup per `hash` in `salva_scrittura` e per
   `invoice_key`/`fattura_id` (una fattura → una scrittura d'acquisto).
3. **Il libro giornale non si cancella con le fatture**: `scritture_contabili` e
   `storia_fatture` sono separate da `invoices`.
4. **Coerenza col resto**: il saldo F24 non è mai costo automatico (vedi
   SPECIFICA_F24); l'IVA non si detrae due volte (vedi motore IVA); i
   corrispettivi non generano doppia scrittura in Prima Nota.
5. **Tracciabilità**: da ogni scrittura si risale al documento di origine; da
   ogni fattura si risale alle sue scritture (`get_scrittura_by_fattura`) e alla
   sua storia (`storia_fatture.storia`).

## 6. Come si ricostruisce la contabilità (procedura del commercialista)

1. Leggi il **libro giornale** (`scritture_contabili`) in ordine di data.
2. Riclassifica per conto → **mastrini** (libro mastro), calcola i **saldi**.
3. I saldi dei conti **patrimoniali** → Stato Patrimoniale; dei conti
   **economici** → Conto Economico → **Bilancio**.
4. Controlli tipici sul mastro: crediti clienti aperti, debiti fornitori aperti,
   IVA a credito/debito, quadratura generale (Σ Dare = Σ Avere su tutti i conti).

## Fonti (ricerca web, luglio 2026)
- appvizer.it — *Come fare il libro mastro*
- financial-corner.com — *Il metodo della partita doppia (giornale, mastro)*
- pmi.it — *Contabilità generale: partita doppia e mastrini*
- economiaziendale.net — *Il libro mastro*
- startyerp.com — *La scheda contabile / mastrino*
