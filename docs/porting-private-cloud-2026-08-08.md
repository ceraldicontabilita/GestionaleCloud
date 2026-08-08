# Porting verificato Private -> GestionaleCloud

## Esito

Il repository canonico e' `ceraldicontabilita/GestionaleCloud`, branch `main`.
Il repository `GestionaleCloud-Private` e' stato usato soltanto come sorgente da
confrontare. Non sono stati copiati database, credenziali, documenti reali o
interi router.

## Portato nel Cloud

- `pagamenti_buoni`: registro incrementale importato esclusivamente da
  `Documenti -> upload-auto` quando il CSV contiene le dieci colonne canoniche.
  Il riferimento operazione e' unico; una riga senza riferimento resta
  `da_verificare` e non viene associata automaticamente a un dipendente o a un
  movimento contabile.
- Export AppDipendenti in `Prima Nota -> Cedolini salari`: ZIP con i PDF binari
  originali in `export_cedolini/`, `prima_nota_salari.xlsx` e
  `storico_pagamenti.xlsx`. L'export e' di sola lettura e non modifica la
  riconciliazione.

## Non copiato

Cedolini, bonifici, estratti conto, F24, IVA, POS, fornitori, Prima Nota e
reporting hanno gia' implementazioni canoniche nel Cloud, piu' aggiornate e con
regole di provenienza proprie. Copiare le versioni Private avrebbe creato
doppioni e avrebbe disallineato le collezioni.

## Endpoint aggiunti

- `GET /api/pagamenti-buoni?year=YYYY`
- `POST /api/pagamenti-buoni/import` (API tecnica; il percorso operativo resta
  Documenti)
- `GET /api/prima-nota-salari/export-appdipendenti/preview`
- `GET /api/prima-nota-salari/export-appdipendenti/download`

La deduplicazione per file sorgente usa la provenienza `documents_inbox`; la
deduplicazione delle righe usa `transfer_reference`. Nessuna inferenza per
importo solo.
