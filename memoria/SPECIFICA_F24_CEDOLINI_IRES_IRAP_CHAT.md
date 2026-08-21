# Specifica definitiva — Motore contabilità, F24, cedolini, IRES, IRAP e Chat intelligente

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza vale l'architettura Drive/Sheets descritta nei documenti correnti; eventuali nomi di collection restano soltanto contesto storico.

## 1. Obiettivo

Il gestionale deve importare e interpretare:

- cedolini paga e Libro Unico del Lavoro;
- modelli F24;
- eventuali prospetti contributivi del consulente;
- dati di bilancio e prima nota;
- documenti INAIL e altri enti.

Lo scopo è:

1. classificare ogni importo;
2. distinguere costo economico, debito, credito, ritenuta, sanzione e pagamento;
3. associare correttamente gli F24 ai cedolini e ai periodi di competenza;
4. alimentare il calcolo IRES e IRAP;
5. rendere ogni valore tracciabile fino al documento originale;
6. consentire alla Chat intelligente di spiegare da dove deriva ogni importo.

---

## 2. Regola fondamentale sulle fonti

L'F24 elaborato dal consulente è il dato ufficiale per:

- importi versati;
- importi compensati;
- codici tributo;
- causali previdenziali;
- periodo di riferimento;
- saldo finale;
- data di pagamento.

Il Libro Unico e i cedolini sono invece la fonte principale per:

- retribuzioni lorde;
- TFR;
- tredicesima e quattordicesima;
- ferie e permessi;
- imponibili INPS, INAIL e IRPEF;
- trattenute individuali;
- qualifica, livello e tipologia contrattuale.

Il gestionale non deve sostituire il dato del consulente con un calcolo interno quando il documento ufficiale è disponibile.

---

## 3. Principio contabile da rispettare

Il saldo finale dell'F24 non coincide automaticamente con il costo deducibile.

Il modello F24 può contenere:

- ritenute IRPEF operate ai lavoratori;
- addizionali regionali e comunali;
- quote contributive a carico del lavoratore;
- quote contributive a carico del datore;
- crediti compensati;
- sanzioni;
- regolarizzazioni;
- premi INAIL;
- contributi di collaboratori e amministratori.

Le ritenute e le quote trattenute al lavoratore non sono un nuovo costo se la retribuzione lorda è già stata contabilizzata.

---

## 4. Estrazione dai cedolini

Per ogni cedolino il sistema deve estrarre almeno:

### Dati anagrafici e contrattuali

- nome e cognome;
- codice fiscale;
- matricola;
- data di assunzione;
- data di cessazione;
- qualifica;
- mansione;
- livello;
- tipo di contratto;
- tempo determinato o indeterminato;
- percentuale part-time;
- apprendistato;
- lavoro dipendente, collaborazione o amministratore;
- eventuali agevolazioni contributive.

### Competenze

Codici tipici:

| Codice | Descrizione | Trattamento |
|---|---|---|
| Z00001 | Retribuzione | Costo retributivo |
| Z00250 | Ferie godute | Componente retributiva |
| Z00255 | Permessi/ROL goduti | Componente retributiva |
| Z01100 | Festività godute | Componente retributiva |
| Z02014 | Assenza non retribuita | Riduzione competenze |
| Z50000 | Tredicesima | Costo retributivo |
| Z50022 | Quattordicesima | Costo retributivo |
| ZP9960 | Arrotondamento | Rettifica |
| ZP3040 | Contributo INAIL trattenuto, se presente | Trattenuta da classificare |

### Basi

- imponibile INPS;
- imponibile INAIL;
- imponibile IRPEF;
- retribuzione utile TFR;
- totale competenze;
- totale trattenute;
- netto del mese.

### Trattenute del lavoratore

| Codice | Descrizione |
|---|---|
| Z00000 | Contributo IVS lavoratore |
| Z00054 | Quota FIS lavoratore |
| Z00501 | Contributo IVS collaboratore |
| F03020 | Ritenuta IRPEF |
| F03325 | Imposta sostitutiva |
| F06020 | Ritenuta su tassazione separata/autonoma |
| F09110 | Addizionale regionale |
| F09130 | Addizionale comunale saldo |
| F09140 | Acconto addizionale comunale |
| F09150 | Trattenuta trattamento integrativo |

