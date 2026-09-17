# Consolidamento sistemi (§0/§2) — analisi sul codice reale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

> Mappa dei presunti "sistemi paralleli" verificata leggendo il codice di `main`.
> Scopo: distinguere ciò che è davvero duplicato (da unificare) da ciò che è
> dominio distinto (da NON fondere) o già unificato.

## Catalogo prodotti — GIÀ UNIFICATO ✅

`prodotti_master` (router `/prodotti-master`, collection `prodotti_master`) è il
**catalogo canonico**: il suo `POST /rebuild` aggrega 6 fonti in una sola
collezione (rebuild iterando: `fatture`, `acquaviva_prodotti`, `prodotti_vendita`,
`magazzino_bar_prodotti`, `listino_prodotti`, `prodotti_canonici`).

Quindi NON esiste un "5→1" da fare. Gli altri non sono doppioni dello stesso concetto:

| Sistema | Ruolo reale | Azione |
|---|---|---|
| `prodotti_master` | Catalogo canonico (aggregatore) | **canonico** |
| `prodotti_canonici` | Motore nomi canonici (sinonimi fornitori) → alimenta master | fonte, tenere |
| `listino` | Prezzi per fornitore (bevande) → fonte del master | fonte, tenere |
| `prodotti_vendita` | **Dominio diverso**: prodotti finiti venduti al banco (legati a ricette) | NON fondere |
| `sconti_merce` | **Dominio diverso**: merce gratis ricevuta dai fornitori | NON fondere |

Ridondanza residua: solo a livello **UI** (CatalogoUnificatoView, ComparatorePrezziView,
ListinoView mostrano fette dello stesso catalogo). Consolidamento UI = scelta di
prodotto, opzionale, non distruttivo sui dati.

## Magazzino — canonico `magazzino_unificato` ✅

`magazzino_unificato` (`/magazzino`) aggrega `magazzino_bar_prodotti` (bar) e
`lotti_fornitori` (materie prime), raggruppa per `prodotto_nome_norm` (stock unico),
scarico FIFO a cascata per `data_fattura`, soglie da `dizionario_prodotti.scorta_minima`
(condivise con i riordini §7). Gli altri router dell'area NON sono morti:
- `magazzino_bar` → carico/scarico bar + lavagna "richieste" (live).
- `materie_prime` → pagina "Materie" (focus allergeni, `/da-fatture`) (live).
- `lotti_fornitori` (router) → endpoint di manutenzione admin; il modulo esporta
  `calcola_nome_canonico` usato dalla produzione.

## Ordini — canonico store `ordini_fornitori`

`ordini_fornitori` è lo store canonico (usato dalla pagina Ordini); `email_ordini`
e `analisi_ordini` lo estendono (invio, analisi). `ordini_app` è un sistema con
storage separato (`ordini_app_storico`/`_reparti`) che ospita anche §7/§8/§11
(riordini, listino, RBAC link-dipendente). Unificarlo richiede di sapere se quelle
collection sono in uso in produzione: decisione operativa (non deducibile dal solo codice).

## Soglie — fonte unica `dizionario_prodotti.scorta_minima` ✅

Niente store soglie parallelo: magazzino (§4 display) e riordini (§7) leggono lo
stesso campo.
