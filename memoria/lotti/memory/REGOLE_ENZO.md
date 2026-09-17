# Direttive permanenti di Enzo (Ceraldi Group) — da propagare a TUTTE le app

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Aggiornato: 02/07/2026. Queste regole valgono per Lotti, App dipendenti e
Gestionale Cloud: copiarle (con la cartella .claude/skills/) nei nuovi progetti.

## Prodotto e dominio
- Un solo punto d'ingresso fatture (cartella Drive condivisa); dedup sempre
  (fornitore+numero+data); mai doppioni/sistemi paralleli/codice morto.
- Prezzi SOLO da acquisti reali in fattura XML; ordini con totali veri:
  prezzo riga, aliquota IVA reale dall'XML, imponibile/IVA/totale che si
  ricalcolano a ogni variazione; PDF ordine con le stesse colonne.
- FIFO consuma sempre il lotto con data_fattura più vecchia; conversioni
  unità reali (uovo 60g, tuorlo 19g, albume 33g; pezzi↔kg via peso_pezzo).
- Matching prodotti: nome_mapping/dizionario_prodotti.nome_canonico.
- Magazzino: niente righe-nota (omaggi/riferimenti) come prodotti; soglia
  minima default 1 / quantità riordino 1; ogni riga d'ordine dice CHI l'ha
  inserita (dipendente, lavagna, riordino automatico, produzione, colazione).

- LE MANI SPORCHE (04/07/2026): il pasticcere/operatore ha SEMPRE le mani
  sporche — deve agire su automazioni e scelte pronte (tendine, chip, bottoni
  grandi), MAI usare la tastiera per scrivere. Ogni campo di testo libero nei
  flussi operativi (motivi, azioni correttive, note) va sostituito con un
  menù a tendina di opzioni predefinite + «Altro (scrivi tu)» come eccezione.
  Componente condiviso: frontend shared/SceltaMotivo.jsx (aggiungere lì le
  liste, non creare textarea nuove).

## Accessi
- PIN valido 2 ORE su tutte le pagine; Esci = blocco immediato.
- Dipendenti liberi ovunque TRANNE: impostazioni/PIN/personale, controllo
  dati, backoffice, configurazione, backup, stampanti (solo amministratore).
- Tablet condivisi: magazzino max 10 minuti di sessione.

## Design (design_handoff/)
- Salvia #5b7a6b + crema #faf7f0; MAI blu/indigo/viola; icone Lucide.
- Ogni pagina centrata, MAI scroll orizzontale su smartphone: tabelle → card.
- Coerenza con la Home/dashboard su tutte le pagine.

## Metodo di lavoro
- Italiano; risultati prima delle spiegazioni; ogni risposta operativa chiude
  con il link https://www.ceraldiapp.it (o l'app del progetto).
- Credenziali MAI in chat/codice/memoria: solo env Render; token/PIN mascherati.
- Dopo ogni modifica strutturale: aggiornare memoria (STATO.md), PR con CI,
  merge, VERIFICA LIVE. Le funzionalità si COLLAUDANO davvero (skill
  collaudo-funzionale), non si dichiarano "a posto" leggendo il codice.
- Guida operativa sempre aggiornata e scaricabile dall'app (skill
  guida-operativa); file di collaudo con link cliccabili a ogni pagina.
- Se non so risolvere un problema (bug raro, configurazione infrastrutturale,
  integrazione mai fatta prima): NON arrendersi e non inventare — cercare su
  GitHub/web come altri progetti reali risolvono esattamente quel problema,
  studiare la soluzione trovata e integrarla nel progetto (codice o
  istruzioni precise), invece di limitarsi a descrivere il problema.
