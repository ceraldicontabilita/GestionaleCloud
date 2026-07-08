# Dipendenti — stato reale vs specifica

Fonte specifica: `DIPENDENTI.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Correzione importante: NON è "solo anagrafica in sola lettura"

Un'analisi precedente in questa sessione aveva concluso che l'HR fosse interamente spostato
sull'app esterna **AppDipendenti** (https://appdipendenti.onrender.com, stesso cluster
MongoDB Atlas condiviso), con solo un'anagrafica in sola lettura rimasta in questo repo.
**Verifica più approfondita smentisce parzialmente questa conclusione**: il backend
`app/routers/employees/dipendenti.py` (2760 righe) ha CRUD completo e attivo — contratti,
buste paga, libretti sanitari, turni, portale dipendenti, libro unico, TFR
(`app/routers/employees/tfr.py`, 1658 righe) — tutto montato e raggiungibile su
`/api/dipendenti`. Un commento nel codice dichiara "SOLO LETTURA" (riga 642) ma si riferisce
SOLO a un singolo endpoint di import bulk (che effettivamente non sovrascrive campi
esistenti senza `overwrite=True`), non all'intero modulo — il commento è fuorviante se letto
fuori contesto. **Quello che manca davvero non è il backend, ma il frontend**: il fascicolo
dipendente a 6 schede richiesto dalla spec non esiste come UI in questo repo.

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Dipendente come entità centrale, fascicolo unico | ✅ backend, ❌ frontend | `app/routers/employees/dipendenti.py` (2760 righe) — CRUD completo lato API; nessuna UI a 6 schede trovata nel frontend |
| Dedup per CF, nome+cognome+nascita, matricola, IBAN | ✅ (parziale, solo CF+nome come chiavi primarie) | `app/services/dipendenti_dedupe.py::trova_duplicati` |
| Funzione di merge duplicati (analoga a quella mancante per Fornitori) | ✅ | `dipendenti_dedupe.py::merge_dipendenti` (righe 199+), con opzione soft-delete, più `auto_merge_tutti` (righe 272+) con `dry_run` |
| Stati (attivo/onboarding/sospeso/cessato/incompleto) | DA VERIFICARE nel dettaglio | non ricontrollato in questo passaggio se tutti e 5 gli stati sono realmente usati nel campo `stato`/`status` del dipendente |
| Regola "cessato non significa cancellato" | DA VERIFICARE | non ricontrollato in questo passaggio se un dipendente cessato resta interrogabile/storico o viene rimosso dalle liste attive |

## Gap confermati (in ordine di priorità)

1. **Frontend fascicolo dipendente assente**: il backend supporta contratti/buste paga/
   libretti sanitari/turni/portale/TFR, ma non esiste nel repo una pagina che esponga questi
   dati in un fascicolo unico a 6 schede come richiesto dalla spec — funzionalità backend
   "orfana" di UI.
2. **Duplicazione di responsabilità con AppDipendenti non chiarita**: sia questo repo che
   AppDipendenti scrivono sullo stesso cluster MongoDB condiviso; non è stato verificato se
   le due app scrivono sulle stesse collezioni in modo coordinato o se esiste rischio di
   sovrascrittura concorrente. Questo va chiarito con l'utente prima di ulteriori sviluppi
   HR in questo repo — potrebbe essere debito tecnico da una migrazione parziale mai
   completata, oppure una duplicazione intenzionale (backend qui, frontend là).
3. **Dedup solo su CF/nome, non su matricola/IBAN**: la spec chiede 4 chiavi di dedup;
   il codice reale (`dipendenti_dedupe.py`) usa principalmente CF come chiave primaria e
   nome come fallback — non confermato se matricola e IBAN sono usati come chiavi di dedup
   aggiuntive.
4. **7 alert richiesti dalla spec**: non riverificati in questo passaggio — da controllare
   in un audit dedicato se esiste un sistema sistematico analogo a quello di Fornitori/
   Magazzino, o se — come per gli altri moduli — solo una minoranza è realmente generata.

## Bug/incoerenze note (da correggere)

- ✔ RISOLTO (lug 2026) — Il commento "SOLO LETTURA" a riga 642 di `dipendenti.py` è stato
  corretto/contestualizzato: ora chiarisce esplicitamente che si applica solo al singolo
  endpoint di import bulk, non all'intero modulo (stesso pattern di commento obsoleto/
  fuorviante già trovato e corretto in `MAGAZZINO.md`).