Queste voci devono essere registrate come debiti verso enti, non come ulteriori costi deducibili.

---

## 5. Importazione F24

Per ogni riga F24 il sistema deve memorizzare:

- sezione;
- codice tributo o causale;
- codice sede;
- matricola o posizione;
- codice Regione;
- codice Comune;
- mese e anno di riferimento;
- periodo da/a;
- importo a debito;
- importo a credito;
- saldo netto;
- data di pagamento;
- documento di origine;
- versione del documento;
- stato di associazione con cedolini e contabilità.

---

## 6. Codici Erario relativi al personale

| Codice | Descrizione | Classificazione |
|---|---|---|
| 1001 | Ritenute su retribuzioni | Debito verso Erario, non nuovo costo |
| 1002 | Ritenute su arretrati | Debito verso Erario |
| 1012 | Ritenute su cessazione/TFR | Debito verso Erario |
| 1701 | Credito trattamento integrativo | Credito compensabile |
| 8906 | Sanzioni sostituto d'imposta | Sanzione, non costo del personale |
| 6869 | Credito investimenti Mezzogiorno | Credito fiscale, non costo |

Il sistema deve poter gestire anche codici diversi, usando una tabella normativa aggiornata.

---

## 7. Regione

### Codice tributo 3802

Addizionale regionale IRPEF trattenuta dal sostituto d'imposta.

Classificazione:

- ritenuta del lavoratore;
- debito verso la Regione;
- non nuovo costo deducibile.

### Codice Regione

Il codice Regione deve essere memorizzato separatamente.

Esempio:

- 05 = Campania.

---

## 8. Comune

### Codice 3847

Addizionale comunale IRPEF — acconto.

### Codice 3848

Addizionale comunale IRPEF — saldo.

Classificazione:

- ritenute del lavoratore;
- debiti verso il Comune;
- non nuovi costi deducibili.

Codici catastali rilevati nei documenti:

- F839 = Napoli;
- B990 = Casoria.

Il sistema deve gestire più Comuni nello stesso F24.

---

## 9. INPS

### DM10

Contributi correnti dei lavoratori dipendenti.

### CXX

Gestione separata collaboratori.

### RC01

Regolarizzazione contributiva.

Regola:

Il totale della sezione INPS non deve essere considerato automaticamente tutto costo deducibile, perché può comprendere:

- quota datoriale;
- quota lavoratore;
- quota collaboratore;
- recuperi;
- conguagli;
- agevolazioni;
- periodi precedenti;
- sanzioni o accessori.

Il dato F24 è canonico per il pagamento. La quota di costo deve essere quella datoriale risultante dalla contabilità paghe o dal prospetto del consulente.

---

## 10. INAIL

La sezione INAIL usa i campi:

- codice sede;
- codice ditta;
- codice controllo;
- numero di riferimento;
- causale;
- debito;
- credito.

Causale tipica:

- P = pagamento premi e accessori INAIL.

Il premio INAIL a carico dell'impresa è costo deducibile secondo le regole fiscali e di competenza.

---

## 11. Classificazione automatica

Ogni riga deve ricevere:

- natura: costo / ritenuta / credito / sanzione / regolarizzazione / pagamento;
- ente: Erario / INPS / Regione / Comune / INAIL;
- competenza: mese e anno;
- data pagamento;
- deducibilità: sì / no / parziale / da verificare;
- origine: cedolino / F24 / prospetto consulente;
- codice;
- stato associazione;
- motivazione dell'associazione o del mancato aggancio.

---

## 12. Formula del costo del personale

Costo personale:

- retribuzioni lorde;
- quota contributiva INPS a carico dell'azienda;
- premio INAIL;
- TFR maturato;
- tredicesima e quattordicesima;
- fondi ed enti a carico dell'azienda;
- altri oneri obbligatori;
- meno sgravi e recuperi datoriali.

Non sommare nuovamente:

- netto pagato;
- IRPEF;
- addizionale regionale;
- addizionale comunale;
- IVS trattenuta al dipendente;

se la retribuzione lorda è già contabilizzata.

---

## 13. IRES

