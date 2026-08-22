# PRODUCT.md — GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Aggiornato il 20/08/2026 sul codice corrente di `main`. Il commit esatto della
release viene verificato in CI e in produzione, senza fissarlo in questo file.

## Prodotto

Questo documento è una vista sintetica. La specifica normativa completa e
atomica è `PROMPT_MASTER.md`; in caso di divergenza prevale il master.

GestionaleCloud è l'ERP interno di Ceraldi Group S.R.L. Unisce documenti,
fatture, fornitori, Prima Nota, banca, fisco, personale, flotta e
riconciliazioni in un solo grafo operativo consultabile.

- Produzione: `https://impresasemplice.online`
- Repository: `ceraldicontabilita/GestionaleCloud`
- Utenti: amministrazione e team interno Ceraldi Group
- Perimetro fiscale predefinito: P.IVA `04523831214`

## Obiettivo

Ogni fatto economico deve essere acquisito una sola volta, conservare la
propria prova e risultare navigabile nelle sezioni collegate. Il gestionale
deve automatizzare i casi certi, mostrare le ambiguità e impedire duplicati e
scritture incoerenti.

```text
Documento originale
  -> entità amministrativa
     -> operazione canonica
        -> Prima Nota
           -> prova bancaria
              -> riconciliazione e stato finale
```

## Principi di prodotto

1. Una sola identità per operazione (`canonical_id` + `operation_id`).
2. Originali immutabili e provenienza sempre visibile.
3. Automatizzare soltanto corrispondenze certe e idempotenti.
4. Mostrare candidati e motivazione nei casi ambigui.
5. Un alert senza lista dei record interessati non è utile.
6. Le pagine collegate devono mostrare lo stesso stato senza ricaricamenti o
   manutenzioni manuali.
7. Drive/Sheets è l'unico archivio operativo portabile.

## Motore delle attese

Ogni fatto validato crea immediatamente le attese obbligatorie del proprio
flusso. Documenti e movimenti arrivati dopo sono evidenze: soddisfano un'attesa
esistente, non la inventano. Il processo è chiuso soltanto quando tutte le
attese obbligatorie sono `SODDISFATTO`, `NON_APPLICABILE` o `SUPERATO`.
Dettagli e test richiesti sono in `docs/REGOLA_FISSA_ATTESE.md`.

## Stato dell'architettura dati

Il codice usa un unico backend supportato in produzione:

- `sheets`: registro operativo su Google Sheets/Drive, con cache asincrona nel processo applicativo.

In produzione configurare sempre esplicitamente il registro Drive/Sheets. In modalità Sheets, la mancanza dell'ID del registro o della cartella Drive è un errore di configurazione. La migrazione storica è conclusa solo dopo copia completa, confronto conteggi/hash, ricostruzione e prova di scrittura; prima di allora i dati storici non si cancellano.

## Fonti dati per dominio

Il prodotto aggrega fatti economici e documentali da sorgenti diverse. Le
fonti operative sono queste:

- Documenti: upload manuale, cartelle Drive configurate, email autorizzate e API dei gestori.
- Fatture e fornitori: XML/P7M da Drive o SDI, anagrafiche e alias normalizzati.
- Prima Nota: fatture, corrispettivi, banca, versamenti contanti, POS, cedolini e F24.
- Riconciliazione: estratti conto, movimenti bancari, CRO/TRN, descrizioni normalizzate e riferimenti del gestore.
- Fisco: modelli F24, codici tributo, quietanze, dichiarazioni e cartelle Drive dedicate.
- Flotta e verbali: email autorizzate, verbali PDF, ZIP, contratti, storico assegnazioni e prove di pagamento.
- Corrispettivi e POS: XML RT, chiusure terminale, accrediti del gestore e commissioni separate.

Il criterio è invariabile: i documenti originali restano immutabili, gli
importi non bastano da soli a provare un'associazione e i casi ambigui devono
mostrare candidati, non collegamenti silenziosi.

Albero Drive previsto:

```text
Radice GestionaleCloud
├── REGISTRO DATI
│   └── Ceraldi ERP - Registro dati
├── PARTENOPAY
├── CODICI TRIBUTO
├── QUIETANZE
└── DICHIARAZIONI
```

Il registro contiene 23 archivi canonici espliciti e può includere gli altri
archivi logici scoperti nel database durante la migrazione. Ogni foglio ha un
progressivo proprio e conserva il payload ricostruibile.

## Albero funzionale

Il catalogo macchina contiene 66 schermate operative.

