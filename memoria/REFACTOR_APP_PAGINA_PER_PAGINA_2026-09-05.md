# Refactoring pagina per pagina — 05/09/2026

Fonte di verità: codice `main`, `page_catalog.json`, log produzione, database e test correnti.

## Obiettivo
Verificare tutte le 64 schermate canoniche non solo come route raggiungibili, ma come flussi operativi completi: dati in ingresso, API, relazioni, scritture, automatismi, errori, duplicazioni e dipendenze.

## Bloccanti trasversali trovati nel primo passaggio

1. **Audit incompleto** — la maggioranza delle 64 pagine è ancora `unverified` o `in_review` nel catalogo canonico.
2. **Drive documentale** — il job `SCHEDULER-DRIVE-INDICE` fallisce perché la radice configurata non risulta una cartella Drive attiva.
3. **Google Sheets quota** — il job di sincronizzazione supera ripetutamente il limite di richieste/minuto e salta sincronizzazioni.
4. **Email/IMAP/SMTP** — servizi non configurati in produzione, quindi le pagine e gli automatismi che dipendono dalla posta non possono essere considerati operativi.
5. **Gestione riservata** — credenziale dedicata non configurata; da ricondurre alla strategia di accesso effettiva scelta per l'ERP.
6. **Prima Nota / corrispettivi** — almeno un corrispettivo reale viene saltato perché tutti i campi importo noti risultano zero; serve diagnosi del record e normalizzazione sorgente.
7. **Funzioni dichiarate ma non implementate** — import Excel personale (ritorna 0), generazione PDF F24 e PDF contabile sollevano `NotImplementedError`.
8. **Frontend** — warning di bundle/chunk troppo grande; va ridotta la superficie caricata per pagina e verificato il lazy loading.
9. **Ritenute** — pagina canonica ancora `unverified`; va validata contro tutte le fatture XML con `DatiRitenuta`, non solo contro la vista già popolata.
10. **Menu** — catalogo Qromo in riallineamento; URL QR canonico deve restare `https://impresasemplice.online/menu/` e non dipendere dal dominio Render.

## Ordine di refactoring operativo

### P0 — catena contabile primaria
- Login / sessione / PIN
- Dashboard
- Archivio fatture
- Fornitori
- Prima Nota
- Pulizia Prima Nota
- Scadenze
- Import documenti
- Archivio documenti
- Movimenti banca
- Riconciliazione banca / F24 / documenti / stipendi
- Ritenute

**Criterio di accettazione P0:** un XML reale deve produrre una catena verificabile `Fornitore/Cliente -> Fattura -> Scadenza -> Pagamento/prova -> Documento -> Prima Nota`, senza duplicati e senza stati fittizi di pagamento.

### P1 — contabilità e fiscale
- Piano dei Conti
- Bilancio
- Verifica Bilancio
- Libro Giornale
- Controllo mensile
- Calendario fiscale
- Cespiti
- Finanziaria
- Chiusura esercizio
- Budget
- Mutui
- Contabilità avanzata
- Utile obiettivo
- Previsioni acquisti
- Gestione IVA
- Dati ISA
- Situazione fiscale

### P1 — documenti e riconciliazioni secondarie
- Archivio bonifici
- Assegni
- PayPal
- PagoPA
- Coerenza POS
- Indice documentale Drive
- Atti amministrativi
- Fatture estere

### P2 — strumenti / integrazioni / amministrazione
- Commercialista
- Pianificazione
- Visure
- Learning Machine
- Agenti AI
- Impostazioni F24 email
- Impostazioni AI
- OpenAPI
- Mittenti email
- Admin sistema
- MFA
- Elaborazioni amministrative
- Elaborazioni legacy
- Utenti
- Mappa gestionale

### P2 — veicoli
- Flotta noleggio
- Verbali noleggio
- Costi noleggio
- Dettaglio verbale

## Regola per ogni pagina
Per ogni schermata vanno verificati e registrati: route, componente, API chiamate, dati realmente restituiti, origine dei dati, scritture effettuate, relazioni upstream/downstream, automazioni, errori runtime, test esistenti, test mancanti, duplicazioni e funzioni da eliminare.

Una pagina non passa a `verified` solo perché restituisce HTTP 200 o perché si apre nel browser.