Formula:

Ricavi imponibili  
meno costi fiscalmente deducibili  
più/minus variazioni fiscali  
uguale imponibile IRES.

L'aliquota deve essere versionata per periodo d'imposta.

---

## 14. IRAP

Il motore IRAP deve essere separato dall'IRES.

Deve:

- partire dal valore della produzione;
- distinguere dipendenti, collaboratori e amministratori;
- distinguere tempo determinato, indeterminato, apprendistato e part-time;
- applicare le regole vigenti nell'anno;
- evitare di sottrarre automaticamente l'intero F24.

---

## 15. Regole di associazione F24 ↔ cedolini

Un F24 può essere associato ai cedolini solo quando sono verificati almeno i seguenti elementi:

1. stesso soggetto fiscale;
2. stesso periodo di riferimento;
3. stessa tipologia di personale o posizione contributiva;
4. presenza di causali coerenti;
5. assenza di indicazioni di regolarizzazione per periodi precedenti, salvo gestione separata;
6. corrispondenza tra mese/anno del cedolino e mese/anno riportato nelle righe F24;
7. eventuale tolleranza solo per la data di pagamento, che normalmente cade nel mese successivo.

### Esempio corretto

Cedolini di maggio 2026:

- periodo competenza: maggio 2026;
- F24 normalmente pagato a giugno 2026;
- righe F24 con periodo 05/2026;
- associazione consentita.

### Esempio non corretto

Cedolini di maggio 2026:

- F24 con periodo 11/2022;
- causale RC01;
- pagamento gennaio 2023;
- associazione vietata.

### Regola per la Chat intelligente

Quando l'utente chiede perché un F24 è stato associato o meno, la Chat deve rispondere mostrando:

- periodo dei cedolini;
- periodo indicato nell'F24;
- data di pagamento;
- causale;
- posizione/matricola;
- eventuale presenza di regolarizzazioni;
- esito finale;
- motivazione leggibile.

---

## 16. Gestione specifica dell'F24 con saldo €50,61

Dati:

- periodo prevalente: novembre 2022;
- causale INPS: RC01;
- pagamento: 16 gennaio 2023;
- ritenuta 1001: €1.382,12;
- sanzioni 8906: €36,56;
- crediti 6869: €5.024,76;
- INPS RC01: €2.840,00;
- Regione 3802: €410,71;
- Comuni 3847/3848: €405,98;
- saldo finale: €50,61.

Classificazione:

- €1.382,12: ritenute IRPEF;
- €36,56: sanzioni;
- €5.024,76: credito fiscale compensato;
- €2.840,00: regolarizzazione contributiva;
- €410,71: addizionale regionale;
- €405,98: addizionali comunali;
- €50,61: uscita finanziaria netta.

Questo F24 non è associabile ai cedolini di maggio 2026.

---

## 17. Chat intelligente

La Chat intelligente deve poter:

- leggere cedolini, F24 e prospetti;
- spiegare ogni codice tributo;
- mostrare la provenienza di ogni importo;
- distinguere costo, ritenuta, credito e pagamento;
- spiegare cosa è deducibile e cosa no;
- indicare perché un F24 è stato associato o escluso;
- evidenziare periodi non coerenti;
- segnalare regolarizzazioni, crediti e sanzioni;
- mostrare il documento origine e la pagina;
- non inventare mai aliquote o importi quando esiste il documento del consulente.

Esempio di risposta:

> Questo F24 non è stato associato ai cedolini di maggio 2026 perché riporta il periodo 11/2022, è stato pagato a gennaio 2023 e contiene la causale RC01, che identifica una regolarizzazione contributiva. I cedolini caricati sono invece relativi a maggio 2026. Il soggetto fiscale è lo stesso, ma il periodo di competenza non coincide.

---

## 18. Controlli obbligatori

Il sistema deve segnalare:

- F24 duplicati;
- periodo errato;
- causale sconosciuta;
- codice Regione mancante;
- codice Comune mancante;
- riga INAIL incompleta;
- credito trattato come costo;
- ritenuta trattata come nuova deduzione;
- saldo F24 trattato come costo;
- F24 associato a cedolini di periodo diverso;
- regolarizzazione imputata al mese corrente senza verifica;
- sostituzione di documenti senza versione storica.

