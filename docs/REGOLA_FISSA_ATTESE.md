# Regola fissa — fatti, obblighi, attese ed evidenze

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Questa regola è obbligatoria per ogni pagina, import, job, router e servizio di
GestionaleCloud.

## Regola centrale definitiva

Quando entra un fatto validato da una fonte autorevole, il sistema crea subito
tutti gli obblighi e tutte le attese obbligatorie che quel fatto comporta. Una
prova arrivata dopo non crea retroattivamente l'attesa: può soltanto
soddisfarla, lasciarla aperta oppure segnalarla come ambigua.

```text
FONTE
  -> DOCUMENTO
  -> CLASSIFICAZIONE
  -> FATTO CANONICO
  -> OBBLIGHI
  -> EXPECTATION
  -> EVIDENZE FUTURE
  -> RICONCILIAZIONE
  -> PRIMA NOTA
  -> CONTABILITA
  -> CONTROLLO
  -> CHIUSURA
```

Ogni fatto ha un solo owner autorevole. Ogni attesa conserva tipo, owner,
`source_fact_id`, `operation_id`, stato ed evidenze collegate. Tutte le
relazioni sono bidirezionali e auditabili.

## Stati obbligatori

Stati aperti:

- `ATTESO`
- `DA_VERIFICARE`
- `IN_ELABORAZIONE`
- `ERRORE`

Stati terminali positivi:

- `SODDISFATTO`
- `NON_APPLICABILE`
- `SUPERATO`

Un processo è chiuso soltanto quando ogni sua attesa obbligatoria è in uno
stato terminale positivo. `ERRORE` non chiude il processo e non equivale a
`NON_APPLICABILE`.

## Regola di acquisizione

- successo: originale conservato, fatto indicizzato e instradato nel dominio;
- errore tecnico: originale conservato in `Errori`, stato `ERRORE` e dettaglio;
- classificazione ambigua: originale in `Da elaborare`, stato
  `DA_VERIFICARE`, candidati visibili e nessun ciclo automatico infinito;
- elaborazione completata: stato nel registro e collocazione `Elaborate` senza
  eliminare o sovrascrivere l'originale.

Upload, Drive ed email devono passare dalla stessa pipeline idempotente.

## Applicazione per dominio

- Fattura fornitore: crea debito, scadenza, metodo atteso, pagamento atteso e
  relative attese documentali/finanziarie.
- Fattura cliente: crea credito, scadenza e incasso atteso.
- Corrispettivo RT/POS: crea giornata fiscale, ricavo, IVA, quota contanti,
  chiusure Numia/SumUp, credito per gestore, accredito bancario atteso,
  commissioni attese e controlli RT-POS-banca.
- Movimento bancario/carta: è evidenza; cerca attese esistenti e non inventa
  fatture, chiusure POS, pagamenti o obblighi mancanti.
- F24: crea attese di quietanza e prova bancaria distinte.
- Cedolino: crea netto dovuto, bonifico atteso, prova bancaria e registrazione
  contabile; la regola del periodo non inventa un cedolino futuro.
- ADER/PagoPA: collega atto, avviso, ricevuta e banca come prove separate.
- Assegno/bonifico/PayPal: conserva l'identità propria e soddisfa soltanto
  debiti o attese deterministiche.
- Noleggio/verbale: collega contratto, targa e driver valido alla data; crea
  pagamento e quietanza attesi senza dedurre il driver dall'intestatario.
- Finanziamento soci: distingue ogni movimento bancario reale tramite identità,
  data e riferimento; l'importo ricorrente non è un duplicato.

## Vincoli POS non negoziabili

La fonte terminale Numia/SumUp è owner della chiusura e crea immediatamente la
coppia con un solo `operation_id`:

```text
Prima Nota Cassa: uscita POS del circuito
Prima Nota Banca: credito gestore / accredito atteso
```

L'estratto conto raggruppa le componenti dello stesso giorno vendita letto
dalla causale `DEL gg/mm/aa` (`NUMIA-AMEX`, `NUMIA-INTER`, `NUMIA-BNCMT`,
`NUMIA-PGBNT`), ne somma l'importo al centesimo e soddisfa l'attesa esistente.
Se l'attesa manca o ce ne sono più di una, le righe bancarie restano
`DA_VERIFICARE`; la banca non crea la chiusura terminale mancante.

Commissioni, fatture del gestore e spese con carta sono fatti distinti e non
entrano nel totale dell'accredito POS.

## Criterio di accettazione

Per ogni modifica deve esistere almeno un test che dimostri:

1. il fatto autorevole crea le attese prima delle prove future;
2. il reimport non duplica né il fatto né le attese;
3. la prova certa soddisfa l'attesa e conserva gli ID delle evidenze;
4. prova assente, discordante o ambigua non crea dati mancanti;
5. la chiusura fallisce finché esiste un'attesa obbligatoria aperta.

## Provenienza della regola

Regola consolidata il 21/08/2026 dai materiali forniti dall'utente:

- albero JSON, SHA-256
  `BA26ED5419258C766AF130FB0460AC3AF977914E5716B5E316B1FBDDE1FF4DFE`;
- albero HTML, SHA-256
  `C2ED6696B43B7E0E37E114CD08117BEB507AC5082E2ED3EC0D5E62AB68D925CD`;
- regola centrale testuale, SHA-256
  `B641ACDC39B13D8BB183AD3D5F17B83F7A1EC8E2CCE06FC0794F9E755328979A`.

I materiali descrivono la regola; codice, test e configurazione corrente
restano l'autorità eseguibile.
