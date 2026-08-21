# Fornitori — regola canonica

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

L'anagrafica fornitori vive nel foglio logico `Fornitori` del registro
Drive/Sheets. Il nome tecnico compatibile usato dall'adapter è `fornitori`, ma
la logica applicativa non deve dipendere dal supporto fisico.

## Identità

Ordine di autorità:

1. partita IVA normalizzata;
2. codice fiscale normalizzato;
3. identificativo esterno verificato;
4. alias/ragione sociale normalizzati come supporto, mai come unica prova in
   caso di omonimia.

Il `canonical_id` del fornitore è stabile. Rinominare la ragione sociale non
crea una seconda anagrafica.

## Campi minimi

- progressivo del foglio;
- `canonical_id`;
- partita IVA e codice fiscale come testo;
- ragione sociale corrente;
- alias conosciuti;
- contatti e coordinate di pagamento verificate;
- metodo di pagamento previsto;
- riferimenti bancari/SDD/PayPal riconosciuti;
- stato attivo/cessato;
- origine, hash o documento fonte e data aggiornamento.

## Import e aggiornamento

Prima di inserire un fornitore, il sistema cerca l'identità fiscale e poi gli
alias. Se trova un record certo lo aggiorna e aggiunge la provenienza; non crea
un duplicato. Dati discordanti vengono mostrati come conflitto.

Le API continuano a esporre il dominio fornitori (`/api/suppliers` e router
correlati) indipendentemente dal backend selezionato.

## Relazioni contabili

- Fatture, pagamenti, documenti e movimenti bancari puntano al medesimo
  `fornitore_id` canonico.
- Un riferimento SDD o conto PayPal può diventare una regola verificata del
  fornitore.
- La corrispondenza per importo da sola non è sufficiente.
- Se più fatture sono compatibili, mostrare `Scegli fattura`.
- Una fusione di duplicati mantiene alias, ID precedenti, provenienza e audit.

## Migrazione

Eventuali riferimenti storici a legacy DB sono conservati solo come contesto. La destinazione è il foglio `Fornitori` su Drive/Sheets. La migrazione e la verifica devono usare copie e dump verificati in Drive/Sheets: conteggi, identità fiscale, relazioni e capacità di ricostruzione vanno provati esclusivamente con `DATA_BACKEND=sheets`.
