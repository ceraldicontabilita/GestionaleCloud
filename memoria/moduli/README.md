# Logica Operativa per Moduli — indice

Gap-analysis dei 10 documenti di specifica forniti dall'utente
(`LOGICA OPERATIVA PER MODULI`), confrontati con il codice reale di GestionaleCloud.
Ogni file segue la stessa struttura: correzione di canale (dove applicabile), tabella
"cosa è confermato implementato" con evidenza file:line, gap prioritari, bug noti.

## Correzione trasversale a tutti i documenti

La specifica originale presuppone "PEC Aruba" come canale di ingresso delle fatture. Verifica
sul codice: non esiste un fornitore/servizio "Aruba" nominato nel sistema. I canali reali sono:
- **Google Drive** — predominante, già attivo, schedulato ogni 15 minuti
  (`app/services/drive_invoice_ingest.py`, `app/scheduler.py`).
- **PEC/SDI generico** — pattern mittente `@pec.fatturapa.it`, non "Aruba" (riga 14 della
  tabella mittenti attendibili: *"SDI - tutte le fatture PEC"*).
- **Upload manuale** — canale complementare storico.

Tutti e tre convergono sulla stessa pipeline (`process_xml_bytes`/`process_fattura_to_db`
in `app/routers/invoices/fatture_upload.py`).

## Documenti

| File | Argomento |
|---|---|
| `FATTURE_RICEVUTE.md` | Import fatture, creazione fornitore, instradamento pagamento, riconciliazione fattura↔banca |
| `FORNITORI.md` | Anagrafica fornitore, dedup, metodo pagamento come variabile centrale |
| `MAGAZZINO.md` | Prodotti, dizionario prodotti, matching righe fattura, giacenze |
| `PRIMA_NOTA_BANCA.md` | Movimenti bancari, i 7 flussi automatici richiesti dalla spec |
| `PRIMA_NOTA_CASSA.md` | Movimenti cassa, split contanti/POS dai corrispettivi |
| `F24.md` | Import F24 da email, stati, matching con banca |
| `RICONCILIAZIONE.md` | Motore di riconciliazione unificato (documento master, incrocia gli altri) |
| `DIPENDENTI.md` | Anagrafica dipendente, dedup/merge, rapporto con AppDipendenti |
| `CEDOLINI.md` | Import cedolini da email, collegamenti a prima nota/TFR/banca |
| `DOCUMENTI_INBOX.md` | Inbox documenti, dedup, classificazione a 7 vie |

## Gap trasversali più rilevanti (ricorrono in più documenti)

1. **Matching stipendi↔banca completamente assente** — confermato incrociando
   `PRIMA_NOTA_BANCA.md`, `RICONCILIAZIONE.md` e `CEDOLINI.md`: nessun codice collega un
   cedolino a un movimento bancario nel motore di riconciliazione automatica.
2. **Sistemi di alert quasi ovunque "definiti ma morti"**: pattern ricorrente in ogni
   documento — le costanti alert esistono in `app/services/alert_engine.py` in numero
   spesso coerente con la spec, ma la maggioranza non ha mai una chiamata di generazione
   reale nel codice (es. Riconciliazione: 6/8 definiti, 0 generati; Cassa: 5/6 definiti,
   1 solo referenziato e mai creato).
3. **Nota di credito (TD04) mai gestita con netting automatico** — gap confermato sia in
   `FATTURE_RICEVUTE.md` che in `RICONCILIAZIONE.md`.
4. **Commenti nel codice non aggiornati che descrivono un comportamento falso**: trovati
   due casi (Magazzino "gestito solo da app esterna Lotti" — falso, il codice scrive
   attivamente su `warehouse_inventory`; Dipendenti "SOLO LETTURA" — falso fuori contesto,
   riferito a un solo endpoint, non all'intero modulo CRUD).
5. **Duplicazione di logica non ancora consolidata** (non toccata in questa sessione,
   segnalata per un audit futuro): due parser F24 indipendenti + un possibile terzo, due
   algoritmi di normalizzazione nome prodotto indipendenti, due vocabolari di stato F24 su
   due collezioni diverse senza sincronismo.

## Tabella mittenti attendibili (riferimento)

Fonte: fornita direttamente dall'utente, 14 righe, colonne CANALE/INDIRIZZO
EMAIL/TIPO DOCUMENTO/DESTINAZIONE/ATTIVO/NOTE. Riga 14 è la conferma definitiva che il
canale PEC è generico SDI (`@pec.fatturapa.it`), non "Aruba". Righe 1-2 confermano il
canale email per cedolini/F24 (Studio Ferrantini, Rosaria Marotta). Le altre righe
(Agenzia Riscossione, INPS/INAIL, Partenopay/PagoPA, TARI, PayPal) instradano verso
`documenti_non_associati` o `verbali` — non ancora incrociate riga-per-riga con il codice
di `app/routers/f24_email_settings.py` e affini in questo passaggio; da fare in un audit
dedicato se serve confermare che OGNI riga della tabella ha un corrispondente reale nella
configurazione mittenti del sistema (`mittenti_email`).
