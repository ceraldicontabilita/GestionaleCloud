# Audit pagine frontend — Fatture e Riconciliazione (post-consolidamento router)

Richiesto dall'utente dopo il consolidamento dei router backend di fatture e riconciliazione
bancaria, per verificare se anche le pagine frontend fossero frammentate/duplicate allo stesso
modo. Investigazione a sola lettura, poi applicati i fix concreti trovati.

## Dominio Fatture: nessuna modifica necessaria

`FattureHub.jsx` (dispatcher tab, analogo a `VeicoliHub`), `ArchivioFattureRicevute.jsx`
(usa solo il router consolidato `/api/fatture-ricevute`), `Corrispettivi.jsx`: struttura già
coerente col backend consolidato. Le vecchie route (`/fatture-ricevute`,
`/archivio-fatture-ricevute`, `/corrispettivi` top-level) sono tutte `Navigate` puliti verso
`/fatture`.

## Dominio Riconciliazione: 1 bug reale corretto + 1 rinomina

### Bug corretto: navigazione tab rotta in RiconciliazioneUnificata.jsx

`handleTabChange` navigava sempre a `` `/riconciliazione-unificata/${tabId}` ``, ma in
`main.jsx` esiste solo il redirect per il path esatto `"riconciliazione-unificata"` (senza
sotto-tab) verso `/riconciliazione` — non una route `riconciliazione-unificata/:tab`. Il click
su qualunque tab diverso da "Dashboard" (Banca, Assegni, F24, Stipendi, Documenti, PayPal)
cadeva quindi sul catch-all e **rimandava l'utente alla Dashboard invece di cambiare tab**.
Corretto: `handleTabChange` ora naviga sempre a `/riconciliazione/...`, l'unico prefisso
realmente instradato (`getTabFromPath` già lo riconosceva correttamente, solo la navigazione
in uscita era sbagliata).

### Rinomina: tab "Assegni" → "Prelievi Assegno"

Il tab interno "Assegni" di `RiconciliazioneUnificata` mostra solo i prelievi-assegno da
movimenti banca da confermare, mentre `GestioneAssegni.jsx` (pagina separata, raggiungibile
da `/riconciliazione/assegni` o `/gestione-assegni`) è la gestione completa (learning,
combinazioni, associazioni). Nessuna duplicazione di codice — solo lo stesso nome in due punti
diversi confondeva l'utente. L'id/URL resta `assegni` per compatibilità, cambiata solo
l'etichetta visibile.

## Trovato ma non risolto in questo passaggio

- **Sistema "riconciliazione-intelligente" ancora vivo nel tab F24**: `RiconciliazioneUnificata`
  chiama `/api/riconciliazione-intelligente/conferma-multipla`
  (`app/services/riconciliazione_intelligente.py`, 88KB), un sistema parallelo sopravvissuto
  alla consolidazione dei 4 sistemi di riconciliazione bancaria fatta in precedenza in questa
  sessione. Non è un endpoint rotto, ma va deciso se migrare la conferma F24 nel motore
  unificato (`riconciliazione_bancaria.py`) o documentare esplicitamente F24 come sotto-dominio
  volutamente separato.
- **Doppio ingresso alla pagina PayPal**: `RiconciliazionePaypal.jsx` è raggiungibile sia da
  `/riconciliazione/paypal` (via Hub) sia dal tab "PayPal" dentro `RiconciliazioneUnificata`
  (stesso componente lazy-incorporato) quando l'URL è `/riconciliazione`. Nessuna duplicazione
  di codice, solo ridondanza di route — da valutare se rimuovere il tab interno.
- **Naming migliorabile**: `VerificaMovimentiBanca.jsx` (import EC mancanti in Prima Nota,
  dominio `/strumenti`) ha un nome simile a "Riconciliazione" ma è un tool distinto — non
  rinominato in questo passaggio per non rompere eventuali riferimenti/bookmark senza un
  motivo funzionale (solo estetico).

## Pagine verificate come già correttamente isolate (nessuna azione)

`VerbaliRiconciliazione.jsx` (multe veicoli, dominio noleggio non bancario),
`VerificaCoerenza.jsx`, `ArchivioBonifici.jsx`, `CoerenzaPOSCorrispettivi.jsx`,
`PuliziaPrimaNota.jsx`, `BilancioVerifica.jsx`, `DashboardRelazionale.jsx` (legge dalla stessa
collezione `riconciliazioni_match` scritta dal motore unificato — coerente).