---

## 19. Regola finale

L'F24 è la fonte ufficiale dei versamenti e delle compensazioni.  
Il cedolino è la fonte ufficiale del costo retributivo e delle trattenute individuali.  
L'associazione tra i due documenti deve avvenire solo quando periodo, causale, posizione e soggetto sono coerenti.  
La Chat intelligente deve spiegare sempre, in modo tracciabile, perché un documento è stato associato oppure escluso.


---

## 20. Gestione ravvedimenti, scadenza naturale e pagamento tardivo

### Regola RC01

Quando nella sezione INPS compare la causale **RC01**, il sistema deve interpretarla come una **regolarizzazione contributiva/ravvedimento riferito a un periodo precedente**, e non come un normale versamento corrente.

L'RC01 deve quindi essere collegato:

- al periodo contributivo indicato nel modello;
- all'eventuale F24 ordinario originario;
- alla data di scadenza naturale;
- alla data effettiva di pagamento;
- agli eventuali interessi, sanzioni o maggiorazioni;
- alla quietanza di pagamento.

Il sistema non deve imputare automaticamente l'intero RC01 come nuovo costo del mese in cui viene pagato.

### Scadenza naturale

Per le ritenute e i contributi relativi a una mensilità, la pagina deve calcolare e mostrare la scadenza naturale applicabile al documento.

Nel caso esaminato:

- periodo di competenza: **novembre 2022**;
- scadenza naturale: **16 dicembre 2022**;
- data effettiva di pagamento: **16 gennaio 2023**;
- ritardo: **31 giorni**;
- stato: **PAGATO IN RITARDO — RAVVEDIMENTO/REGOLARIZZAZIONE**.

Questi dati devono essere visibili nella pagina di dettaglio dell'F24.

### Colonne obbligatorie nella pagina F24

La tabella di visualizzazione deve contenere almeno:

| Colonna | Contenuto |
|---|---|
| Periodo di competenza | Mese e anno cui si riferisce il debito |
| Scadenza naturale | Data ordinaria prevista |
| Data effettiva di pagamento | Data risultante dalla quietanza o dal modello pagato |
| Giorni di ritardo | Differenza tra pagamento e scadenza |
| Stato pagamento | In scadenza / Pagato nei termini / Pagato in ritardo / Non pagato |
| Tipo versamento | Ordinario / Ravvedimento / Regolarizzazione |
| Causale INPS | DM10 / CXX / RC01 / altra |
| Documento collegato | F24 originario, F24 ravveduto, quietanza |
| Possibile duplicazione | Sì / No / Da verificare |
| Motivazione | Spiegazione automatica |

Lo stato **Pagato in ritardo** deve essere evidenziato graficamente e accompagnato dalla data di scadenza naturale e dalla data effettiva.

---

## 21. Relazione tra F24 ordinario DM10 e F24 con RC01

### Principio

Quando il sistema trova:

- un F24 ordinario con causale **DM10**;
- un F24 con causale **RC01**;
- stesso soggetto fiscale;
- stesso periodo di competenza;
- stessi tributi o tributi sostanzialmente corrispondenti;

non deve sommare automaticamente entrambi come due distinti costi o due distinti debiti.

L'ipotesi operativa è che l'RC01 rappresenti la regolarizzazione del debito originario.

### Controlli di collegamento

Il motore deve confrontare:

1. codice fiscale dell'azienda;
2. periodo di riferimento;
3. matricola INPS;
4. codice sede;
5. causale DM10/RC01;
6. codici Erario presenti;
7. codice Regione;
8. codici Comune;
9. importi originari;
10. differenze dovute a sanzioni, interessi o maggiorazioni;
11. data di presentazione;
12. data di pagamento;
13. quietanza disponibile.

### Regola anti-duplicazione contabile

Se l'F24 RC01 ripropone tributi già presenti nell'F24 ordinario, come:

- codice 1001;
- codice 3802;
- codici 3847 e 3848;
- altre ritenute riferite allo stesso periodo;

il sistema deve evitare che tali importi siano registrati due volte nel costo, nei debiti fiscali o nei pagamenti.

