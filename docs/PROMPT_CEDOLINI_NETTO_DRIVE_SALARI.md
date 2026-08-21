# Prompt operativo - Cedolini, netto pagabile, Drive e Salari

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

```text
Correggi e rendi verificabile l'intero flusso cedolini di GestionaleCloud usando
Google Drive come archivio canonico dei PDF e la pagina `/salari` come vista
contabile dei soli importi dimostrati.

============================================================
1. VERIFICA INIZIALE
============================================================

- Sincronizza il repository canonico `ceraldicontabilita/GestionaleCloud` e
  verifica `origin/main`, stato locale, test e configurazione Drive corrente.
- Preserva tutte le modifiche locali non pertinenti.
- Riusa `Documenti`, la pipeline cedolini, `prima_nota_salari`, la pagina
  `/salari` e gli indici Drive esistenti; non creare un archivio parallelo.
- Non usare filename, importi vicini, OCR isolato o dati aggregati come prova
  del netto del cedolino.

============================================================
2. REGOLA CANONICA PER IL NETTO
============================================================

Il netto pagabile deve provenire esclusivamente dalla cella graficamente
associata a una delle etichette canoniche del cedolino, per esempio:

- `TOTALE NETTO`;
- `NETTO DEL MESE`;
- `NETTO IN BUSTA`, se presente nel modello verificato.

La lettura deve usare posizione e struttura della pagina PDF, non soltanto
l'ordine del testo estratto.

Non confondere mai il netto con:

- `ARR. PREC.` o `ARR. ATTUALE`;
- totale competenze o totale trattenute;
- detrazioni, ritenute, imponibili, TFR o fringe benefit;
- arrotondamenti;
- un numero vicino alla parola `NETTO` ma collocato in un'altra colonna;
- un importo già presente nel nome del file.

Se la cella del netto è vuota, il valore deve restare nullo. Non sostituirlo
con zero e non scegliere il candidato numerico più vicino.

============================================================
3. STATI OBBLIGATORI
============================================================

Ogni PDF deve ricevere uno dei seguenti stati espliciti:

- `NETTO_VERIFICATO_DA_CEDOLINO`: un solo importo nella cella canonica;
- `NETTO_NON_PRESENTE_O_NON_LEGGIBILE`: cella vuota, PDF non leggibile o
  modello non riconosciuto;
- `MULTIPLE_NETS_DA_VERIFICARE`: più netti legittimi nello stesso PDF;
- `ERRORE_PARSER`: errore tecnico con dettaglio auditabile.

Soltanto `NETTO_VERIFICATO_DA_CEDOLINO` può alimentare automaticamente Salari
e la tabella dei bonifici da assegnare.

============================================================
4. NOMI FILE E INDICE DRIVE
============================================================

Per un netto verificato usa:

`Nome Dipendente - YYYY-MM - EUR 1.234,56.pdf`

Per una cella vuota o non leggibile usa:

`Nome Dipendente - YYYY-MM - NETTO NON PRESENTE.pdf`

Non rinominare un documento ambiguo con un importo non verificato.

Ricrea `INDICE_CEDOLINI_PAGA.xlsx` con le sole colonne:

`employee | source | year | month | net_amount | net_candidates | status`

Requisiti dell'indice:

- `source` deve essere un collegamento cliccabile al file Drive tramite ID
  stabile, mai un percorso locale Windows;
- `net_amount` deve essere numerico soltanto per i netti verificati;
- `net_candidates` serve esclusivamente per la revisione dei casi multipli;
- il nome del PDF non è una fonte per calcolare `net_amount`;
- rinominare il file non deve rompere il collegamento Drive.

============================================================
5. SALARI E BONIFICI DA ASSEGNARE
============================================================

Ricrea `SALARI_E_BONIFICI_DA_ASSEGNARE.xlsx` con:

1. `Indice`: tutte le righe e i relativi stati;
2. `Salari`: soltanto netti verificati, con collegamento Drive al PDF;
3. `Bonifici da assegnare`: somma dei netti verificati per dipendente, anno e
   mese, mantenendo il numero dei cedolini sorgente.

La tabella `Bonifici da assegnare` è una proposta di importo dovuto. Non è una
prova di pagamento e non deve impostare automaticamente:

- bonifico eseguito;
- movimento bancario;
- data pagamento;
- riconciliazione bancaria;
- stato pagato.

Lo stato iniziale deve restare `DA_ASSEGNARE`. Un pagamento diventa verificato
soltanto tramite una prova bancaria reale e un collegamento bidirezionale
auditabile.

============================================================
6. DEDUPLICAZIONE
============================================================

- Il duplicato documentale certo richiede uguaglianza dell'hash del PDF.
- Dipendente, mese e importo uguali non bastano a eliminare un cedolino: nello
  stesso periodo possono esistere mensilita aggiuntive, arretrati, conguagli o
  documenti distinti.
- Conserva sempre file originale, ID Drive, hash, percorso sorgente e motivo
  della decisione.
- Ogni eliminazione deve essere recuperabile e registrata; non eliminare file
  soltanto per somiglianza del nome.

============================================================
7. CONTROLLI PRIMA DELL'IMPORTAZIONE
============================================================

Prima di scrivere in produzione:

- ricontrolla visivamente almeno un campione per ogni modello grafico;
- verifica che un netto vuoto non produca alcun importo;
- verifica che `ARR. ATTUALE` e `ARR. PREC.` siano sempre esclusi;
- confronta numero PDF, righe indice, netti verificati, casi multipli e casi
  non leggibili;
- verifica tutti i collegamenti Drive;
- verifica assenza di duplicati per hash;
- esegui test automatici su layout con netto valorizzato, netto vuoto,
  simbolo valuta corrotto nel testo estratto e PDF multipagina;
- mostra conteggio, totale e impatto all'utente;
- richiedi conferma immediatamente prima di trasmettere dati retributivi
  personali al gestionale di produzione.

In caso di dubbio, blocca l'importazione e conserva il documento in revisione.
È preferibile un importo nullo dichiarato a un importo plausibile ma inventato.
```
