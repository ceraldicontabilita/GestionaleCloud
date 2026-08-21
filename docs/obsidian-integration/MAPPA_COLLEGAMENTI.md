# Mappa dei collegamenti

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

## Aree e dossier

| Area | Note generate | Relazioni principali | Dashboard utili |
| --- | --- | --- | --- |
| Aziende | anagrafica, sedi, ruoli, contatti | documenti, banche, immobili, personale | dati mancanti, scadenze |
| Fornitori | anagrafica, contratti, comunicazioni | fatture, pagamenti, bonifici, PEC | fatture non pagate, documenti mancanti |
| Clienti | anagrafica, attività, comunicazioni | fatture emesse, incassi, contratti | scaduti, attività aperte |
| Contabilità | fatture, prima nota, riconciliazioni | soggetti, pagamenti, movimenti | pagamenti senza fattura, fatture senza prova |
| Fiscalità | F24, quietanze, dichiarazioni, tributi, IVA | PDF, banca, periodo, codice tributo | F24 senza quietanza, scadenze fiscali |
| Banche | conti e movimenti selezionati | pagamenti, fatture, F24, stipendi | non riconciliati, conflitti |
| Personale | fascicolo dipendente, ruoli e periodi | contratti, cedolini, pagamenti, veicoli | documenti mancanti, scadenze |
| Veicoli | targa, proprietà, utilizzi | driver, verbali, manutenzioni, assicurazioni | documenti in scadenza, verbali aperti |
| Immobili | fascicolo tecnico e amministrativo | utenze, fornitori, lavori, autorizzazioni | manutenzioni e rinnovi |
| Atti amministrativi | pratica e timeline | PEC, ente, documenti, pagamento | pratiche aperte e da verificare |
| Documenti | metadati e provenienza | soggetto, pratica, entità elaborata | errori, OCR debole, duplicati |
| Procedure | SOP, checklist e runbook | pagina Gestionale, ruolo responsabile | procedure da revisionare |
| Automazioni | run, errori e heartbeat | sorgenti, documenti prodotti, notifiche | job falliti o in ritardo |
| Normativa | fonti ufficiali e data di acquisizione | procedura, tributo, pratica | fonti da ricontrollare |

## Collegamenti minimi obbligatori

### Documento

- sorgente e provenienza;
- hash esatto;
- soggetto;
- pratica o entità elaborata;
- eventuali duplicati esatti;
- pagina autenticata del Gestionale.

### Fattura

- fornitore o cliente;
- documento originale;
- registrazione contabile;
- pagamento documentale;
- movimento bancario confermato;
- eventuali anomalie.

### F24

- modello canonico;
- righe tributo;
- periodo;
- quietanza documentale;
- movimento bancario distinto;
- dichiarazione compatibile.

### Dipendente

- identificatore stabile;
- contratto e periodo;
- cedolini distinti;
- pagamenti e prove;
- veicoli assegnati nei relativi intervalli.

### Veicolo

- targa normalizzata;
- driver e intervalli di assegnazione;
- assicurazione e revisioni;
- manutenzioni;
- verbali e pagamenti.

### Pratica amministrativa

- ente;
- protocollo;
- comunicazioni PEC;
- documenti;
- scadenze;
- stato e responsabile;
- pagamenti o ricevute senza confonderli con la prova bancaria.

## Pagine trasversali

- `Home aziendale`
- `Oggi`
- `Prossimi 7 giorni`
- `Prossimi 30 giorni`
- `Da verificare`
- `Documenti non elaborati`
- `Associazioni ambigue`
- `Pagamenti con prove parziali`
- `Job automatici`
- `Decisioni recenti`
- `Procedure da revisionare`