Le righe devono essere collegate al medesimo fascicolo mensile e classificate come:

- debito originario;
- regolarizzazione;
- sanzioni/interessi;
- pagamento originario;
- pagamento ravveduto.

### Importante

La sola presenza dello stesso mese non basta per dichiarare un duplicato. Il sistema deve effettuare il confronto completo dei campi sopra elencati.

---

## 22. Gestione delle quietanze

### Definizione

La quietanza è la prova dell'effettivo pagamento dell'F24.

Quando viene caricata una quietanza, il sistema deve:

- riconoscere che si tratta di una quietanza;
- estrarre data di pagamento;
- estrarre saldo addebitato;
- collegarla all'F24 corrispondente;
- cambiare lo stato da “presentato” a “pagato”;
- conservare il documento originale.

### Chiave di collegamento quietanza ↔ F24

Usare una combinazione di:

- codice fiscale;
- saldo finale;
- data;
- identificativo operazione;
- ABI/CAB;
- periodo;
- codici tributo;
- causali;
- eventuale numero protocollo.

---

## 23. Rilevazione del doppio pagamento

Se risultano pagati sia:

- l'F24 ordinario DM10;
- sia l'F24 RC01;

e i due documenti sono riferiti allo stesso debito originario, il sistema deve mostrare un alert:

> **POSSIBILE DOPPIO PAGAMENTO**

### Condizioni minime

L'alert deve attivarsi quando:

- stesso contribuente;
- stesso periodo;
- stesso debito o stessi tributi principali;
- entrambe le quietanze risultano pagate;
- gli importi non rappresentano chiaramente solo sanzioni, interessi o differenze;
- non esiste una compensazione o uno storno che giustifichi il secondo pagamento.

### Informazioni da mostrare

- F24 ordinario;
- F24 RC01;
- relative quietanze;
- data del primo pagamento;
- data del secondo pagamento;
- importi pagati;
- quota potenzialmente duplicata;
- quota riferibile a sanzioni/interessi;
- livello di affidabilità dell'anomalia;
- richiesta di verifica al consulente.

### Stati dell'anomalia

- Da verificare;
- Confermato doppio pagamento;
- Non duplicato — sola regolarizzazione;
- Rimborsato/compensato;
- Chiuso dal consulente.

---

## 24. Comportamento della Chat intelligente su ravvedimenti e duplicazioni

La Chat intelligente deve poter rispondere, per esempio:

> L'F24 è riferito a novembre 2022. La scadenza naturale era il 16 dicembre 2022, mentre il pagamento risulta effettuato il 16 gennaio 2023, con 31 giorni di ritardo. La causale RC01 indica una regolarizzazione contributiva. Il documento è quindi classificato come pagato in ritardo.

Oppure:

> Ho trovato un F24 ordinario DM10 e un F24 RC01 riferiti allo stesso periodo. Non ho sommato automaticamente gli importi perché l'RC01 può essere la regolarizzazione del debito originario. Sto confrontando codici tributo, matricola, periodo e quietanze.

Oppure:

> Entrambi i modelli risultano pagati e sono riferiti allo stesso debito. È stata rilevata una possibile duplicazione di pagamento. Occorre verificare con il consulente se il secondo versamento comprende soltanto sanzioni e interessi oppure se il capitale è stato versato due volte.

La Chat deve sempre distinguere tra:

- duplicazione documentale;
- duplicazione contabile;
- doppio pagamento effettivo;
- semplice ravvedimento;
- pagamento di sole sanzioni/interessi.


---

## Caso 3

Esiste solo la Quietanza

↓

Non ricostruire automaticamente il modello F24.

Il sistema deve mostrare nella pagina F24 un alert bloccante:

> **F24 mancante — prego caricare il modello F24 corrispondente.**

La quietanza deve essere registrata come prova di pagamento non ancora associata, con stato:

- Quietanza presente;
- F24 mancante;
- associazione incompleta;
- calcolo fiscale sospeso per le voci non classificabili senza il modello originario.

La Chat intelligente deve spiegare che la quietanza conferma il pagamento, ma non sostituisce il modello F24 ai fini della classificazione completa di codici, causali, crediti, periodi e collegamenti contabili.