I riferimenti più delicati del catalogo sono:

- Coerenza POS: pagina 40, nel ramo Riconciliazione.
- Elaborazioni amministrative: pagina 56.
- Elaborazioni legacy: pagina 57.

```text
Ceraldi ERP
├── Accesso
│   ├── Login
│   └── Gestione riservata
├── Dashboard e inserimento
│   ├── Dashboard
│   └── Inserimento rapido
├── Fatture e fornitori
│   ├── Archivio fatture
│   ├── Corrispettivi
│   ├── Fornitori
│   └── Verifica fatture estere
├── Prima Nota e personale
│   ├── Prima Nota Cassa/Banca
│   ├── Pulizia e controllo duplicati
│   ├── Cedolini e salari
│   └── Ritenute
├── Flotta e verbali
│   ├── Flotta noleggio
│   ├── Verbali noleggio
│   ├── Dettaglio verbale
│   └── Riepilogo costi
├── Contabilità e fisco
│   ├── Piano dei conti e libro giornale
│   ├── Bilancio e verifica
│   ├── Controllo mensile e calendario fiscale
│   ├── IVA, F24, ritenute e situazione fiscale
│   ├── Cespiti, finanziaria, mutui e chiusura
│   └── Budget, utile, previsioni acquisti e dati ISA
├── Riconciliazione
│   ├── Banca e documenti
│   ├── F24 e stipendi
│   ├── Bonifici e assegni
│   ├── PayPal e PagoPA
│   ├── Coerenza POS
│   └── Movimenti banca
├── Documenti e Drive
│   ├── Import documenti
│   ├── Archivio documenti
│   ├── Indice documentale Drive
│   └── Atti amministrativi
├── Strumenti e integrazioni
│   ├── Verifica coerenza
│   ├── Commercialista, pianificazione e visure
│   ├── OpenAPI e mittenti email
│   ├── Learning Machine e agenti
│   └── Impostazioni F24/AI
├── HACCP e produzione
│   └── Tracciabilità, ricezioni, registri, ricette, produzioni e attrezzature
└── Amministrazione
    ├── Sistema e Registro Drive
    ├── MFA ed utenti
    └── Elaborazioni e batch
```

## Flussi principali

### Fattura fornitore

```text
Drive/SDI -> XML/P7M -> deduplica -> fornitore -> fattura
-> scadenza -> pagamento -> Prima Nota -> movimento banca -> riconciliata
```

### Corrispettivi e POS

```text
XML RT -> ricavo/cassa
SumUp API -> totale giornaliero -> trasferimento SumUp atteso
chiusura Numia manuale serale -> trasferimento Numia atteso
export storico Numia Drive -> deduplica + totale giornaliero -> trasferimento Numia atteso
accredito gestore -> riconciliazione del trasferimento
commissione -> costo separato
```

### Versamento contanti

```text
Versamento -> uscita Cassa + entrata Banca (stesso operation_id)
-> movimento estratto conto -> riconciliazione
```

### F24

```text
Modello F24 -> righe per codice tributo -> quietanza
-> movimento bancario -> stato riconciliato
```

### PartenoPay e verbali

```text
Email/ZIP -> verbale -> targa -> storico driver
-> pagamento/quietanza -> banca -> eventuale trattenuta
```

## Requisiti trasversali

- Import idempotente tramite hash e identità canonica.
- Relazioni bidirezionali navigabili.
- Importi contabili al centesimo e date utente in formato italiano.
- Prove distinte: documento, disposizione, ricevuta, quietanza, banca.
- Log di audit per ogni modifica significativa.
- Nessun pagamento automatico.
- Nessuna associazione definitiva ambigua.
- Nessuna eliminazione degli originali.

## Esperienza utente

- Interfaccia semplice, densa ma leggibile.
- Stato record visibile a colpo d'occhio.
- Azioni vicine al dato interessato.
- Rosso = errore, verde = verificato, oro = attenzione.
- Liste raggruppate per giorno quando la data è la chiave di lettura.
- Modali chiudibili da pulsante, overlay ed Escape, con documento leggibile.
- Desktop e mobile senza overflow; target touch minimo 44–48 px.
- La manutenzione tecnica resta in Admin e non sostituisce l'automazione.

## Non obiettivi

- Eseguire pagamenti in autonomia.
- Inventare classificazioni o legami mancanti.
- Considerare una quietanza equivalente al movimento bancario.
- Usare un importo come unica chiave di riconciliazione.
- Conservare per sempre un archivio operativo non portabile.
