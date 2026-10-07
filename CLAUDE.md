# Istruzioni per Claude — GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-10-06
storage_architecture: supabase
consolidated_source: single-claude-md
-->

Repository canonico:

`ceraldicontabilita/GestionaleCloud`

Produzione:

`https://gestionalecloud.onrender.com`

---

# 1. Scopo di questo file

Questo file è la **fonte normativa del repository**.

Contiene:

1. regole architetturali;
2. regole di dominio;
3. comportamento che il codice deve rispettare;
4. stato di produzione realmente verificato;
5. incoerenze note;
6. lavoro ancora aperto.

Il `README.md` è soltanto una guida d'ingresso.

Il codice, i test, le migrazioni realmente applicate e la configurazione live vincono sempre sulla documentazione.

Se codice e questo file non concordano:

- verificare quale sia la realtà;
- correggere il codice se viola una regola;
- correggere questo file se descrive uno stato non più vero;
- fare entrambe le modifiche nello stesso intervento quando necessario.

Non creare altri documenti permanenti di stato, audit, roadmap o memoria.

La cronologia delle modifiche appartiene a Git.

---

# 2. Come leggere questo file

Ogni area distingue sempre tre concetti.

## REGOLA

Comportamento vincolante del sistema.

## PRODUZIONE

Ciò che risulta realmente attivo e verificato.

## APERTO

Ciò che non rispetta ancora completamente la regola o deve essere completato.

Non trasformare una voce di **APERTO** in realtà acquisita.

Non descrivere come esistente una migrazione che non è stata ancora applicata in produzione.

---

# 3. Principio architetturale fondamentale

GestionaleCloud deve convergere verso:

- un solo servizio;
- una sola fonte autorevole per ogni fatto;
- un solo writer per ogni fatto;
- un solo motore per ogni regola;
- identificatori stabili;
- relazioni esplicite;
- proiezioni rigenerabili;
- nessuna duplicazione di logica;
- nessun dato inventato.

La cartella in cui si trova il codice non assegna la proprietà del dato.

La proprietà appartiene al dominio.

---

# 4. Domini canonici

| Dominio | Possiede |
| --- | --- |
| ERP / Finanza | fatture, righe fatture, fornitori commerciali, movimenti bancari, pagamenti, incassi, contabilità, fiscalità |
| HR / Persone | persona, dipendente, rapporto di lavoro, presenze, turni, ferie, payroll, cedolino |
| Lotti / Operazioni | ricette tecniche, ingredienti, produzione, lotto, giacenza, HACCP, firme operative |
| Catalogo / Menu | prodotto commerciale, categoria, immagine, prezzi, disponibilità per canale, allergeni pubblicati |
| B&B / Hospitality | struttura, soggiorno, wallet, voucher, utilizzi, extra, recensioni, richieste fiscali |
| Piattaforma | identità tecnica, sessione, audit, documenti, relazioni, job, notifiche, errori, outbox |

Gli altri domini possono:

- leggere;
- collegare un ID;
- ricevere una proiezione;
- ricevere un evento idempotente.

Non devono copiare il fatto canonico.

---

# 5. Identificatori

Identificatori condivisi:

- `person_id`
- `employee_id`
- `supplier_id`
- `product_id`
- `document_id`
- `invoice_id`
- `invoice_line_id`
- `transaction_id`

Gli identificativi nuovi devono nascere dal proprietario canonico.

Preferire UUID, identity o sequence del database.

Mai:

`max(id) + 1`

## APERTO

Le fatture storiche contengono ancora ID numerici e testuali.

Finché la migrazione non è completata usare esclusivamente gli helper canonici che gestiscono entrambe le varianti.

Non introdurre nuovo codice che presuma un solo tipo storico di `invoice_id`.

## PRODUZIONE

Gli id di `menu.menu_categories`, `menu_subcategories` e `menu_products` nascono dal database (identity BY DEFAULT, migrazione `20261007051337_menu_id_dal_database` applicata il 07/10/2026). Ponte Lotti e admin Menu inseriscono senza id tramite `app/menu/supabase_client.py::inserisci_con_id_del_database`; nessun ripiego su `max(id)+1`.

---

# 6. Un solo servizio

## REGOLA

Un unico servizio Render serve l'intero gruppo.

Host principale:

`https://gestionalecloud.onrender.com`

Dominio alternativo:

`impresasemplice.online`

Applicazioni:

| Area | Rotta | Codice |
| --- | --- | --- |
| ERP | `/` | `app/` + `frontend/` |
| HR | `/hr`, `/hr/portale` | `app/hr/` + `frontend_hr/` |
| Menu | `/menu`, `/menu/admin` | `app/menu/` + `frontend_menu/` |
| Lotti | `/lotti` | `app/lotti/` + `frontend_lotti/` |
| B&B / Colazioni | `/convenzioni/` | `frontend_colazioni/` + API/RPC esistenti |

Il vecchio `/colazioni` reindirizza a `/convenzioni`.

Il catch-all della SPA ERP deve essere registrato dopo le sotto-app.

Il prefisso nudo di un `Mount` deve essere reindirizzato alla versione con `/`.

---

# 7. Repository

Repository vivo:

`https://github.com/ceraldicontabilita/GestionaleCloud`

Checkout canonico Windows del titolare:

`C:\Users\ceral\Documents\GESTIONALE CLOUD 2`

Vecchi repository non sono fonti vive.

Non riattivare sistemi paralleli.

Prima di intervenire:

1. confrontare `HEAD` con `origin/main`;
2. controllare modifiche locali;
3. non cancellare lavoro non proprio;
4. non includere file estranei.

Mai:

`git add -A`

Aggiungere solo i file pertinenti.

---

# 8. Metodo di lavoro

- Rispondere e ragionare in italiano.
- Risultati prima delle spiegazioni.
- Correggere i difetti trovati, non limitarsi a descriverli.
- Procedere per micro-tranche verificabili.
- Non riscrivere l'intero sistema in una volta.
- Prima di eliminare un percorso controllare import statici e dinamici, route, frontend, job, API e dati persistiti.
- Un test che cita un modulo non dimostra che il modulo sia raggiungibile in produzione.
- Una risposta HTTP 200 non dimostra che il flusso funzioni.
- Testare dati, relazioni, deduplica e stato finale.
- Quando serve una scelta del titolare, proporre opzioni e mettere per prima quella consigliata.
- Chiudere il lavoro con verifica live quando possibile e sicura.

---

# 9. Supabase e Drive

## REGOLA

Supabase è l'archivio strutturato applicativo.

Backend ammesso:

`DATA_BACKEND=supabase`

Schemi principali:

- `gestionale`
- `hr`
- `lotti`
- `menu`

`legacy_staging` è transitorio.

Google Drive conserva gli originali documentali.

Drive non è il database.

Sintesi:

`Supabase = dati, stato e relazioni`

`Drive = originali documentali`

---

# 10. Migrazioni database

Ogni migrazione realmente applicata deve esistere in:

`supabase/migrations/`

La versione deve corrispondere al registro reale delle migrazioni.

Non inventare numeri di versione.

Il repository deve permettere di ricostruire il database.

DDL pesanti su `gestionale.documents`:

- a database scarico;
- oppure con strategie non bloccanti quando possibili.

Una modifica dello schema può invalidare temporaneamente la cache PostgREST.

## APERTO

Esistono strutture/migrazioni Cassa e Catalogo applicate al database che devono ancora essere esportate correttamente nel repository.

Questa incoerenza va eliminata.

---

# 11. Cache e prestazioni

Le liste e i conteggi devono usare proiezioni leggere.

Il payload completo si legge per ID.

Mai caricare l'intera collezione con payload se non strettamente necessario.

Per un'intera collezione:

- un prefetch;
- calcolo in background;
- stato in `sistema_stato`;
- operazione riprendibile se lunga.

Il puro calcolo CPU lungo non deve bloccare l'event loop.

Usare thread per parsing o calcolo CPU quando necessario.

Un job superiore al timeout del proxy non deve vivere dentro una richiesta sincrona.

---

# 12. Importi, date e codici

- Importi: `Decimal`.
- Mai `float` per denaro.
- Valuta esplicita.
- Backend date: ISO-8601.
- UI: `gg/mm/aaaa`.
- Scheduler: `Europe/Rome`.
- Codici tributo, IUV e codici avviso: stringhe.
- Mai convertire identificatori con zeri iniziali in numeri.
- Dato sconosciuto: `None` / vuoto / “Dato non disponibile”.
- Mai inventare uno zero.

---

# 13. Errori

Le API devono restituire quando applicabile:

- `code`
- `message`
- `details`
- `correlation_id`

`except Exception: pass` è vietato dove si contano soldi.

Il log deve contenere almeno:

- tipo eccezione;
- contesto;
- dato o record coinvolto quando sicuro.

Non affidarsi solo a `str(exc)`.

---

# 14. Cancellazioni e storico

Un fatto amministrativo non scompare senza storia.

Preferire:

- storno;
- quarantena;
- revoca;
- sostituzione;
- `rimosso`;
- `archived`.

Un file sparito da Drive deve diventare `rimosso`, quando il protocollo ha realmente la capacità di rilevarlo.

Una scrittura contabile sbagliata si storna.

Non si cancella.

Nessuna cancellazione massiva per filtro.

Le cancellazioni reali richiedono i meccanismi protetti previsti.

---

# 15. Catena canonica dei fatti

Ogni flusso economico deve convergere a:

DOCUMENTO  
↓  
FATTO CANONICO  
↓  
OBBLIGO / CREDITO  
↓  
PAGAMENTO  
↓  
PROVA  
↓  
SCRITTURA CONTABILE  
↓  
RICONCILIAZIONE  
↓  
PROIEZIONE / UI

Ogni passaggio deve usare ID reali e relazioni persistenti.

Non rappresentare un processo complesso con booleani scollegati.

---

# 16. Prove e documenti

Fattura, disposizione, quietanza, ricevuta e movimento bancario sono prove diverse.

Un PDF di bonifico dimostra una disposizione/documentazione.

Non dimostra automaticamente l'addebito sul conto.

La prova bancaria è il movimento compatibile dell'estratto ufficiale.

Una prova successiva non deve creare l'obbligo che dovrebbe dimostrare.

L'obbligo nasce dal fatto autorevole.

---

# 17. Stati delle attese

Stati aperti:

- `ATTESO`
- `DA_VERIFICARE`
- `IN_ELABORAZIONE`
- `ERRORE`

Stati terminali positivi:

- `SODDISFATTO`
- `NON_APPLICABILE`
- `SUPERATO`

`ERRORE` non chiude il processo.

Ogni attesa deve avere:

- tipo;
- owner;
- `source_fact_id`.

La prova ambigua non inventa un collegamento.

---

---

# 17A. Regola generale del motore di riconciliazione

> **Contratto comune.** Le regole di questa sezione valgono per tutti i domini di riconciliazione. Quando una sezione specialistica successiva è più restrittiva o usa una prova più forte, prevale la regola specialistica. Non creare un secondo motore generale in parallelo ai motori canonici esistenti.


Il gestionale deve trattare ogni operazione amministrativa utilizzando una catena di prove.

La struttura fondamentale è:

**OBBLIGAZIONE → DOCUMENTO → ISTRUZIONE DI PAGAMENTO → PAGAMENTO → INTERMEDIARIO EVENTUALE → BANCA → RICONCILIAZIONE**

Non bisogna mai confondere questi elementi.

### 1. PRINCIPIO ASSOLUTO

Un documento non equivale automaticamente a un pagamento.

Una ricevuta di pagamento non equivale automaticamente a un movimento bancario.

Un pagamento effettuato tramite POS, PayPal, Nexi, Numia, SumUp o altro intermediario non equivale automaticamente all'accredito bancario.

Un F24 predisposto non equivale automaticamente a un F24 addebitato.

Una rata prevista non equivale automaticamente a una rata pagata.

Una cartella con piano di rateizzazione non equivale automaticamente a un debito regolare.

Il gestionale deve sapere sempre:

1. **cosa doveva essere pagato;**
2. **perché doveva essere pagato;**
3. **a quale soggetto o ente;**
4. **entro quale data;**
5. **con quale identificativo;**
6. **quanto è stato effettivamente pagato;**
7. **attraverso quale canale;**
8. **se esiste una ricevuta;**
9. **se esiste la prova finanziaria;**
10. **a quale movimento bancario corrisponde.**

---

## 2. MODELLO UNIVERSALE

Ogni elemento deve appartenere a una categoria precisa.

#### A. OBBLIGAZIONE

Esempi:

- fattura fornitore;
- F24;
- avviso bonario;
- cartella esattoriale;
- rata INPS;
- ravvedimento;
- rottamazione;
- rata Agenzia Entrate-Riscossione;
- bollettino pagoPA;
- stipendio;
- contributi;
- imposta;
- tributo locale.

L'obbligazione rappresenta:

**“Quanto devo, a chi, perché e quando.”**

#### B. DOCUMENTO

È la fonte che descrive l'obbligazione.

Può essere:

- PDF;
- XML;
- avviso;
- F24;
- cartella;
- piano di ammortamento;
- prospetto;
- cedolino;
- ricevuta;
- comunicazione dell'ente.

#### C. PAGAMENTO

Descrive l'operazione eseguita:

- bonifico;
- assegno;
- pagoPA;
- carta;
- PayPal;
- F24 telematico;
- addebito diretto;
- bollettino;
- RAV;
- MAV;
- altro strumento.

#### D. PROVA DI PAGAMENTO

Può essere:

- ricevuta pagoPA;
- quietanza F24;
- ricevuta PayPal;
- ricevuta POS;
- ricevuta telematica;
- attestazione dell'ente.

Questa prova permette di dire:

**“Il pagamento risulta eseguito/documentato.”**

Non sempre permette di dire:

**“Il relativo denaro è già stato verificato sul conto corrente.”**

#### E. PROVA FINANZIARIA

La prova finanziaria principale rimane:

**movimento bancario reale/importato dall'estratto conto.**

---

## 3. LIVELLI DI CERTEZZA

Il motore non deve usare solamente PAGATO / NON PAGATO.

Deve utilizzare livelli.

#### PREVISTO

Esiste l'obbligazione ma non risulta ancora un pagamento.

#### PREDISPOSTO

È stato preparato un pagamento ma non esiste ancora prova della sua esecuzione.

#### DOCUMENTATO

Esiste una ricevuta o quietanza.

#### TROVATO IN BANCA

Esiste un movimento finanziario compatibile.

#### RICONCILIATO

Documento, importo, identificativi e prova finanziaria risultano coerenti.

#### PARZIALMENTE RICONCILIATO

Solo una parte dell'importo è stata provata.

#### DA VERIFICARE

Esistono elementi compatibili ma anche discrepanze.

---

## 4. PAGOPA

Per ogni bollettino pagoPA il gestionale deve estrarre quando disponibili:

- IUV;
- codice avviso;
- ente creditore;
- codice fiscale/P.IVA debitore;
- causale;
- importo;
- data scadenza;
- data pagamento;
- PSP;
- identificativo transazione;
- ricevuta;
- eventuali commissioni.

L'identificativo principale deve essere:

**IUV / Codice Avviso**

e non semplicemente:

**importo + data.**

Esempio:

Avviso:

**IUV 12345678901234567  
Comune X  
€432,00**

Ricevuta:

**IUV 12345678901234567  
Pagato €432,00**

Il collegamento è forte.

Se successivamente viene trovato anche il movimento:

**Pagamento pagoPA €432**

la catena diventa:

**Avviso → IUV → Ricevuta → Movimento bancario**

e può essere considerata riconciliata.

Se esiste la ricevuta ma il movimento bancario non è ancora individuato:

**DOCUMENTATO, NON ANCORA RICONCILIATO CON BANCA**

---

## 5. PARTENOPAY

PartenoPay non deve avere una logica contabile indipendente.

Deve essere trattato come:

**PORTALE / ORIGINE DEL PAGAMENTO PAGOPA**

Pertanto:

**PartenoPay → pagoPA → IUV/Codice Avviso → Ricevuta → eventuale movimento bancario**

Il gestionale deve conservare "PartenoPay" come:

- portale;
- origine;
- ente/servizio;
- metadato.

Ma utilizzare il motore pagoPA per la riconciliazione.

---

## 6. PAYPAL

PayPal deve essere trattato come un **conto/intermediario finanziario**, non come banca e non semplicemente come POS.

Per ogni operazione PayPal memorizzare:

- transaction ID;
- data;
- soggetto;
- importo lordo;
- commissione;
- importo netto;
- valuta;
- tipo operazione;
- eventuale rimborso;
- eventuale storno;
- stato;
- eventuale documento collegato.

Esempio:

Vendita: €100

Commissione PayPal: €3

Saldo PayPal: €97

Successivamente:

Trasferimento PayPal → banca €497

Quel bonifico potrebbe contenere più operazioni.

NON bisogna cercare:

**vendita €100 = accredito banca €100**

perché potrebbe non esistere.

La catena corretta è:

**Operazioni PayPal → saldo PayPal → trasferimento aggregato → conto corrente**

Le commissioni devono essere registrate separatamente.

---

## 7. NEXI / NUMIA / SUMUP

Nexi, Numia e SumUp devono essere trattati come **acquirer / intermediari POS**.

Non bisogna riconciliare ogni vendita direttamente con l'estratto conto.

La catena deve essere:

**Corrispettivi → transazioni POS → chiusura/settlement → commissioni → accredito banca**

Esempio:

Vendite elettroniche RT:

€1.000

Transazioni POS:

€1.000

Commissioni:

€8

Accredito banca:

€992

La riconciliazione corretta è:

**€1.000 POS = €992 banca + €8 commissioni**

e non:

**€1.000 POS ≠ €992 banca → errore**

Devono essere supportati:

- accrediti aggregati;
- accrediti di più giornate;
- commissioni;
- storni;
- chargeback;
- rimborsi;
- accrediti ritardati.

---

## 8. CARTELLE ESATTORIALI

Una cartella deve diventare una **posizione debitoria strutturata**.

Estrarre almeno:

- ente creditore;
- numero cartella;
- data;
- contribuente;
- importo originario;
- sanzioni;
- interessi;
- spese;
- totale;
- eventuali tributi contenuti;
- eventuali codici tributo;
- scadenze;
- stato;
- eventuale piano di rateizzazione.

Il sistema non deve trasformare automaticamente l'importo totale della cartella in un'unica uscita se è presente un piano.

Deve creare:

**Cartella → Piano → Rate**

Esempio:

Cartella €12.000

12 rate da €1.000

Il database deve avere:

**Debito principale €12.000**

e sotto:

Rata 1  
Rata 2  
Rata 3  
...

Ogni rata deve essere riconciliabile indipendentemente.

---

## 9. RATEIZZAZIONI AGENZIA ENTRATE-RISCOSSIONE

Ogni piano deve avere una propria anagrafica:

**PIANO RATEALE**

contenente:

- identificativo;
- posizione originaria;
- importo iniziale;
- numero rate;
- capitale;
- interessi;
- spese;
- data concessione;
- scadenze;
- rate pagate;
- rate residue;
- debito residuo.

Ogni rata:

**PIANO → RATA → PAGAMENTO → BANCA**

Non basta trovare un'uscita dello stesso importo.

Quando possibile utilizzare:

- numero documento;
- identificativo rata;
- codice pagamento;
- RAV/pagoPA;
- riferimento presente nella causale.

---

## 10. ROTTAMAZIONI

La rottamazione deve essere trattata come un particolare piano di definizione del debito.

Il gestionale deve conservare separatamente:

**Debito originario**

e

**Debito definito tramite rottamazione**

Non cancellare il debito originario.

Creare invece una relazione:

**Posizioni originarie → Definizione agevolata → Piano → Rate**

Ogni rata deve avere:

- numero rata;
- importo;
- scadenza;
- identificativo pagamento;
- stato;
- ricevuta;
- movimento bancario.

---

## 11. DILAZIONI INPS

Stessa architettura:

**Debito INPS → Piano dilazione → Rate**

Memorizzare:

- matricola/posizione;
- periodo contributivo;
- debito;
- sanzioni/accessori;
- piano;
- numero rate;
- scadenze;
- importi;
- pagamento prima rata;
- stato del piano;
- rate pagate;
- rate mancanti;
- debito residuo.

Il motore non deve codificare permanentemente nel software quantità massime di rate o regole normative.

Queste devono essere gestite attraverso:

**tabelle normative versionate per data di validità.**

---

## 12. AVVISI BONARI

L'avviso bonario deve diventare una posizione debitoria autonoma collegata alla dichiarazione o periodo fiscale di origine.

Memorizzare:

- numero comunicazione;
- Agenzia delle Entrate;
- anno fiscale;
- imposte interessate;
- importo richiesto;
- sanzioni;
- interessi;
- data notifica/comunicazione;
- scadenza;
- eventuale piano rateale;
- modalità di pagamento;
- F24 collegati.

Se rateizzato:

**Avviso → Piano → Rate → F24 → Banca**

---

## 13. RATEIZZAZIONE AVVISO BONARIO

Non creare tanti debiti indipendenti.

Creare:

**un debito principale**

con:

**un piano di pagamento**

contenente N rate.

Il totale delle rate deve poter essere confrontato con:

**capitale + sanzioni + interessi + eventuali accessori**

Ogni rata può generare un F24 distinto.

Quindi:

**Avviso bonario → rata 3 → F24 → codici tributo → addebito banca**

---

## 14. RAVVEDIMENTO OPEROSO

Il ravvedimento non deve essere interpretato come un semplice pagamento.

Il sistema deve sapere quale obbligazione originaria viene regolarizzata.

Esempio:

IVA originaria

+

tributo

+

sanzione ravvedimento

+

interessi

=

F24 ravvedimento

Il sistema deve collegare:

**Obbligazione originaria → Ravvedimento → F24 → righe tributo → pagamento bancario**

Quindi non deve confondere:

- imposta principale;
- sanzione;
- interessi.

Devono restare classificati separatamente.

---

## 15. CODICI TRIBUTO AGENZIA DELLE ENTRATE

Questa è una regola fondamentale.

Il codice tributo NON deve essere usato da solo per riconciliare con la banca.

Il codice tributo serve a capire:

**CHE COSA È STATO PAGATO**

mentre il movimento bancario dimostra:

**CHE IL MODELLO F24 È STATO ADDEBITATO**

La gerarchia deve essere:

**Movimento bancario → F24 → righe F24 → codici tributo**

E NON:

**Movimento bancario → singolo codice tributo**

Esempio:

F24 totale €10.000

composto da:

IVA €5.000  
ritenute €2.000  
INPS €2.500  
interessi €100  
sanzioni €400

La banca mostrerà eventualmente:

**ADDEBITO F24 €10.000**

Il gestionale riconcilia l'addebito di €10.000 con il MODELLO.

Dopo la riconciliazione del modello distribuisce contabilmente i €10.000 sulle relative righe.

Quindi:

**BANCA €10.000**

↓

**F24 €10.000**

↓

- codice tributo A €5.000
- codice tributo B €2.000
- codice INPS €2.500
- interessi €100
- sanzione €400

---

## 16. ANAGRAFICA CODICI TRIBUTO

Creare una tabella centrale:

**CODICI TRIBUTO**

con:

- codice;
- descrizione;
- ente;
- sezione F24;
- natura;
- categoria contabile;
- imposta;
- sanzione/interesse/capitale;
- periodicità;
- anno di riferimento richiesto;
- eventuale collegamento con altri codici;
- validità dal;
- validità al.

Non affidarsi esclusivamente all'intelligenza artificiale.

Claude può suggerire una classificazione, ma la fonte principale deve essere la tabella ufficiale/versionata.

---

## 17. COMPENSAZIONI F24

Il gestionale deve comprendere anche i crediti.

Esempio:

Debiti F24: €10.000

Credito compensato: €3.000

Saldo da pagare:

€7.000

La banca dovrà essere confrontata con:

**€7.000**

e non con €10.000.

Ma contabilmente devono restare visibili:

**debiti €10.000**

**crediti utilizzati €3.000**

**saldo €7.000**

Quindi:

**Totale debiti − totale crediti = saldo finale F24**

Solo il saldo finale deve essere confrontato con l'addebito finanziario.

---

## 18. CALENDARIO FISCALE PREVISIONALE

Il calendario fiscale non deve essere un semplice calendario manuale.

Deve essere generato automaticamente utilizzando almeno quattro fonti.

#### FONTE 1: SCADENZE NORMATIVE

Scadenze fiscali previste dalla normativa.

#### FONTE 2: STORICO AZIENDALE

Esempio:

se ogni mese vengono versate ritenute, il sistema può prevedere l'obbligazione del mese successivo.

#### FONTE 3: DOCUMENTI REALI

Quando arriva:

- F24;
- piano INPS;
- cartella;
- avviso;
- rata;
- comunicazione;

la previsione diventa una **scadenza certa/documentata**.

#### FONTE 4: DATI OPERATIVI

Cedolini, fatture, IVA, corrispettivi, personale, contributi e altri dati possono generare previsioni.

---

## 19. DIFFERENZA TRA PREVISIONE E SCADENZA CERTA

Fondamentale.

Il calendario deve mostrare chiaramente:

#### PREVISTA

Generata dal gestionale.

#### CALCOLATA

Derivata dai dati disponibili.

#### DOCUMENTATA

Esiste un documento che conferma importo/scadenza.

#### PAGAMENTO PREDISPOSTO

Esiste un F24 o altra disposizione.

#### PAGATA

Esiste prova di pagamento.

#### RICONCILIATA

Esiste anche la prova bancaria coerente.

Non trasformare automaticamente una previsione in un debito certo.

---

## 20. CALENDARIO FINANZIARIO PREVISIONALE

Il calendario fiscale deve alimentare anche la tesoreria.

Esempio:

15 novembre

Stipendi previsti: €35.000

16 novembre

Ritenute previste: €9.000

INPS previsto: €14.000

30 novembre

Rata cartella: €5.000

Il gestionale può prevedere:

**uscite finanziarie future €63.000**

e confrontarle con:

**liquidità prevista**

Questo permette al CFO Agent/Tesoreria di segnalare preventivamente eventuali carenze di liquidità.

---

## 21. PROSPETTI PAGA

I prospetti paga hanno una funzione molto più importante del semplice archivio PDF.

Devono servire al gestionale per conoscere anticipatamente il costo e gli obblighi relativi al personale.

Il prospetto deve alimentare almeno:

- dipendente;
- periodo;
- retribuzione lorda;
- netto;
- contributi;
- ritenute;
- eventuali trattenute;
- TFR;
- ferie/permessi se disponibili;
- costo aziendale quando ricavabile;
- importo da pagare al dipendente;
- importi da versare successivamente a enti e fisco.

---

## 22. PROSPETTO PAGA ≠ PAGAMENTO DIPENDENTE

Il cedolino/prospetto paga dice:

**quanto deve essere pagato.**

Il bonifico dice:

**quanto è stato disposto.**

La banca dice:

**quanto è stato realmente addebitato.**

La catena corretta è:

**Prospetto paga → Cedolino → Dipendente → Bonifico → Estratto conto**

Solo alla fine:

**PAGATO E RICONCILIATO**

---

## 23. PROSPETTI PAGA E F24

Il motore deve inoltre utilizzare i prospetti paga per creare collegamenti con gli obblighi successivi.

Per esempio:

**Prospetti paga ottobre**

↓

ritenute dipendenti

↓

contributi

↓

F24 novembre

Quindi il gestionale può sapere che un F24 contenente determinate componenti deriva, almeno in parte, dal ciclo paghe.

La relazione deve essere:

**Periodo paghe → obblighi fiscali/previdenziali → F24 → banca**

Non:

**Cedolino → F24 direttamente pagato**

---

## 24. RICONCILIAZIONE MULTILIVELLO

Claude deve cercare i collegamenti in quest'ordine:

#### LIVELLO 1 - IDENTIFICATORE UNIVOCO

Esempi:

- IUV;
- codice avviso;
- transaction ID;
- numero assegno;
- CRO/TRN;
- identificativo F24;
- numero cartella;
- identificativo rata;
- identificativo piano.

Se corrisponde, la probabilità è elevata.

#### LIVELLO 2 - IMPORTO

Controllare importo.

#### LIVELLO 3 - DATA

Controllare data/scadenza/intervallo compatibile.

#### LIVELLO 4 - SOGGETTO

Controllare:

- beneficiario;
- ente;
- fornitore;
- dipendente;
- PSP;
- intermediario.

#### LIVELLO 5 - CAUSALE

Analizzare descrizione del movimento.

#### LIVELLO 6 - RELAZIONI GIÀ CONOSCIUTE

Esempio:

Nexi → specifico conto corrente

PayPal → specifico conto corrente

numero assegno → fornitore

piano rateale → rata prevista

IUV → avviso specifico.

---

## 25. CERTEZZA MATEMATICA E CERTEZZA PROBABILISTICA

Il gestionale deve distinguere.

#### CERTEZZA FORTE

Identificativo univoco + importo coerente.

Esempio:

IUV coincidente + €512,37 coincidente.

#### CERTEZZA MOLTO FORTE

Identificativo + importo + soggetto + documento tutti coerenti.

#### PROPOSTA PROBABILE

Importo + data + causale simili ma nessun identificativo certo.

#### AMBIGUA

Più documenti possono corrispondere allo stesso movimento.

In questo caso:

**NON RICONCILIARE AUTOMATICAMENTE.**

Mostrare:

**Da verificare**

con candidati suggeriti.

---

## 26. NON FORZARE MAI LA RICONCILIAZIONE

Claude non deve utilizzare la logica:

“Questo sembra quello più probabile, quindi lo considero pagato.”

Deve invece utilizzare:

“Questo è il candidato più probabile, ma mancano prove sufficienti.”

Le proposte AI devono restare separate dalle prove documentali.

---

## 27. RICONCILIAZIONI UNO-A-MOLTI

Il motore deve supportare:

**1 movimento bancario → più documenti**

Esempio:

un bonifico paga 3 fatture.

Oppure:

un accredito Nexi contiene 250 transazioni POS.

---

## 28. RICONCILIAZIONI MOLTI-A-UNO

Supportare:

**più movimenti → 1 obbligazione**

Esempio:

fattura pagata con acconto + saldo.

Oppure:

debito pagato parzialmente con più versamenti.

---

## 29. RICONCILIAZIONI MOLTI-A-MOLTI

Supportare anche:

**più pagamenti → più documenti**

senza perdere le allocazioni.

Creare quindi una tabella:

**ALLOCATIONS / RICONCILIAZIONI**

contenente:

- origine;
- destinazione;
- importo allocato;
- data;
- tipo relazione;
- livello certezza;
- metodo di riconciliazione;
- utente/algoritmo;
- timestamp.

---

## 30. NESSUNA CANCELLAZIONE DELLA STORIA

Se una posizione viene:

- corretta;
- rateizzata;
- rottamata;
- annullata;
- sostituita;
- riconciliata;
- disassociata;

non cancellare la storia.

Creare un log:

**evento precedente → evento successivo**

Il gestionale deve poter ricostruire sempre:

**perché oggi una posizione risulta in quello stato.**

---

## 31. REGOLA DEL DATABASE

Non creare una tabella indipendente e scollegata per ogni nuovo tipo di documento.

Utilizzare entità comuni:

- obligations
- documents
- payment_instructions
- payments
- payment_receipts
- bank_transactions
- intermediary_transactions
- settlement_batches
- tax_lines
- installment_plans
- installments
- reconciliations
- allocations
- deadlines
- audit_logs

e collegare tutto tramite ID e relazioni.

---

## 32. REGOLA FINALE

Per qualsiasi documento o pagamento il sistema deve essere capace di rispondere a queste domande:

**CHE COS'È?**

**CHI DEVE PAGARE?**

**A CHI?**

**PERCHÉ?**

**QUANTO?**

**QUANDO?**

**CON QUALE IDENTIFICATIVO?**

**ESISTE IL DOCUMENTO?**

**ESISTE UNA RICEVUTA?**

**ESISTE IL MOVIMENTO FINANZIARIO?**

**È STATO RICONCILIATO?**

**CON QUALE LIVELLO DI CERTEZZA?**

Se una di queste informazioni manca, non inventarla.

Utilizzare:

**NON DISPONIBILE / DA VERIFICARE / IN ATTESA DI RICONCILIAZIONE.**

L'intelligenza artificiale deve aumentare la capacità di trovare collegamenti.

Non deve sostituire la prova

---

# 18. Ingresso documenti

## REGOLA

Un documento viene riconosciuto dal contenuto.

Non dal titolo.

Non dalla cartella.

Non dalla data modifica.

Nome e percorso possono aiutare solo a ordinare il lavoro.

Un file entra nel gestionale solo se passa dallo smistatore previsto.

Ingressi principali:

- Documenti > Import;
- cartella unica Drive.

Cartella unica:

- `DA ELABORARE`
- `ELABORATE`
- `ERRORI`

Eventuali stati come `ARRETRATO` seguono le regole specifiche.

La presenza in `ELABORATE` non dimostra che il documento sia stato acquisito correttamente.

Serve il registro applicativo.

## APERTO

Esistono ancora classificazioni che consultano nome file o percorso prima del contenuto.

Devono essere eliminate una alla volta.

---

# 19. Deduplica documentale

## Duplicato certo

Solo:

- SHA-256 uguale;
- byte identici.

Nome, dimensione, data e importo non sono prova sufficiente.

## Possibile duplicato

Può essere individuato con identità business coerente.

Esempi:

- fattura: P.IVA + numero + data;
- bonifico: CRO/TRN + importo;
- quietanza: protocollo + saldo;
- cedolino: CF + periodo + tipo + valori;
- verbale: numero/IUV/targa.

I possibili duplicati non vengono eliminati automaticamente.

---

# 20. Originali documentali

L'ERP deve usare il servizio canonico per l'apertura degli originali.

Nuovi endpoint alternativi sono vietati.

Gli endpoint storici possono esistere soltanto come alias compatibili.

## APERTO

HR mantiene endpoint propri per proteggere documenti visibili al singolo dipendente.

Non considerarli nuovi sistemi da copiare.

Devono essere consolidati solo quando esiste una soluzione che preserva gli stessi permessi.

---

# 21. Protocollo Drive

Il protocollo registra:

- file nuovo;
- file modificato;
- file rimosso quando rilevabile;
- impronta;
- provenienze.

Una stessa impronta in più posizioni non crea un nuovo documento.

Le posizioni sono `source_occurrences`.

## PRODUZIONE

Il protocollo incrementale è attivo.

Il giro completo è spento per motivi di memoria.

## CONSEGUENZA

Lo stato del protocollo non può essere considerato fotografia completa delle eliminazioni/spostamenti su Drive finché il giro completo resta spento.

Non affermare il contrario.

---

# 22. Event bus

Esiste un solo event bus:

`app/services/event_bus.py`

Il ramo HR deve usare il re-export.

Un fatto si pubblica una volta sola.

Non creare un secondo registro eventi.

---

# 23. Prima Nota

Motore canonico:

`app/services/scritture_contabili.py`

Non creare nuovi `insert_one` diretti per scritture di Prima Nota.

Prima Nota non è la copia dell'estratto conto.

Una riga entra quando possiede significato contabile sufficiente.

---

# 24. Libro giornale

## PRODUZIONE

Il libro giornale è **spento** per decisione del titolare (07/10/2026): non gli serve. Il registro operativo è la Prima Nota cassa/banca (§23).

Interruttore unico nel motore: `LIBRO_GIORNALE_ATTIVO` (difetto spento). Con l'interruttore spento `registra_fattura`, `registra_corrispettivo`, `registra_scrittura_semplice`, storni, pregresso e job rispondono `stato = disattivato` e non scrivono nulla; `_scrivi_movimento` rifiuta comunque (`GiornaleDisattivato`). Le letture delle scritture già esistenti non cambiano. I test accendono l'interruttore per collaudare il motore.

Non riaccenderlo senza decisione del titolare. Le regole che seguono valgono quando è acceso.

Motore:

`app/services/registrazione_contabile.py`

Ogni scrittura:

`DARE = AVERE`

al centesimo.

Tolleranza arrotondamento IVA:

massimo 0,01 €, attraverso la riga canonica prevista.

Oltre la tolleranza la scrittura viene rifiutata.

---

# 25. Competenza e pagamento

La competenza economica e il pagamento sono fatti distinti.

## Fattura

DARE:

- costo;
- IVA se applicabile.

AVERE:

- debito fornitore.

## Pagamento

DARE:

- debito fornitore.

AVERE:

- banca/cassa.

Il pagamento non genera nuovamente il costo.

Stessa logica per:

- stipendi;
- F24;
- contributi;
- ritenute;
- altri debiti.

## APERTO CRITICO

Il pagamento di fatture, stipendi e F24 non chiude ancora in modo uniforme il debito nel libro giornale.

Questa è una priorità architetturale.

La futura implementazione deve entrare nel motore contabile canonico.

Non creare un motore parallelo.

---

# 26. Bilancio

Il bilancio deve usare la competenza.

Non la data di pagamento.

Non lo stato attuale della fattura per ricostruire automaticamente la situazione di un esercizio precedente.

## APERTO CRITICO

Il bilancio attuale non usa ancora correttamente `data_competenza` in tutti i percorsi.

Il debito dello stato patrimoniale non è ancora completamente derivato dai saldi contabili.

Prima di considerare affidabile una chiusura di esercizio correggere questi punti.

---

# 27. Fatture ricevute

Le fatture appartengono all'ERP.

Campi canonici:

- `invoice_date`
- `invoice_number`
- `total_amount`

Non usare come fonte principale campi derivati storici come:

- `data_documento`
- `totale`

quando possono mancare.

Per cercare ID fattura storici usare gli helper canonici.

---

# 27A. A-Cube — fatture passive via API

## REGOLA

Codice: `app/services/acube.py`, `app/routers/acube.py`, pagina Integrazioni › A-Cube fatture (`/integrazioni/acube`).

- Il webhook `POST /api/acube/webhook` è pubblico ma protetto dal segreto nell'header `Authorization`; il segreto nasce nel database (`sistema_stato`, chiave `acube_webhook`) e non esce mai.
- Del corpo del webhook si usa solo l'`uuid`: la fattura si rilegge sempre da A-Cube con la credenziale del gestionale.
- Registro del canale: collezione `acube_fatture` (una riga per `uuid`, idempotente).
- In `ACUBE_ENV=sandbox` le fatture sono simulate: si registrano e si vedono, ma non entrano mai in contabilità.
- In produzione l'originale passa dallo smistatore dei documenti (`_smista`, lo stesso della cartella unica Drive) con `channel: "acube"`: nessun secondo writer delle fatture. `ACUBE_IMPORT=false` ferma il solo import.
- Controllo di riserva ogni giorno alle 6:20 (Europe/Rome) sugli ultimi 5 giorni, mai sullo storico.

## PRODUZIONE

Variabili su Render: `ACUBE_EMAIL`, `ACUBE_PASSWORD`, `ACUBE_ENV=sandbox` (07/10/2026). Scheda della società creata nella sandbox A-Cube con ricezione fatture passive attiva.

## APERTO

Produzione A-Cube e Cassetto fiscale (fatture, F24, corrispettivi) da attivare con il commerciale A-Cube (ticket 334300): accesso tramite incaricato, non delega (la delega non scarica gli F24).

---

# 28. Stato pagamento fattura

La domanda “è pagata?” ha un solo motore logico.

Non leggere isolatamente campi storici concorrenti.

L'archivio contiene ancora:

- `stato`
- `stato_pagamento`
- `payment_status`
- `pagato`
- `paid`

Il codice deve passare dagli helper canonici.

## TARGET

Ridurre progressivamente la persistenza a un modello coerente e derivare le viste.

Non aggiungere un sesto campo.

---

# 29. Metodo di pagamento fornitore

Il metodo previsto viene dall'anagrafica fornitore.

Non viene dedotto dalla fattura.

Se manca:

fattura `sospesa`.

Mai default automatico “bonifico”.

Mai ripiego automatico “cassa”.

Metodo previsto e pagamento effettivamente provato sono concetti distinti.

## REGOLA — registrazione all'import per metodo fornitore

Oltre l'ultima data del report «Fatture ricevute» del titolare (`data_limite_dichiarazioni`) la fattura a rata unica di un fornitore non escluso si instrada all'import secondo il metodo dell'anagrafica, in un solo punto (`auto_registra_prima_nota`) e con il writer unico di Prima Nota:

| Metodo fornitore | All'import |
| --- | --- |
| cassa | movimento in Prima Nota Cassa subito, data = data fattura, fattura pagata, `fattura.pagata` una volta sola |
| banca | riga provvisoria in Prima Nota Banca = attesa dell'estratto conto; con riga EC univoca al centesimo → pagata e riconciliata |
| assegno collegato o previsto | §39: pagamento dichiarato con assegno, in attesa di riscontro bancario; una sola riga di attesa |
| misto | Provvisoria, decide l'operatore |
| mancante | `sospesa_metodo_fornitore_mancante` + alert `FAT_MP_NON_DEFINITO`, nessun movimento |

La data fattura del movimento cassa è la dichiarazione del titolare tramite anagrafica, non un dato inventato; senza data documento non si registra.

Note di credito TD04/TD08 non generano un'entrata di cassa automatica (§32).

Fino alla data limite comanda il report del titolare (`pagamenti_dichiarati_titolare`), non il metodo.

Il secondo import della stessa fattura non produce un secondo movimento né un secondo evento (§122).

---

# 30. Fatture e scadenze

Le fatture fornitore non hanno una scadenza operativa automatica.

Il titolare decide quando pagare.

Non inventare:

- +30 giorni;
- scadenza XML;
- condizioni commerciali trasformate in agenda.

F24 e stipendi mantengono le proprie scadenze reali.

---

# 31. Fatture e partite aperte

`fattura.created` deve produrre gli effetti previsti in modo idempotente.

Una fattura senza evento può restare senza:

- partita;
- alert;
- audit;
- flussi a valle.

## APERTO

Esiste pregresso senza partita aperta.

Usare il recupero canonico.

Non creare partite manualmente con SQL.

---

# 32. Note di credito

TD04/TD08:

- non sono costo;
- invertono la scrittura;
- diminuiscono costo, IVA a credito e debito;
- eventuale rimborso chiude la nota di credito.

## APERTO CRITICO

Esistono note di credito storiche contabilizzate col segno errato.

Devono essere rettificate con storni/scritture corrette, non cancellate.

---

# 33. Fornitori

Identità:

1. P.IVA valida;
2. CF;
3. id esterno verificato.

Un cambio ragione sociale non crea un nuovo fornitore.

Doppioni certi e probabili sono gestiti dal motore canonico.

Due P.IVA valide diverse non si fondono.

La fusione è soft e mantiene storico.

---

# 34. Righe acquisti

`GET /api/righe-acquisti` è una vista.

Non un secondo archivio.

Le classificazioni persistenti stanno nella collezione dedicata.

Una classificazione non confermata resta:

`DA_VERIFICARE`

La classificazione AI produce proposte.

Non scritture contabili.

---

# 35. Movimenti bancari

La riga bancaria canonica è identificata da:

- riferimento esterno;
- oppure fingerprint canonico.

Doppioni fra export dello stesso conto devono convergere in una riga.

Un movimento bancario non si associa per solo importo.

Servono identità e contesto.

## PRODUZIONE — conto BNL storico (4500/3192, chiuso)

Gli estratti PDF BNL 2021-2023 si leggono con `app/services/estratto_conto_bnl_parser.py` (riconoscimento dal contenuto, mai dal nome) e si scrivono in `estratto_conto_movimenti` con `conto_contabile = conti_pos.CONTO_BNL` (19.01.02), `banca = BNL`, `fonte = estratto_bnl_pdf`, stessa chiave di deduplica del conto BPM. Il verso di ogni riga viene dalla colonna del PDF («PER UNA USCITA DI» / «PER UNA ENTRATA DI»), non dalla causale; l'estratto si rifiuta se `saldo iniziale + entrate − uscite ≠ saldo finale` o se i totali del riepilogo non coincidono con le righe lette.

I movimenti BNL non si proiettano in Prima Nota: sono archivio bancario per riconciliare assegni, F24, cartelle e bonifici ai dipendenti di quegli anni. Per questo solo formato la soglia d'arretrato (`DRIVE_ESTRATTI_ANNO_MINIMO`) non si applica (titolare, 07/10/2026); gli altri estratti la seguono.

---

# 36. Categorizzazione banca

Motore unico.

Le regole apprese dal titolare possono prevalere sulle regole generiche.

Non creare motori locali nelle pagine.

Un movimento senza categoria resta una coda da classificare.

Non inventare una categoria per far sparire la coda.

---

# 37. Riconciliazione fatture ↔ banca

Una fattura bancaria è riconciliata solo se esiste una prova coerente.

Importo al centesimo.

Identità coerente.

Quando ambiguo mostrare candidati.

Non applicare.

## APERTO CRITICO

Esistono fatture marcate riconciliate senza movimento riconciliato.

Questi stati devono essere riallineati.

Lo stato della fattura deve diventare derivato dalla catena di prove, non un booleano indipendente.

---

# 38. Bonifici

Il PDF del bonifico è una prova documentale.

Non prova l'addebito.

Il movimento bancario ufficiale completa la prova.

La stampa PDF di una fattura non è un bonifico.

Una parcella con ritenuta usa il netto dovuto al fornitore.

---

# 39. Gestione Assegni
La Gestione Assegni è una **pre-registrazione di un futuro movimento bancario**.

Non serve soltanto a censire i numeri utilizzati.

Quando l'utente emette un assegno, comunica in anticipo al gestionale quale movimento dovrà comparire successivamente sul conto corrente.

La catena canonica è:

**Carnet → Assegno → Beneficiario → Fattura/obbligo → Movimento bancario → Riconciliazione**

---

## Carnet

Il carnet contiene una sequenza di numeri assegno.

Il numero è sempre testo.

Gli zeri iniziali sono significativi.

Esempio:

`00004581`

non deve diventare:

`4581`

---

## Creazione carnet

L'amministratore può creare un carnet indicando:

- banca;
- conto corrente;
- primo numero assegno;
- quantità assegni.

Esempio:

Primo numero:

`004581`

Quantità:

`20`

Il gestionale genera:

- 004581
- 004582
- 004583
- …
- 004600

Stato iniziale:

`DISPONIBILE`

La generazione deve controllare che i numeri non esistano già per lo stesso conto/carnet.

Non creare duplicati.

---

## Stati canonici dell'assegno

| Stato | Significato |
| --- | --- |
| `DISPONIBILE` | numero presente nel carnet e mai utilizzato |
| `EMESSO` | assegno compilato, movimento bancario ancora assente |
| `COLLEGATO` | associato a una fattura o altra obbligazione |
| `DA_VERIFICARE` | dati incompatibili, incompleti o ambigui |
| `TROVATO_IN_BANCA` | numero identificato nell'estratto ma catena non ancora completamente verificata |
| `RICONCILIATO` | assegno, importo, banca e obbligazione risultano coerenti |
| `ANNULLATO` | numero inutilizzabile conservato nella sequenza |

Gli stati devono avere un solo registro canonico.

Frontend e backend non mantengono liste proprie.

---

## Emissione dell'assegno

Quando un assegno viene utilizzato si registrano, quando disponibili:

- numero assegno;
- carnet;
- conto corrente;
- beneficiario;
- fornitore;
- importo;
- data emissione;
- causale;
- `fattura_id`;
- numero fattura;
- data fattura;
- eventuale altro documento/obbligazione collegato.

Lo stato passa almeno:

`DISPONIBILE → EMESSO`

Se viene collegato a un'obbligazione:

`EMESSO → COLLEGATO`

Il collegamento a una fattura può dichiararne il pagamento secondo le regole del titolare, ma il riscontro bancario resta ancora atteso.

---

## Attesa bancaria

L'emissione crea una previsione/attesa di movimento bancario.

Concettualmente:

> Attendo sul conto X un addebito per assegno N, importo Y.

L'attesa deve conservare almeno:

- conto;
- numero assegno;
- importo;
- data emissione;
- beneficiario;
- obbligazione collegata.

L'assegno non crea un movimento dell'estratto conto.

La banca deve fornirlo realmente.

---

## Identificazione nell'estratto conto

Quando arriva una fonte bancaria ufficiale, il motore assegni cerca il numero dell'assegno nei dati strutturati e nella causale disponibile.

Esempio assegno:

`004581`

Estratto:

`ADDEBITO ASSEGNO 004581`

Il numero costituisce l'identità principale.

Per una riconciliazione automatica certa serve anche:

`importo bancario = importo assegno`

al centesimo.

Quando numero e importo coincidono:

**Movimento bancario → Assegno**

può essere determinato automaticamente se non esistono ambiguità.

---

## Numero uguale, importo diverso

Se il numero viene trovato ma l'importo non coincide:

`DA_VERIFICARE`

Messaggio:

**Assegno identificato, ma importo non coerente.**

Non modificare automaticamente l'importo dell'assegno.

Non forzare la riconciliazione.

Mostrare:

- importo registrato;
- importo banca;
- differenza;
- movimento candidato.

---

## Movimento bancario con assegno non registrato

Se l'estratto contiene:

`ASSEGNO 004593`

ma nel sistema non esiste il numero:

segnalare:

`ASSEGNO_BANCA_NON_REGISTRATO`

Non creare automaticamente beneficiario o fattura.

Se il numero appartiene a un carnet censito ed è ancora `DISPONIBILE`, segnalare l'anomalia con priorità alta.

Esempio:

> Assegno 004593 transitato in banca ma ancora disponibile nel carnet.

---

## Assegno emesso non transitato

Un assegno `EMESSO` o `COLLEGATO` non ancora trovato in banca resta aperto.

Il sistema può segnalarlo dopo un periodo significativo, senza dichiararlo errore automaticamente.

Esempio:

> Assegno 004587 emesso il 10/09/2026 e non ancora rilevato nell'estratto conto.

Non inventare una data di addebito.

---

## Modifica prima della riconciliazione

Finché non esiste una riconciliazione bancaria definitiva, l'utente può correggere i dati registrati.

Sono modificabili almeno:

- importo;
- beneficiario/fornitore;
- fattura;
- data fattura;
- data emissione;
- causale;
- collegamento all'obbligazione.

Non è necessario cancellare e ricreare l'assegno.

Il numero assegno conserva la sua identità nel carnet.

---

## Storico modifiche

Ogni modifica amministrativa deve lasciare uno storico.

Registrare:

- campo modificato;
- valore precedente;
- nuovo valore;
- data/ora;
- utente;
- eventuale motivo.

Esempio:

`importo: 2350,00 → 2420,00`

`fattura: FT 125/2026 → FT 128/2026`

Non sovrascrivere in modo invisibile i valori precedenti.

---

## Effetti della modifica

Se l'assegno aveva dichiarato una fattura come pagata ma non possiede ancora prova bancaria, una modifica del collegamento deve:

1. ritirare la precedente dichiarazione;
2. riaprire l'obbligazione precedente quando necessario;
3. collegare la nuova obbligazione;
4. ricreare/aggiornare l'attesa bancaria;
5. mantenere lo stesso assegno e il suo storico.

Mai lasciare contemporaneamente pagate sia la vecchia sia la nuova fattura.

---

## Assegno già riconciliato

Quando l'assegno è `RICONCILIATO`, non consentire modifiche silenziose ai campi che compongono la riconciliazione:

- numero;
- importo;
- beneficiario;
- fattura;
- conto;
- data emissione quando rilevante.

Mostrare:

> Questo assegno è già riconciliato con un movimento bancario. La modifica renderebbe incoerente la prova esistente.

La procedura normale è:

**disassocia/storna la riconciliazione**
→ **correggi l'assegno**
→ **riesegui la riconciliazione**

Ogni passaggio deve essere tracciato.

Una prova bancaria non viene cancellata.

Si ritira il collegamento.

---

## Annullamento

Un assegno può essere annullato.

L'annullamento:

- non elimina il record;
- non elimina il numero dal carnet;
- non rende nuovamente disponibile quel numero;
- conserva lo storico.

Stato:

`ANNULLATO`

Motivi predefiniti:

- errore di compilazione;
- deteriorato;
- beneficiario errato;
- importo errato;
- sostituito con altro assegno;
- altro.

`Altro` permette testo libero.

---

## Assegno annullato già collegato

L'annullamento deve ritirare eventuali dichiarazioni di pagamento non ancora provate.

La fattura viene riaperta quando necessario.

Se esiste già una prova bancaria ufficiale, l'annullamento semplice non è ammesso.

Serve prima gestire la riconciliazione esistente attraverso il percorso amministrativo previsto.

---

## Numero annullato

Un assegno annullato non torna `DISPONIBILE`.

La sequenza del carnet deve restare:

- 004581 RICONCILIATO
- 004582 ANNULLATO
- 004583 DISPONIBILE

Non:

- 004581
- 004583

Il numero 004582 deve restare visibile.

---

## Collegamento alla fattura

La fattura collegata deve essere identificata tramite il suo ID canonico.

Numero fattura e data possono essere conservati come presentazione/prova, ma non sostituiscono `fattura_id`.

Quando l'assegno è collegato all'intero dovuto di una fattura, la dichiarazione del titolare può segnalarla come pagata secondo il motore canonico.

Fino al riscontro nell'estratto:

stato finanziario:

**pagamento dichiarato, in attesa di riscontro bancario**

Dopo il riscontro:

**pagamento provato in banca**

All'import della fattura XML l'assegno collegato prevale sul metodo del fornitore (§29): la fattura resta `in_attesa_estratto_conto` con `metodo_pagamento_previsto = assegno`, senza decisione richiesta e con una sola riga di attesa in Prima Nota Banca marcata con l'`assegno_id`; il riscontro resta al motore dell'estratto conto.

---

## Pagamenti parziali e più fatture

Un assegno può essere associato a più obbligazioni soltanto se il sistema conserva le quote.

La somma delle quote deve essere:

`= importo assegno`

al centesimo.

Se non quadra:

`DA_VERIFICARE`

Non distribuire automaticamente una differenza.

---

## Controlli carnet

La pagina Gestione Assegni deve evidenziare almeno:

- disponibili;
- emessi;
- collegati;
- da verificare;
- trovati in banca;
- riconciliati;
- annullati;
- emessi non transitati;
- numeri mancanti;
- duplicazioni;
- movimenti bancari con assegno non registrato;
- assegni transitati ma ancora `DISPONIBILE`;
- assegni con importo diverso dalla banca.

---

## Numerazione carnet BPM

Quando la banca utilizza carnet con regole specifiche già conosciute dal sistema, usare il motore canonico esistente.Non duplicare la logica della numerazione nei router o nel frontend.

Gli zeri persi possono essere ricostruiti solo quando la regola del carnet rende l'identità deterministica.

Un frammento incompleto non deve essere indovinato.

---

## Writer unico

Un solo servizio deve governare:

- emissione;
- modifica;
- annullamento;
- collegamento fatture;
- associazione banca;
- riconciliazione;
- storico.

Router, pagine e job devono chiamare quel motore.

Non creare un secondo matching assegni per importo o data.

---

## Principio generale assegni

La Gestione Assegni anticipa un movimento futuro senza inventarlo.

L'utente dichiara:

> Ho emesso l'assegno 004581 a Fornitore Alfa per € 2.350,00.

Il gestionale conserva:

**004581 → Fornitore Alfa → € 2.350 → FT 125/2026**

Quando la banca restituisce:

> ASSEGNO 004581 - € 2.350,00

il motore può ricostruire:

**Movimento bancario**
→ **Assegno 004581**
→ **Fornitore Alfa**
→ **FT 125/2026**

La banca costituisce la prova finale del transito.

La registrazione preventiva serve a rendere quella riconciliazione semplice, deterministica e verificabile.

---

# 40. Trasferimenti interni

Versamento/prelievo contanti:

- uscita da un conto;
- entrata nell'altro;
- stesso `operation_id`;
- categoria `trasferimento_interno`.

Non è costo.

Non è ricavo.

---

# 41. POS e Coerenza POS–Corrispettivi

Corrispettivo RT, chiusura del terminale POS e accredito bancario sono **tre fatti distinti**.

La catena di verifica è:

**Corrispettivo RT → Chiusura POS → Accredito bancario**

Il gestionale non deve saltare nessuno dei tre passaggi e non deve trasformare una corrispondenza presunta in una riconciliazione bancaria.

## Prima prova: RT ↔ POS

Il corrispettivo RT dichiara quanto è stato incassato elettronicamente nella giornata.

La chiusura del terminale POS documenta quanto è realmente transitato sul terminale.

Il primo controllo è quindi:

`elettronico dichiarato dal RT ↔ totale transato dai POS`

Esempio:

| Fonte | Importo |
| --- | ---: |
| Corrispettivo elettronico RT | € 1.250,00 |
| Totale POS giornata | € 1.250,00 |

Se coincidono al centesimo:

**RT ✓ → POS ✓**

La giornata è coerente fra registratore telematico e terminale.

Questo **non significa ancora che il denaro sia stato accreditato in banca**.

## Stati da individuare

### RT > POS

Nel registratore telematico risultano più pagamenti elettronici di quelli realmente passati dal terminale.

Possibili cause:

- tasto carta utilizzato per errore;
- pagamento classificato male;
- chiusura POS incompleta;
- terminale non acquisito.

Stato:

`DA_VERIFICARE_RT_POS`

Non correggere automaticamente né RT né POS.

### POS > RT

Sul terminale risultano più transazioni di quelle dichiarate elettroniche dal registratore telematico.

Possibili cause:

- pagamento elettronico registrato come contante;
- chiusura RT errata;
- transazione appartenente a un'altra giornata operativa;
- terminale o documento POS duplicato.

Stato:

`DA_VERIFICARE_RT_POS`

### RT = POS, banca assente

Registratore e terminale coincidono.

Il pagamento elettronico è verificato fino al POS, ma manca ancora la prova bancaria.

Stato funzionale:

**POS verificato, accredito da riconciliare**

Non:

**Incassato in banca**

La mancanza dell'accredito non è automaticamente un'anomalia perché il gestore può accreditare successivamente.

### RT = POS, banca presente

Se anche l'accredito bancario è stato identificato e la quadratura economica è corretta:

**RT ✓ → POS ✓ → BANCA ✓**

Il ciclo è completamente riconciliato.

---

## Seconda prova: POS ↔ banca

L'importo accreditato in banca non deve necessariamente essere identico al lordo POS.

Il gestore può:

- trattenere commissioni;
- accorpare più giornate;
- dividere una giornata in più accrediti;
- regolare commissioni separatamente.

Esempio:

| Componente | Importo |
| --- | ---: |
| Transato POS | € 1.000,00 |
| Accredito bancario | € 994,00 |
| Commissioni documentate | € 6,00 |
| Quadratura | € 1.000,00 |

La quadratura corretta è:

`accrediti bancari + commissioni documentate = transato POS`

al centesimo.

Non considerare automaticamente anomalo:

`POS ≠ accredito`

prima di aver verificato commissioni, payout e aggregazioni.

## Accredito bancario

Il gestionale **non inventa mai l'accredito**.

Anche quando:

`RT = POS`

lo stato bancario resta aperto finché il movimento reale non compare nella fonte bancaria ammessa.

Una chiusura POS non crea artificialmente una riga bancaria.

L'estratto conto può soltanto soddisfare un'attesa già esistente.

---

## Più terminali e più circuiti

Quando nella stessa giornata esistono più terminali o circuiti, il controllo deve conservare le componenti.

Esempio:

`RT elettronico = € 1.500`

può corrispondere a:

- SumUp € 500;
- altro circuito € 1.000.

Non forzare un'unica chiusura POS se esistono più prove distinte.

La somma delle chiusure compatibili deve quadrarne il totale.

---

## Semaforo Coerenza POS

La pagina Coerenza POS deve mostrare chiaramente i tre anelli:

**RT → POS → BANCA**

con stato separato per ciascuno.

Esempi:

`RT ✓ | POS ✓ | BANCA …`

= terminale verificato, accredito ancora da trovare.

`RT ✓ | POS ⚠ | BANCA …`

= differenza fra registratore e terminale.

`RT ✓ | POS ✓ | BANCA ✓`

= ciclo completamente riconciliato.

`RT ? | POS ✓ | BANCA ✓`

= manca o non è determinabile la prova RT.

Il colore non deve essere l'unica informazione: mostrare sempre stato e motivo testuale.

---

## Principio contabile

Il ricavo nasce dal documento fiscale del corrispettivo secondo le regole del dominio.

La chiusura POS e l'accredito bancario **non generano un secondo ricavo**.

Sono prove e movimenti finanziari.

---

---

# 42. Corrispettivi

Via primaria:

XML RT.

CSV AdE:

dato provvisorio.

Non genera Prima Nota o giornale fino al documento definitivo.

Il non riscosso si legge solo dalle voci esplicite del documento.

Mai:

`totale - contanti - POS`

per inventare il non riscosso.

---

# 43. Ricavi e fatture emesse

I ricavi del bar derivano dalle vendite fiscalmente registrate.

La fonte ordinaria è costituita dai **corrispettivi RT**.

Le **fatture emesse relative a vendite già comprese nei corrispettivi non generano un secondo ricavo**.

La fattura emessa deve essere collegata al corrispettivo che contiene già quella vendita.

La catena è:

**Vendita → Corrispettivo → eventuale fattura emessa**

e non:

**Corrispettivo + fattura emessa = due ricavi**

## Fattura emessa dopo scontrino

Se la fattura è stata emessa per una vendita già battuta nel registratore telematico:

- conserva il documento fiscale;
- collega la fattura al corrispettivo;
- non aumenta nuovamente i ricavi;
- non aumenta nuovamente l'IVA;
- non crea un nuovo credito cliente per lo stesso incasso.

L'identità aziendale stabilisce se una fattura è emessa:

`cedente = FISCAL_COMPANY_ID`

Le fatture emesse non vanno nella collezione delle fatture fornitori.

---

## Vendite fatturate non comprese nei corrispettivi

Se esiste un caso reale in cui una fattura emessa rappresenta una vendita **non già compresa nei corrispettivi**, il sistema non deve ignorarla.

Deve prima dimostrare che manca il corrispettivo collegabile.

Solo allora quella fattura può concorrere autonomamente ai ricavi secondo la sua corretta disciplina contabile e fiscale.

Mai decidere soltanto dal tipo di documento.

La regola è:

**una vendita reale = un solo ricavo**

indipendentemente dal numero di documenti che la rappresentano.

---

## Non sono ricavi

Non costituiscono nuovi ricavi:

- accrediti POS;
- payout SumUp;
- accrediti PayPal;
- giroconti;
- trasferimenti interni;
- versamenti di contanti;
- rimborsi;
- movimenti bancari che costituiscono soltanto regolazione di un credito già registrato.

---

---

# 44. SumUp e Numia

SumUp e conto BPM sono conti/fonti distinti.

I movimenti SumUp restano nella collezione prevista.

Numia è dismesso.

Non segnalarlo come fonte corrente ferma oltre la sua ultima attività.

---

# 45. PayPal

PayPal si riconcilia con banca e documenti usando il motore previsto.

L'utente può scegliere fra candidati quando necessario.

La scelta manuale non autorizza modifica di importo o valuta.

---

# 46. Mutui

Una rata ha prove di forza diversa:

1. banca;
2. quietanza;
3. estratto annuale;
4. dichiarazione del titolare;
5. stato stampato sul piano.

Non usare un generico “Pagata” senza indicare la prova.

Se l'importo non torna secondo la tolleranza prevista:

`DA_VERIFICARE`

---

# 47. IVA

`iva_detraibile` assente significa:

**non deciso**

Non zero.

Lo zero è un dato vero soltanto se determinato.

Una fattura senza classificazione IVA non deve essere fatta passare artificialmente come classificata.

Periodo:

`periodo_iva_attribuito`

---

# 48. Regola del 15

Operazione mese precedente ricevuta e annotata entro il 15:

può competere al mese precedente solo nello stesso anno.

Operazione anno precedente:

mai retroattribuzione automatica a dicembre.

---

# 49. LIPE — confronto IVA, controllo del commercialista e ricostruzione delle attese

## Principio vincolante: la LIPE non “vince” sul nostro calcolo

La LIPE **non deve vincere automaticamente sul calcolo IVA del gestionale**. È il riferimento indipendente del commercialista con cui confrontare il nostro risultato.

- Se coincide, il periodo è coerente rispetto alla LIPE.
- Se esiste un piccolo scostamento, il sistema lascia il nostro calcolo invariato e mostra un avviso con la differenza e le componenti che la spiegano.
- Se lo scostamento è significativo, il sistema apre una verifica e cerca fatture, note di credito, periodi IVA e altri documenti che possano spiegare la divergenza.
- La LIPE non modifica automaticamente fatture, IVA detraibile, periodi o liquidazioni per far tornare i numeri.
- Se manca l'F24, una LIPE valida può generare **l'attesa del tributo**. La quietanza Agenzia delle Entrate con protocollo può soddisfare documentalmente quell'attesa quando codice, periodo e importo sono coerenti.
- Questa catena **non crea retroattivamente un F24 mai acquisito**: il modello continua a risultare mancante e, se arriva in seguito, viene inserito nella catena già esistente senza duplicare pagamento o quietanza.


La LIPE non serve soltanto come documento fiscale da archiviare.

Serve come **prova esterna del calcolo IVA trasmesso dal commercialista** e come strumento di controllo incrociato fra:

1. IVA calcolata dal gestionale;
2. IVA dichiarata dal commercialista;
3. F24;
4. quietanze Agenzia delle Entrate;
5. banca.

La LIPE non sostituisce i documenti sorgente del gestionale e non modifica automaticamente le fatture.

Serve a capire se i due sistemi stanno descrivendo la stessa posizione IVA.

---

## Catena di controllo

La catena attesa è:

**Fatture + corrispettivi → calcolo IVA Gestionale**

confrontato con:

**LIPE del commercialista**

e successivamente, quando esiste un versamento:

**F24 → quietanza AdE con protocollo → movimento bancario**

La LIPE costituisce quindi un ponte di controllo fra la nostra contabilità e quella del commercialista.

---

## LIPE ↔ calcolo IVA Gestionale

Per ogni periodo il sistema deve confrontare almeno:

- operazioni attive;
- operazioni passive;
- IVA a debito;
- IVA detraibile;
- debito/credito del periodo;
- credito precedente;
- importo finale dovuto o a credito;
- eventuali altri campi VP realmente leggibili e rilevanti.

Il confronto non deve limitarsi all'importo finale.

Deve permettere di capire **dove nasce la differenza**.

---

## Coincidenza

Se Gestionale e LIPE coincidono secondo i valori rilevanti:

`COINCIDE`

È la situazione migliore.

Il sistema può considerare il periodo verificato rispetto alla contabilità trasmessa dal commercialista.

---

## Piccolo scostamento

Una differenza piccola non deve necessariamente bloccare il periodo.

Deve però essere visibile.

Stato:

`COINCIDE_CON_SCOSTAMENTO`

con:

- valore gestionale;
- valore LIPE;
- differenza;
- percentuale quando utile;
- componenti che producono lo scarto.

Lo scostamento non viene corretto automaticamente.

Non modificare fatture o liquidazioni per farle coincidere artificialmente.

La soglia oltre la quale uno scostamento smette di essere “piccolo” deve essere una regola configurata/versionata e non un numero inventato nel codice.

---

## Scostamento significativo

Se lo scostamento supera la soglia prevista:

`DA_VERIFICARE`

Il gestionale deve aiutare a determinare la causa.

Una delle verifiche principali è:

**Il commercialista ha registrato tutte le fatture che risultano nel gestionale?**

Il controllo deve quindi evidenziare, quando i dati disponibili lo consentono:

- fatture presenti nel gestionale che potrebbero mancare nella contabilità del commercialista;
- differenze nell'IVA acquisti;
- differenze nell'IVA vendite;
- note di credito;
- documenti attribuiti a un periodo diverso;
- fatture ricevute dopo il termine;
- documenti esclusi o ancora `DA_VERIFICARE`.

Non dichiarare automaticamente che l'errore è del commercialista.

Il sistema segnala la divergenza e le possibili cause.

---

## LIPE non quadrata

Una LIPE che non supera i controlli aritmetici del quadro VP:

- viene conservata come documento;
- conserva l'originale;
- porta il motivo dell'errore;
- non diventa fonte canonica del confronto numerico.

Stato:

`LIPE_DA_VERIFICARE`

Non usare valori non affidabili per generare attese fiscali.

---

## LIPE come fonte per ricostruire ciò che ci aspettiamo di trovare

Quando manca il modello F24, i dati affidabili della LIPE possono essere utilizzati per creare o arricchire una **attesa fiscale**, mai un F24 inventato.

Esempio:

la LIPE dimostra un debito IVA mensile/trimestrale.

Il gestionale può sapere:

- periodo;
- natura IVA;
- importo dichiarato;
- codice tributo teoricamente atteso quando determinabile dalle regole fiscali versionate.

Il sistema può quindi creare:

`TRIBUTO_ATTESO_DA_LIPE`

con:

- periodo;
- importo;
- codice tributo atteso;
- fonte = LIPE;
- protocollo LIPE;
- documento origine.

Ma non deve creare un falso modello F24.

---

## LIPE → codice tributo atteso

Il codice tributo deriva dalla regola fiscale versionata.

Esempi, quando applicabili:

- IVA mensile: 6001–6012;
- trimestrali: codici previsti dal registro fiscale;
- altri casi soltanto se la norma e il motore li conoscono.

La LIPE fornisce il **dato economico dichiarato**.

Il registro fiscale fornisce il **codice tributo atteso**.

Non dedurre un codice sconosciuto per somiglianza.

---

## Assenza del modello F24

Se:

- la LIPE valida indica un debito;
- il codice tributo atteso è determinabile;
- il modello F24 non è presente;

il sistema non deve fermarsi.

Deve cercare le prove successive disponibili, in particolare:

**quietanza Agenzia delle Entrate**

con:

- protocollo;
- data;
- righe tributo;
- periodo;
- importi.

La quietanza può quindi essere confrontata con l'attesa derivata dalla LIPE.

---

## LIPE ↔ quietanza in assenza di F24

Quando manca il modello F24, è ammesso il collegamento:

**LIPE → tributo atteso → quietanza AdE**

solo se:

- periodo coerente;
- codice tributo coerente;
- importo coerente secondo le regole applicabili;
- protocollo della quietanza disponibile;
- nessuna ambiguità significativa.

Questo collegamento significa:

**il versamento atteso dalla LIPE trova riscontro nella quietanza**

Non significa:

**abbiamo ricostruito il modello F24 originale**

Il modello F24 continua a risultare mancante.

---

## Quietanza con protocollo

Il protocollo della quietanza Agenzia delle Entrate è una parte importante dell'identità documentale.

Va conservato e mostrato nel collegamento.

La catena può diventare:

**LIPE**
→ periodo IVA e importo dichiarato  
→ **tributo atteso**
→ codice tributo  
→ **quietanza AdE con protocollo**
→ **movimento bancario**

Se arriva successivamente il modello F24, viene inserito nella catena senza creare un secondo pagamento.

---

## Quietanza non equivale a banca

Anche quando LIPE e quietanza coincidono:

**versamento documentato ≠ movimento bancario verificato**

Lo stato deve distinguere:

- importo atteso;
- quietanza trovata;
- banca da verificare;
- banca riconciliata.

Esempio:

`LIPE ✓ → QUIETANZA ✓ → BANCA …`

---

## Finalità di controllo del commercialista

Una funzione esplicita della LIPE è permettere di controllare la completezza reciproca dei dati.

Il sistema deve aiutare a rispondere a domande come:

- Il nostro totale IVA coincide con quello trasmesso?
- Il commercialista ha probabilmente acquisito tutte le nostre fatture?
- Quali fatture o note di credito possono spiegare la differenza?
- Il periodo è stato attribuito nello stesso modo?
- Esiste una quietanza coerente col debito dichiarato?
- Esiste l'addebito bancario?
- Manca soltanto il modello F24?

La LIPE è quindi una **fonte di confronto e riconciliazione fiscale**, non un comando che sovrascrive la nostra contabilità.

---

---

# 50. F24

Modello, righe tributo, quietanza e movimento bancario sono entità distinte.

Livelli:

- `CERTO`
- `PROBABILE`
- `PARZIALE`
- `NESSUN_MATCH`
- `MOVIMENTO_ORFANO`

Solo `CERTO` scrive automaticamente il pagamento.

`PROBABILE` e `PARZIALE` richiedono conferma del titolare.

---

# 51. Stato F24

Distinguere:

- da pagare;
- versamento documentato;
- banca da verificare;
- riscontrato in banca;
- compensato.

La quietanza dimostra il versamento.

Non sostituisce il riscontro bancario quando richiesto.

---

# 52. F24 e costi

Il saldo F24 non è un costo.

Ritenute, addizionali, contributi, IVA e altri debiti chiudono posizioni verso enti.

Non registrare l'intero F24 a costo.

---

# 53. Codici tributo

Descrizioni e regole vengono dal registro canonico.

Non duplicare tabelle nei parser.

Codice tributo sempre stringa.

Un codice sconosciuto blocca la contabilizzazione definitiva.

---

# 54. F24 saldo zero

Saldo zero significa:

**compensazione totale**

Non errore.

Nessun addebito bancario atteso.

---

# 55. Ritenute 1040

Il periodo del 1040 segue il mese del pagamento al professionista.

Non il mese della fattura.

Finché la fattura non è pagata:

- periodo vuoto;
- scadenza vuota;
- nessun F24 agganciato automaticamente.

---

# 56. HR come fonte persone

Anagrafica canonica:

`hr.app_dipendenti`

Lotti legge una proiezione.

ERP collega il pagamento.

Non creare una seconda anagrafica.

Stati:

- `attivo`
- `cessato`

---

# 57. PIN

Un PIN personale per persona.

Un solo PIN amministratore centrale, salvo eccezioni esplicite Lotti.

Non creare login admin paralleli.

---

# 58. Cedolini

Un solo motore di lettura.

Il netto si legge dalla cella esplicitamente associata a:

- `TOTALE NETTO`
- `NETTO DEL MESE`
- `NETTO IN BUSTA`

Mai ricostruire il netto da competenze meno trattenute come fonte autorevole.

Valore mancante:

`None`

Mai zero.

---

# 59. Stati netto

- `NETTO_VERIFICATO_DA_CEDOLINO`
- `NETTO_NON_PRESENTE_O_NON_LEGGIBILE`
- `MULTIPLE_NETS_DA_VERIFICARE`
- `ERRORE_PARSER`

Solo il primo alimenta automaticamente i flussi economici.

---

# 60. Acconti recuperati in busta

Separare:

`netto_pdf`

`acconto_recuperato`

`dovuto_mese`

Non sommare l'acconto in più moduli.

## APERTO

Verificare che Posizione dipendente e deposito HR non lo conteggino due volte.

---

# 61. Pagamento stipendio

Un solo motore associa bonifico e stipendio.

Niente primo movimento con importo vicino e nome simile.

Identità e periodo devono essere coerenti.

Il movimento vale come prova bancaria solo se proviene dalla fonte ufficiale prevista.

---

# 62. Bonifico prima del cedolino

Se arriva prima il bonifico:

`in_attesa_busta`

Importo busta:

null.

Mai zero.

All'arrivo della busta il mese viene ricalcolato.

---

# 63. Posizione dipendente

DARE:

- dovuto da buste;
- 13ª;
- 14ª;
- conciliazioni non bonus.

AVERE:

- bonifici;
- acconti;
- contanti ammessi;
- altri pagamenti provati.

Non confondere pagamento dichiarato e pagamento bancariamente provato.

---

# 64. TFR

Un solo motore.

Le correzioni si stornano.

Il giornale è quello del gestionale.

Non creare un secondo giornale HR.

---

# 65. Fork HR

Due copie dello stesso modulo non si mantengono manualmente.

## PRODUZIONE

Il router TFR è uno solo: `app/hr/routers/tfr.py` (montato su `/hr/api/tfr`). `app/routers/tfr.py` espone soltanto due letture del fondo sull'archivio del gestionale per Gestione Cespiti e re-esporta il resto; non scrive.

## APERTO

Fork di logica residui fra `app/` e `app/hr/` (stesso sottopercorso, nessun re-export; `tests/runtime/test_fork_app_hr.py` ne impedisce la crescita): `routers/employees/dipendenti.py`, `routers/pin_login.py`, `utils/dependencies.py`. Il fondo TFR letto dal gestionale (`gestionale.dipendenti.tfr_maturato`) non deriva ancora dall'anagrafica canonica HR.

Ogni modifica a quei tre file deve controllare il gemello finché non viene consolidato.

---

---

# 65A. HR — Cedolini, pagamenti, acconti e riconciliazione

## Obiettivo della pagina

Archivio paghe deve mostrare, per dipendente, rapporto di lavoro e periodo:

- documenti retributivi e relative fonti;
- netto stampato sul cedolino;
- acconti recuperati in busta;
- totale dovuto del periodo;
- pagamenti verificati e attribuiti;
- residuo, eccedenze e anomalie.

Ogni importo deve essere spiegabile aprendo il documento che lo prova.
Cedolino presente, documento verificato e retribuzione pagata sono fatti
distinti. Nessuno dei tre implica automaticamente gli altri.

Drive conserva gli originali; Supabase conserva dati, stati e relazioni.
Excel è un formato di importazione, non un secondo archivio operativo.

## Identità, rapporto e periodo

- Leggere dal PDF datore di lavoro, nome, codice fiscale, matricola,
  periodo retributivo, assunzione ed eventuale cessazione.
- Non dedurre identità o competenza dal nome del file.
- Collegare il documento all'anagrafica tramite identità verificata.
  Omonimie e corrispondenze incomplete restano `DA_VERIFICARE`.
- Distinguere i rapporti della stessa persona: una riassunzione non
  sovrascrive la precedente assunzione o cessazione.
- La competenza del cedolino, la data di emissione e la data del pagamento
  sono campi distinti.
- Lo storico richiesto parte dal 01/01/2017. Il limite deve essere coerente
  fra import Excel, lettura PDF, sincronizzazione e visualizzazione.
- Conservare il periodo civile originale delle mensilità aggiuntive.
  I mesi tecnici 13 e 14 sono classificazioni del registro, non date.

## Campi da estrarre

Leggere i valori nelle rispettive caselle o voci del documento:

- netto del mese;
- totale competenze;
- totale trattenute;
- imponibile INPS;
- contributi e ritenute previdenziali del dipendente;
- imponibile IRPEF;
- ritenute IRPEF, rimborsi e addizionali;
- arrotondamenti;
- retribuzione utile TFR;
- quote TFR, anticipazioni e liquidazioni, quando presenti;
- ore ordinarie mensili;
- ratei e componenti di tredicesima e quattordicesima;
- acconti recuperati, con codice voce, descrizione, segno e importo.

Non confondere:

- imponibile INPS con ritenute previdenziali;
- imponibile IRPEF con imposta trattenuta;
- retribuzione utile TFR con quota maturata, fondo o liquidazione;
- valori mensili con progressivi annuali;
- ore retribuite con presenze effettivamente lavorate;
- lordo, netto e importo del bonifico.

Il netto si legge esclusivamente nella casella graficamente associata
all'etichetta del netto. Competenze meno trattenute è un controllo:
non sostituisce il netto stampato.

Campo vuoto o illeggibile significa dato mancante, mai zero.
Uno zero verificato si mostra come `€ 0,00`.

Ogni valore verificato conserva fonte, pagina, etichetta o codice voce,
metodo di estrazione e versione del parser. OCR e letture ambigue
richiedono verifica visiva prima di alimentare importi certi.

## Classificazione dei documenti

Distinguere almeno:

1. cedolino ordinario;
2. tredicesima autonoma;
3. quattordicesima autonoma;
4. cedolino misto;
5. documento di fine rapporto, liquidazione o TFR;
6. documento autonomo di arretrati o conguaglio.

La classificazione deve essere provata dal contenuto.

Una quota di tredicesima, quattordicesima, arretrati o TFR dentro una busta
non crea automaticamente un secondo cedolino o un secondo debito.

Formato del produttore, tipo retributivo e stato documentale sono distinti.
Zucchetti, TeamSystem e CSC identificano famiglie di lettura.
Definitivo, rettificato, sostituito e stampa di controllo identificano stati
o versioni, non nuove mensilità.

Un foglio di sole presenze non è un cedolino retributivo.
Una stampa di controllo non alimenta automaticamente il dovuto definitivo.

## Fascicoli, copie e versioni

- Segmentare i fascicoli per identità, rapporto, periodo e documento.
- Conservare tutte le pagine appartenenti allo stesso cedolino.
- Un netto ripetuto su più pagine si conta una volta sola.
- Netti discordanti nello stesso documento restano `DA_VERIFICARE`.
- Stesso dipendente, periodo e tipo non costituiscono da soli una chiave
  univoca: possono esistere documenti aggiuntivi legittimi.
- Distinguere copia dello stesso documento, continuazione, documento
  aggiuntivo e versione sostitutiva.
- Conservare SHA-256 del documento corrente, hash del fascicolo sorgente,
  pagine originarie e identificativi Drive.
- Sostituire un collegamento multipagina con un PDF individuale aggiorna
  la fonte del record esistente: non crea un secondo cedolino.
- Non sostituire fonti definitive con stampe di controllo.
- Non scegliere una versione soltanto perché più recente.
- Documenti già pagati o contabilizzati richiedono una rettifica tracciata,
  non una sovrascrittura silenziosa.
- Gli originali non si cancellano come conseguenza automatica del cambio
  di collegamento.

## Importazione Excel e PDF

L'Excel operativo contiene due fogli: `Cedolini` e `Pagamenti`.
Non aggiungere fogli tecnici al file destinato all'importazione.

`Cedolini` contiene una riga per documento retributivo distinto:
identità, rapporto, periodo, tipo, importi, stato di verifica, nome file,
ID/link Drive, SHA-256 e pagine sorgente.

`Pagamenti` contiene una riga per operazione distinta:
beneficiario, importo, valuta, data, causale, riferimenti bancari,
stato di esecuzione e fonte documentale.

I campi relativi agli acconti devono avere un mapping esplicito:
non possono essere ignorati dall'importatore.

Flusso obbligatorio:

1. anteprima senza scritture;
2. controllo di duplicati, conflitti, anagrafiche e dati mancanti;
3. conferma riferita allo stesso file verificato tramite SHA-256;
4. importazione delle sole righe ammesse;
5. deposito dei pagamenti nella coda di riconciliazione.

Non modificare automaticamente anagrafiche, presenze, dati corretti,
associazioni confermate o scritture contabili esistenti.

La seconda importazione della stessa fonte deve produrre zero nuovi
documenti, zero nuovi pagamenti e zero nuovi debiti.

## Prova del pagamento e riconciliazione

Cedolino, disposizione bancaria, ricevuta, distinta ed estratto conto
sono evidenze differenti.

Una disposizione prenotata, revocata, annullata o non eseguita non prova
il pagamento. La firma sulla busta paga non sostituisce la prova bancaria.

La riconciliazione verifica:

- identità del beneficiario e rapporto;
- riferimento dell'operazione;
- competenza e destinazione;
- importo attribuito;
- esecuzione del pagamento;
- assenza di associazioni incompatibili.

Importo uguale, cognome o vicinanza di date non bastano da soli.
Una proposta non è un'associazione confermata.

Ricevuta ed estratto della stessa operazione completano un unico pagamento:
non producono due accrediti nel registro del dipendente.

Sono ammesse relazioni uno-a-molti e molti-a-uno soltanto con quote
documentate e confermate. Le quote non possono superare l'importo
disponibile del pagamento.

Una distinta con beneficiari vari richiede il dettaglio dei beneficiari
e delle quote. Non inventare una ripartizione.

Commissioni, fatture, giroconti, rimborsi spese, TFR e conciliazioni
non diventano automaticamente stipendi ordinari.

Un pagamento ricevuto prima del cedolino resta `IN_ATTESA_CEDOLINO`:
dovuto e residuo sono sconosciuti, non zero.

Il saldo si verifica in Decimal al centesimo. Differenze ed eccedenze
restano visibili; non vengono assorbite da tolleranze o assegnate
automaticamente al mese successivo.

## Acconti stipendio

Distinguere due fatti:

- acconto effettivamente versato;
- recupero dell'acconto dichiarato nel cedolino.

L'acconto versato conserva dipendente, importo, data, natura,
periodo di destinazione e prova del pagamento.
Se la competenza è sconosciuta, resta da attribuire.

Un bonifico già importato si classifica come acconto:
non si ricrea come movimento manuale.

Il recupero si legge da una voce esplicita e verificata del cedolino.
Una differenza aritmetica non prova l'esistenza di un acconto.
La voce di recupero non prova da sola il precedente versamento.

Se il netto stampato è già ridotto dall'acconto recuperato:

    dovuto del periodo = netto stampato + acconto recuperato verificato
    pagato = somma dei pagamenti verificati attribuiti, contati una volta
    residuo = dovuto del periodo - pagato

Esempio: netto stampato 900,00 €, recupero acconto 300,00 €,
dovuto 1.200,00 €. Acconto bancario 300,00 € e saldo bancario 900,00 €
chiudono il periodo. Non sottrarre nuovamente l'acconto dal netto stampato.

Se il cedolino non recupera l'acconto, il dovuto resta il netto stampato;
l'acconto verificato concorre fra i pagamenti attribuiti.

Non sommare due volte l'acconto quando un dato storico contiene già
il totale comprensivo del recupero. Conservare separatamente
`netto_stampato`, `acconto_recuperato` e `dovuto_periodo`.

## TFR e altri anticipi

Acconto stipendio, anticipo TFR, prestito e anticipo spese sono distinti.

Se un'anticipazione TFR è già compresa nel netto della busta,
non aggiungerla nuovamente al dovuto o ai pagamenti.
Conservare la componente TFR e il relativo trattamento separatamente.

Non considerare un pagamento diretto in contanti automaticamente regolare
perché registrato a mano o perché il dipendente è cessato.
Applicare le regole di tracciabilità pertinenti al rapporto e alla data.

## Mesi mancanti e collegamento con Presenze

La copertura documentale distingue:

- cedolino verificato presente;
- cedolino presente con netto mancante;
- cedolino con netto zero verificato;
- sole presenze;
- sola stampa di controllo;
- documento mancante durante un rapporto attivo;
- periodo esterno al rapporto;
- rapporto o periodo da verificare.

Calcolare i buchi documentali interni senza inventare mesi precedenti
all'assunzione o successivi alla cessazione.

Un documento TFR non dimostra da solo che tutti i mesi intermedi siano
correttamente assenti. Ricostruire cessazioni e riassunzioni con le fonti.

Cedolini e Presenze usano la stessa anagrafica e lo stesso rapporto.
Le differenze fra ore retribuite e presenze si segnalano:
non si correggono automaticamente.

## Stati, audit e criterio di completamento

Tenere separati stato del documento, verifica degli importi,
copertura del periodo e stato del pagamento.

Un cedolino con netto zero verificato può non avere un importo da erogare:
non richiede un pagamento fittizio per risultare completo.

Ogni associazione, ripartizione, rettifica o revoca conserva autore,
data, motivo, valore precedente e fonti.
Le conferme manuali non vengono riassegnate da processi automatici.

Un solo motore possiede le regole di deduplica, attribuzione e saldo:
importatori, sincronizzazioni e frontend non devono duplicarle.

Il flusso è completo solo dopo verifica di:

- apertura delle fonti corrette;
- identità, periodo, tipo e pagine;
- importi e distinzione fra zero e dato mancante;
- idempotenza;
- assenza di doppio conteggio degli acconti;
- relazioni reciproche fra cedolino, pagamento e prova;
- residui ed eccedenze al centesimo;
- conservazione delle decisioni dopo ricarica e sincronizzazione.

Importazione riuscita, HTTP 200 o pagina renderizzata non costituiscono
da soli prova di una riconciliazione corretta.

## Relazione con le regole HR sintetiche

Questa sezione dettaglia e completa le sezioni HR precedenti. In caso di apparente conflitto, applicare la formulazione che conserva più prove, distingue meglio dato mancante da zero e impedisce doppio conteggio o riconciliazione automatica ambigua.


---

# 66. Lotti — chi entra, magazzino, FIFO, ordini, prezzi e nomi

## A cosa serve e a cosa è collegato

Lotti è il modulo operativo di laboratorio e magazzino per:

- HACCP e tracciabilità;
- giacenze;
- produzione;
- ordini ai fornitori.

Lotti è **a valle del Gestionale**: le fatture XML arrivano dal Gestionale e alimentano Lotti tramite i flussi previsti.

Lotti legge da HR:

- persone;
- PIN personali;
- ruoli;
- mansioni;
- permessi.

Lotti **non mantiene una propria anagrafica persone parallela**.

Lotti spinge le ricette nel Menu attraverso il ponte previsto.

Un guasto o una lentezza di Lotti **non deve mai fermare l'import contabile** del Gestionale.

---

## Chi entra e cosa vede

### Titolare

Il titolare entra dalla sessione amministratore del Gestionale e vede tutto, comprese:

- le temperature da rilevare;
- i registri;
- le funzioni amministrative;
- il pulsante per tornare al Gestionale.

Il Gestionale e i comandi riservati restano protetti anche lato server.

### Operatore

L'operatore entra dal tablet con il proprio PIN personale.

Vede soltanto le card previste dalla sua mansione e dai suoi permessi.

Un indirizzo diretto verso un reparto non autorizzato non deve aggirare la navigazione: l'operatore viene ricondotto alle card disponibili per il suo profilo.

### Mansione e postazione

Comanda prima la postazione esplicitamente scelta dal titolare.

Se non esiste una postazione specifica, vale la mansione della scheda HR.

Mappatura operativa:

- `pasticcere` → **Pasticceria**;
- `rosticcere`, `cuoco`, `laboratorio` → **Rosticceria**;
- `barista`, `sala` → **Magazzino e Ordini**;
- chi possiede il permesso `haccp_registri` vede anche i registri HACCP.

Se la mansione non è deducibile:

- non inventare una restrizione;
- mostrare soltanto le funzioni che il profilo può usare con certezza;
- non mostrare il Gestionale;
- non mostrare le temperature riservate al titolare.

### Passaggio a un altro reparto

Per operare come un'altra persona o in un'altra mansione si usa:

**Cambia operatore**

poi si inserisce nuovamente il PIN.

Un PIN inserito da una card che non appartiene alla mansione dell'operatore non concede accesso generale: apre soltanto l'azione esplicitamente autorizzata, se il server la consente.

### Controllo lato server

La UI non è mai una barriera di sicurezza sufficiente.

Il backend deve continuare a usare le guardie canoniche, compresi quando applicabili:

- `require_admin`;
- `require_permesso`.

Il Gestionale e i comandi riservati restano accessibili soltanto al titolare/amministratore anche se qualcuno tenta di richiamare direttamente l'endpoint.

---

## Magazzino e FIFO

### Origine della giacenza

La giacenza nasce dalle righe delle fatture alimentari.

Ogni riga ammessa genera il relativo lotto in:

`lotti_fornitori`

salvo che il fornitore sia escluso dal magazzino secondo la decisione canonica del Gestionale.

La fattura resta un fatto contabile ERP: Lotti riceve soltanto ciò che gli serve per magazzino e tracciabilità.

### Vista magazzino

Chi preleva deve vedere **una riga per prodotto**.

Righe con:

- stesso prodotto;
- stessa unità di misura compatibile;

possono essere aggregate nella vista.

L'aggregazione della vista non elimina i lotti sottostanti e non cancella le loro provenienze.

### Scarico

L'endpoint/motore canonico di scarico è:

`/magazzino/scarico`

Non creare un secondo motore di scarico in router, ricette, ordini o frontend.

### FIFO

Il FIFO consuma prima il lotto con `data_fattura` più vecchia fra **tutti i fornitori dello stesso prodotto compatibile**, poi passa ai lotti successivi.

La scelta non dipende dal fornitore più recente né dal prezzo più basso.

### Unità e confezionamento

Lo scarico ragiona sempre nell'unità mostrata all'operatore, ad esempio:

- pezzi;
- kg.

Ogni lotto conserva il proprio fattore di confezionamento/collo.

Lotti con confezionamenti differenti non devono essere sommati come se fossero identici.

Esempio:

- X24;
- X12.

Questi due confezionamenti restano distinti se il fattore di conversione non consente una rappresentazione coerente nella stessa unità.

### Oltre la giacenza

Se la quantità richiesta supera la giacenza disponibile:

- risposta di errore;
- mostrare la quantità realmente disponibile;
- non scrivere nessun movimento parziale nascosto;
- non portare la giacenza sotto zero.

### Movimento di magazzino

Ogni lotto realmente consumato deve lasciare un movimento con almeno:

- lotto;
- quantità;
- unità;
- operatore;
- data/ora;
- origine dell'operazione;
- metodo `fifo` quando lo scarico è FIFO.

### Ricette

Per una ricetta il FIFO deve utilizzare prima i lotti la cui associazione con l'ingrediente è **confermata** secondo le regole della sezione Nomi.

Una semplice proposta di matching non autorizza lo scarico automatico.

### Stock zero

Una merce arrivata a giacenza zero **non deve sparire dall'universo ordinabile**.

Nel magazzino operativo può risultare esaurita, ma il Carrello ordini deve poterla ritrovare tramite:

`anche_esauriti`

Questa possibilità è riservata al flusso Carrello e non trasforma lo zero in giacenza disponibile.

---

## Senza glutine

### Catalogo

Il catalogo usa:

`acquaviva_prodotti`

La fonte dei fornitori abilitati deriva dal registro:

`fornitori_rivendita`

con flag:

`senza_glutine`

Il catalogo si riallinea dalle fatture XML dal 2026 dei fornitori che possiedono quel flag.

Regole:

- un prodotto per descrizione canonica;
- prezzo preso dall'ultima fattura compatibile;
- secondo giro idempotente con `nuovi=0`.

### Comando amministratore

Comando canonico:

`POST /acquaviva/prodotti/senza-glutine/importa-da-fatture?dry_run=`

Usare anteprima quando prevista prima della scrittura reale.

### Identità del fornitore

Il fornitore si riconosce per identità/nome completo normalizzato.

Mai per semplice sottostringa.

Esempio:

`progetto alpha`

non equivale automaticamente a qualsiasi soggetto contenente soltanto:

`alfa`

perché un soggetto come `Alfa Service` può vendere prodotti completamente differenti, ad esempio cannucce e bicchieri.

### Invio al banco

Un prodotto senza glutine mandato al banco deve prima essere scaricato dal magazzino attraverso il FIFO.

Endpoint previsto:

`POST /acquaviva/prodotti/senza-glutine/{id}/al-banco`

Sequenza:

**scarico FIFO → registrazione al banco**

Se la giacenza è assente o insufficiente:

- risposta `409`;
- nessuna vendita/uscita al banco viene registrata;
- nessuna giacenza negativa viene inventata.

---

## Ordini

### Richiesta merce

Ogni reparto può chiedere merce attraverso:

**Richiedi merce**

La richiesta deve conservare chi l'ha inserita.

### Lavagna

La Lavagna rappresenta consegna dalla scorta interna.

Usa soltanto prodotti disponibili nel magazzino bar secondo le regole del flusso.

Non è un ordine automatico al fornitore.

### Carrello ordini

Il Carrello ordini raccoglie le richieste che il titolare deve valutare prima dell'acquisto.

Restano riservati al titolare anche lato server:

- conferma ordine;
- modifica quantità definitiva;
- scelta/invio al fornitore;
- operazioni amministrative equivalenti.

### Righe ordine

Ogni riga deve conservare almeno:

- chi l'ha inserita;
- prodotto/articolo;
- quantità;
- unità;
- fornitore quando scelto;
- prezzo di riga;
- aliquota IVA;
- imponibile;
- IVA;
- totale.

I valori economici derivano dalle fonti ammesse e devono essere ricalcolati a ogni variazione della quantità o delle condizioni della riga.

Non conservare totali incoerenti dopo una modifica.

---

## Confronto prezzi

### Motore unico

Motore canonico:

`servizi/confronto_fornitori.py`

Identità fornitore:

P.IVA canonica quando disponibile.

Non creare confronti paralleli in Catalogo, Ordini o frontend.

### Prezzo pagato

Un prezzo realmente pagato deriva soltanto dalle **righe XML delle fatture**.

Un listino non diventa prezzo pagato.

### Listino

Il listino rappresenta il prezzo che il fornitore dichiara in una certa data.

Deve essere mostrato sempre con:

- indicazione `listino`;
- data della fonte.

Mai presentarlo come prezzo effettivamente pagato.

### Unità di confronto

Per bevande e prodotti equivalenti il confronto commerciale deve avvenire per pezzo/confezione coerente.

Non confrontare automaticamente bevande a kg o litro quando l'unità commerciale reale è il pezzo/cartone.

### Cartone

Il prezzo fattura vale come prezzo del cartone quando:

- l'unità della riga è un cartone;
- oppure la confezione dichiara `N` pezzi e la quantità fatturata è compatibile con il cartone secondo la regola del motore.

Non dividere arbitrariamente un prezzo senza una confezione determinabile.

### Prezzi troppo distanti

Se, nello stesso gruppo candidato, i prezzi per pezzo differiscono di oltre **3×** fra minimo e massimo:

- dichiarare l'anomalia del gruppo;
- non scegliere automaticamente il fornitore migliore;
- richiedere verifica della normalizzazione/confezione.

Questo controllo serve a intercettare articoli accorpati male o confezioni diverse.

### Scelta fornitore

Quando un prodotto è correttamente identificato e i prezzi sono confrontabili, la riga del carrello viene proposta al fornitore che costa meno.

La scelta automatica è ammessa solo se il confronto è realmente omogeneo.

---

## Nomi: normalizzazione e matching

Nome commerciale, descrizione di fattura e ingrediente di ricetta sono **tre concetti distinti**.

Non devono essere fusi indiscriminatamente.

La catena è:

**descrizione fattura → articolo da ordinare / articolo di casa → ingrediente di ricetta**

con motori e conferme distinti.

### Articolo da ordinare

L'articolo commerciale deve essere identificato dal testo tramite almeno:

**marca + prodotto + formato + confezione**

quando questi elementi sono presenti.

Esempi di normalizzazione formato/confezione:

- `CL.50` = `50CL` = `ML500`;
- `LT.1,5` = `CL.150`;
- `KG.3X6` conserva quantità e confezionamento;
- `CTX24` / `X24` = confezione da 24 pezzi.

Lotti, scadenze, gradi alcolici, percentuali e altri dati contingenti non fanno parte dell'identità base dell'articolo, salvo quando sono realmente distintivi del prodotto.

### Rumore

La normalizzazione può togliere elementi di rumore non distintivi, ad esempio:

- `VAP`;
- marcatori di confezione già interpretati come `CTX`;
- origine geografica quando non identifica la variante commerciale.

Parole troppo generiche come:

- ACQUA;
- BIRRA;
- VINO;

non sono da sole sufficienti per stabilire che due descrizioni rappresentino lo stesso articolo.

### Match certo

Stesso formato normalizzato e stesse parole distintive significative possono produrre un match certo quando non esistono elementi incompatibili.

### Match probabile

Se tutte le parole distintive di una descrizione sono contenute nell'altra, ma una descrizione contiene parole aggiuntive potenzialmente non distintive:

- classificare come `probabile`;
- non accorpare automaticamente;
- mostrare la scelta a una persona.

Decisioni umane:

- `stesso`;
- `diverso`.

### Materiale/contenitore incompatibile

Vetro e lattina non si uniscono automaticamente.

Un'informazione di confezione/materiale incompatibile prevale sulla somiglianza del nome.

---

## Lettura AI degli articoli

Motore:

`servizi/lettura_articoli_ai.py`

La lettura AI si esegue una volta per descrizione/versione secondo il sistema di cache previsto.

Può estrarre:

- marca;
- prodotto;
- variante;
- formato;
- confezione.

Misura e numero pezzi si acquisiscono **solo se scritti nel testo**.

Mai indovinarli.

Due descrizioni con la stessa lettura strutturata possono essere dichiarate:

`abbinato_ai`

quando le altre regole di compatibilità sono rispettate.

L'abbinamento AI deve restare separabile/revocabile se una persona dimostra che i prodotti sono diversi.

---

## Descrizione fattura → ingrediente di ricetta

Esiste una sola tabella di mapping:

`nome_mapping`

Chiave:

`descrizione_key`

La chiave deriva dalla descrizione normalizzata secondo `chiave_descrizione`, mantenendo il criterio canonico previsto, inclusi minuscolo e spazi normalizzati.

Ogni riga deve poter conservare almeno:

- `nome_canc`;
- `ingredienti_ricetta`;
- `alimentare`;
- `confermato`;
- `fonte`;
- prove e riferimenti necessari.

### Conferma umana

Una proposta non autorizza lo scarico merce.

Per lo scarico automatico prevale il mapping `confermato` da una persona.

### Ripiego senza conferma

Quando manca un mapping confermato, il sistema può usare soltanto regole conservative a parola intera ed escludere lotti per i quali esistono prove incompatibili.

Esempi da non confondere:

- `olive in acqua e sale` non significa che il prodotto sia `sale`;
- `nuova Biancalieve` non significa `uova`;
- `granella di pistacchio` non è automaticamente `crema di pistacchio`.

`nome_mapping` identifica l'ingrediente utile alle ricette.

Non è il registro canonico dell'articolo commerciale da ordinare.

---

## Catalogo fornitore → riga fattura

Il collegamento del catalogo/listino del fornitore con le righe XML usa:

`applica_prezzo_da_fatture`

Ordine di affidabilità:

1. codice articolo della riga XML;
2. nome normalizzato esatto o alias dichiarato;
3. forte sovrapposizione di parole, soltanto quando una riga di fattura porta a un unico prodotto compatibile.

Mai collegare per semplice sottostringa.

Ciò che non si aggancia con sufficiente certezza resta:

- senza prezzo pagato;
- senza stato `già acquistato`.

Non inventare il collegamento per rendere completa la UI.

---

## Web

Un solo ingresso di ricerca web:

`cerca_sul_web`

Non creare una seconda chiamata parallela per la stessa descrizione.

Una categoria può essere assegnata automaticamente soltanto quando:

- il web ha confidenza alta;
- esiste almeno una fonte;
- il risultato web concorda con il testo della fattura;
- la categoria appartiene al dizionario ammesso.

Negli altri casi il risultato web è una **proposta** che attende conferma.

L'AI e il web aiutano a trovare il collegamento.

Non sostituiscono la prova né la decisione umana nei casi ambigui.

---

# 71. Ricette e disponibilità

Disponibilità commerciale ≠ giacenza teorica.

“Esaurito oggi” è una scelta commerciale esplicita.

---

# 72. HACCP

Mai generare valori finti.

Mai:

- random;
- temperature plausibili;
- firme false.

La misura arriva da una persona.

La firma richiede identità valida.

---

# 73. Menu

Lotti spinge nel Menu.

Il Menu non è un secondo proprietario della ricetta.

Le righe `origine="lotti"` sono gestite da Lotti.

---

# 74. Prodotto unico Menu / B&B / Cassa

## TARGET

Stesso prodotto per:

- Menu;
- Lotti;
- B&B;
- Cassa.

Stesso:

- ID;
- PRD;
- nome;
- allergeni;
- prezzi canonici;
- categorie.

## PRODUZIONE

Non assumere completata l'unificazione finché le relative migrazioni non risultano applicate e verificate sul database reale.

---

# 75. Codice prodotto

Formato:

`PRD-000123`

Assegnato dal database.

Mai dall'app.

Mai `max + 1`.

---

# 76. Prezzi Menu

Distinguere:

- banco;
- tavolo.

Un prezzo non deciso resta non deciso.

Non copiare automaticamente uno nell'altro.

---

# 77. Allergeni

Dato mancante ≠ nessun allergene.

Distinguere:

- esclusione motivata;
- conferma “nessuno”;
- dato mancante.

---

# 78. B&B / Colazioni

Applicazione:

`/convenzioni/`

Ruoli:

- titolare;
- albergatore;
- ospite.

La sessione titolare deriva dal gestionale.

L'albergatore ha il proprio PIN.

---

# 79. Wallet B&B

Saldo:

somma movimenti confermati.

Ricariche e rimborsi idempotenti.

Ordine wallet:

addebito atomico.

Fallimento ordine:

storno.

---

# 80. Fatture B&B

Non automatizzare emissione fiscale con API inesistenti.

La ricarica che richiede fattura apre la relativa attesa.

---

# 81. Ordini hotel

Ogni ordine ha:

- giorno;
- orario;
- metodo pagamento;
- stato;- righe.

Il server decide la scadenza.

Non il browser.

---

# 82. Flotta aziendale a noleggio

## REGOLA

Le auto gestite dal sistema sono veicoli a **noleggio a lungo termine**.

Ceraldi Group S.r.l. è intestataria dei contratti e destinataria dei verbali.

Il proprietario/fatturante è il noleggiatore.

Il gestionale deve distinguere:

- veicolo;
- targa;
- noleggiatore;
- contratto;
- periodo contratto;
- assegnazioni nel tempo;
- utilizzatore alla data.

Non dedurre proprietà aziendale dal fatto che il veicolo compare in fattura.

---

## Flotta documentata

| Targa | Veicolo | Noleggiatore | Contratto | Dal | Al | Utilizzatore |
| --- | --- | --- | --- | --- | --- | --- |
| FR788JG | Peugeot 3008 | LeasePlan | 5665218 | 07/07/2018 | 06/01/2022 da confermare | Valerio Ceraldi |
| FS135MG | Ford Edge | ALD | 40254099 | 11/10/2018 | 31/01/2020 | Vincenzo Ceraldi |
| GA304TA | DS7 Crossback | PSA Renting / Free2Move | 7507840825 | 13/05/2020 ricavata, da confermare | 20/05/2021 | Vincenzo Ceraldi |
| GA308TA | DS7 Crossback | PSA Renting / Free2Move | 7507840835 | 01/07/2020 | 20/05/2021 | Giuseppina Pane |
| GE911SC | Mazda CX-5 | ALD | 40634991 | 08/03/2021 | in corso | Valerio fino 26/10/2021; Marina Liuzza fino 26/12/2023; Giuseppina Pane fino 30/04/2024; poi pool |
| GG262JA | Mazda CX-5 | Arval | 1568555 | 13/07/2021 | 11/11/2024 | Valerio Ceraldi |
| GG782PN | Alfa Romeo Stelvio | Leasys | 1202101854 e altri documenti | 24/09/2022 | 04/12/2025 | Vincenzo Ceraldi |
| GW980EP | Mazda CX-60 | Arval | 2637658 | 09/08/2024 | in corso | Antonietta Ceraldi |
| GX037HJ | BMW X1 | ALD / Ayvens | 6074667 | 11/01/2025 | 10/01/2029 | Valerio Ceraldi |
| HB411GV | BMW X3 | Leasys | 1203652735 | 04/12/2025 | 04/12/2028 | Vincenzo Ceraldi |

Questi dati provengono dai documenti esaminati e vanno trattati con il relativo grado di certezza.

---

## Correzioni e anomalie note della flotta

- `QW980EP` è errore di battitura di `GW980EP`, non una seconda auto.
- `GG473WT` compare in un verbale ma non risulta fra le auto aziendali documentate.
- la data iniziale di `GA304TA` è ricavata dalla durata contrattuale e resta da confermare;
- la fine effettiva di `FR788JG` resta da confermare;
- Giuseppina Pane può comparire nello storico assegnazioni anche se non presente nell'anagrafica HR attuale;
- i verbali personali della targa `DW730ZF` non appartengono alla flotta aziendale e restano esclusi.

Non correggere automaticamente una targa simile senza prova documentale.

---

# 83. Verbali e conducente

Il verbale è intestato alla società quando la società è intestataria del veicolo/contratto.

Il conducente non è necessariamente la società né l'utilizzatore attuale.

Il conducente si determina dalla:

- targa;
- data infrazione;
- ora infrazione quando presente;
- storico delle assegnazioni.

Il motore deve scegliere l'utilizzatore **alla data e ora del fatto**.

Non quello di oggi.

---

## Veicolo in pool

Se alla data del verbale il veicolo è in `pool` o non esiste una assegnazione univoca:

`DA_ASSEGNARE`

Non scegliere automaticamente una persona.

La decisione è del titolare.

---

## Cambio conducente nello stesso giorno

Se il verbale non contiene un'ora sufficiente e il giorno coincide con un cambio di assegnazione:

mostrare i candidati.

Non scegliere.

---

# 84. Verbale ↔ fattura

Esiste un solo collegamento canonico fra verbale e fattura.

Il verbale porta il riferimento alla fattura.

Non mantenere sul lato fattura una seconda lista concorrente se non necessaria.

La fattura collegata può essere:

- fattura del noleggiatore;
- spesa di rinotifica;
- spesa di gestione multa;
- altra spesa documentata collegata al verbale.

Il collegamento della fattura **non prova il pagamento del verbale**.

---

# 85. Verbale, pagamento e spese del noleggiatore

Sono fatti distinti:

1. verbale;
2. pagamento del verbale;
3. spese bancarie;
4. fattura del noleggiatore per gestione/rinotifica.

Il noleggiatore può fatturare alla società spese proprie, ad esempio:

- gestione pratica;
- rinotifica;
- trasmissione dati conducente.

Queste spese non sono l'importo della sanzione.

Devono restare collegate al verbale ma contabilmente distinte.

---

# 86. Importo ridotto e importo ordinario

Il verbale può prevedere un importo ridotto entro il termine previsto dalla notifica e un importo ordinario successivo.

La data di riferimento è la **notifica provata**.

Non la data del verbale.

Non inventare la data di notifica quando manca.

Scaduto il termine del ridotto, il sistema può proporre l'importo ordinario soltanto se letto dal documento.

Mai inventarlo.

---

# 87. Pagamento del verbale

Il verbale deve essere considerato **pagato e provato** solo con una prova documentale valida.

Prove ammesse secondo il flusso:

- ricevuta PagoPA;
- quietanza;
- ricevuta PayPal;
- bonifico documentato secondo le regole del dominio.

L'importo deve coincidere con quello dovuto al centesimo.

Un pagamento solo dichiarato non basta per il recupero sul dipendente.

La sola riga bancaria non basta, se manca la prova documentale richiesta dal flusso di recupero.

---

# 88. Recupero del verbale al conducente

Il recupero verso il conducente segue questa sequenza:

1. verbale certo;
2. targa certa;
3. conducente certo alla data/ora;
4. pagamento del verbale provato;
5. importo certo;
6. proposta di trattenuta;
7. conferma del titolare;
8. nota al consulente del lavoro;
9. eventuale recepimento in busta secondo il processo paghe.

La trattenuta **non parte automaticamente**.

Il gestionale produce una proposta.

Solo il titolare può confermarla.

---

# 89. Trattenuta verbale

La proposta nasce soltanto quando:

- il verbale è pagato;
- esiste prova valida;
- l'importo è certo;
- il conducente è certo.

Non nasce da:

- semplice assegnazione del veicolo;
- movimento bancario isolato;
- pagamento dichiarato senza prova;
- fattura del noleggiatore;
- sola presenza di una multa.

Stato iniziale:

`PROPOSTA`

---

# 90. Nota al consulente del lavoro

Dopo la conferma della trattenuta, il gestionale prepara la nota per il consulente.

La nota appartiene al **mese successivo al pagamento del verbale**.

Viene trasmessa insieme alle presenze del mese attraverso i flussi previsti.

Dopo invio riuscito:

`inviato_consulente`

---

## Contenuto minimo della nota

La nota deve contenere:

- numero verbale;
- targa;
- data infrazione;
- ora infrazione se disponibile;
- importo pagato;
- data pagamento;
- IUV o riferimento della prova;
- conducente alla data;
- eventuale riferimento alla quietanza;
- eventuali riferimenti documentali utili.

Il consulente deve poter capire esattamente quale verbale viene recuperato.

---

# 91. Verbali e presenze

## PRODUZIONE ATTUALE

Il gestionale **non usa oggi il foglio presenze per stabilire chi guidava il veicolo**.

Il conducente viene determinato dallo storico di assegnazione del veicolo.

Il foglio presenze svolge un'altra funzione:

porta al consulente la nota del recupero nel mese successivo al pagamento.

Non confondere i due flussi.

---

## FUTURO CONTROLLO POSSIBILE

Un controllo incrociato con le presenze può essere utile come **segnalazione**, non come sostituto dello storico veicolo.

Esempio:

- conducente veicolo = Mario;
- presenze = Mario assente/ferie nella data del verbale.

Il sistema potrebbe generare:

`ASSEGNAZIONE_AUTO_DA_VERIFICARE`

ma non cambiare automaticamente il conducente.

Lo storico del veicolo e la scelta del titolare restano autorevoli.

---

# 92. PagoPA

Una ricevuta PagoPA prova il pagamento.

Non prova automaticamente la natura.

La natura viene dal documento quando esplicita o dalla scelta del titolare.

Una ricevuta PagoPA non crea un verbale.

Senza verbale compatibile resta in attesa.

---

# 93. Cartella di pagamento

La cartella crea l'obbligo.

La ricevuta lo soddisfa se:

- stesso IUV;
- importo al centesimo.

La scadenza dipende dalla notifica reale.

Non inventare data notifica dal PDF.

---

# 94. Sicurezza

Segreti solo in ambienti sicuri.

Mai in:

- codice;
- repository;
- documenti;
- chat;
- file di memoria.

Ogni route nuova deve essere protetta.

Autorizzazione sempre backend.

---

# 95. Sessioni

ERP fornisce la sessione amministratore comune.

HR, Menu e Lotti la riutilizzano quando previsto.

Non creare login admin indipendenti.

---

# 96. MFA

Non dichiarare MFA universale se non implementata universalmente.

Applicare MFA dove previsto dalle operazioni sensibili e dalle policy reali.

---

# 97. Telegram

Telegram è il canale operativo attivo per gli alert previsti.

Non reintrodurre sistemi paralleli salvo flussi espressamente autorizzati.

---

# 98. Design ERP

ERP:

- crema;
- inchiostro;
- terracotta;
- niente blu/viola/freddi;
- `PageHeader`;
- filtri;
- tabella;
- caricamento progressivo;
- card mobile automatiche.

Plus Jakarta Sans.

Icone Lucide.

Niente emoji nelle nuove interfacce applicative.

---

# 99. Design HR / Menu / Lotti

Palette salvia/crema.

Niente blu, indaco, viola, ciano o grigi freddi.

Usare i token esistenti.

Non introdurre un secondo design system.

---

# 100. Mobile

## REGOLA

Vale per tutte e quattro le app (ERP, HR, Menu, Lotti), per ogni pagina, a **390 px** di larghezza:

- nessuno scroll orizzontale (`scrollWidth` ≤ 390 e nessun elemento che sporga);
- contenuto centrato con margine di **16 px per lato**;
- le tabelle diventano card impilate con il meccanismo canonico (`tabelleCard`): non se ne crea un secondo;
- ogni elemento interattivo ha area di tocco minima di **44 × 44 px**.

## VERIFICA

Una pagina non è conforme perché «sembra a posto»: si misura a 390 px con il browser (screenshot prima e dopo, misure di larghezza, margini, tabelle non trasformate, tocchi sotto 44 px) e si riporta pagina per pagina.

Le liste vuote non dimostrano la trasformazione in card: servono righe reali o di prova.

---

# 101. Flussi operativi

Pasticcere e banconista non devono digitare testo quando può essere evitato.

Preferire:

- tendine;
- chip;
- bottoni;
- selezioni.

Testo libero solo come eccezione “Altro”.

---

# 102. AI

Un solo client.

AI:

- legge;
- classifica;
- propone.

Non scrive direttamente fatti contabili.

La conferma applica il motore deterministico.

---

# 103. Lettori AI

Un documento deve avere un percorso canonico.

AI produce proposta.

Il parser deterministico scrive il fatto.

## APERTO

Esistono ancora due lettori AI di documenti: `app/services/ai_document_parser.py` (immagini → AI: fattura, F24, busta paga) e `app/services/document_ai_extractor.py` (testo → AI, più tipi).

I cedolini hanno un solo lettore, `app/services/cedolini_motore.py::leggi_pdf`: lo usano ingresso, riverifica HR e rilettura dell'archivio (`batch_reprocessing`). Non reintrodurre un lettore AI separato per i cedolini.

Consolidare un flusso alla volta.

Non crearne altri.

---

# 104. Ricerca web Lotti

Un solo motore finale.

## APERTO

Esistono ancora due code/giri.

Fonderli.

---

# 105. Legacy

“Legacy” non è una giustificazione per mantenere due sistemi.

Un percorso vecchio resta solo finché esistono:

- dati;
- lettori;
- writer;
- URL necessari.

Prima di eliminare:

contare i dati reali.

---

# 106. legacy_staging

Schema transitorio.

Migrare tramite vie normali.

Mai SQL diretto se il flusso applicativo produce anche:

- audit;
- giornale;
- eventi;
- relazioni.

Dopo migrazione verificata:

eliminare lo schema.

---

# 107. Stato produzione verificato

Questa sezione contiene solo ciò che serve a capire il comportamento corrente.

Non è un diario.

## Servizio

- Render serve `main`.
- Supabase è backend dati.
- cartella Drive unica attiva.
- scheduler attivo.
- protocollo incrementale attivo.
- protocollo completo spento per memoria.

## Fatture

Il 06/10/2026 (02:14–03:18 UTC) le collezioni contabili `invoices`, `corrispettivi`, `movimenti_contabili`, `prima_nota_cassa` e `prima_nota_banca` sono state azzerate e ricreate da zero; la causa non è nel log applicativo. Al 07/10 `invoices` ha 21 fatture, il report AdE 2026 (`fatture_report_ae`) ne conta 902, di cui 795 con `invoice_id` che non esiste più e 888 con pagamento dichiarato dal titolare. Gli XML sono su Drive in `ELABORATE`: la ricostruzione passa da `POST /api/admin/documenti/rimetti-in-coda` (dry-run, poi reale) e dal giro della cartella unica; i pagamenti dichiarati si applicano da soli all'arrivo di ogni fattura. Non creare un secondo importatore.

Persistono ID storici misti testo/numero.

Il pregresso non è completamente normalizzato.

Esistono partite e relazioni da riallineare.

## Banca

Banco BPM è collegato via Enable Banking (consenso PSD2 fino al 25/12/2026): il giro automatico delle 07:15 e 09:00 (Europe/Rome) legge gli ultimi `ENABLE_BANKING_GIORNI_GIRO` giorni (difetto 7) e importa solo i movimenti certamente nuovi; `ENABLE_BANKING_DAL=AAAA-MM-GG` fa rileggere da quella data una volta sola (usato dopo l'azzeramento del 06/10/2026 per il 2026 intero). La fonte API resta provvisoria finché non arriva l'estratto conto ufficiale.

Persistono:

- movimenti senza categoria;
- relazioni incomplete;
- fatture con stato di riconciliazione incoerente.

## Contabilità

Persistono scritture storiche non quadrate.

Il pagamento non chiude ancora tutti i debiti nel giornale.

Il bilancio non usa ancora la competenza in tutti i percorsi.

## HR

Persistono:

- bonifici da associare;
- riferimenti cedolino orfani;
- moduli duplicati.

## Menu / prodotto unico

Non considerare completata l'unificazione finché le migrazioni non risultano applicate e collaudate sul database reale.

## Drive

L'incrementale non vede tutte le eliminazioni/spostamenti.

## AI

Client unico raggiunto.

Pipeline duplicate ancora presenti.

## Flotta / verbali

Lo storico dei veicoli e degli utilizzatori deve essere completato e consolidato nel gestionale.

Le assegnazioni storiche documentate sono la base per individuare il conducente alla data del verbale.

Le presenze non sono oggi una fonte per decidere il conducente.

---

# 108. Aperto — priorità critica

## P1 — Contabilità

Libro giornale spento dal 07/10/2026 (§24): i punti 1, 4 e 5 restano fermi finché il titolare non lo riaccende; la priorità operativa è la Prima Nota cassa/banca alimentata dalle fatture (§29) e dai pagamenti dichiarati.

1. Fare in modo che ogni pagamento chiuda il debito nel libro giornale (sospeso: giornale spento).
2. Correggere il bilancio affinché usi `data_competenza`.
3. Ricostruire debiti/crediti alla data di chiusura.
4. Rettificare note di credito storiche errate (sospeso: giornale spento).
5. Analizzare scritture non quadrate (sospeso: giornale spento).

---

# 109. Aperto — fatture e banca

1. Riallineare fatture riconciliate senza prova coerente.
2. Riparare relazioni senza `fattura_id`.
3. Recuperare fatture senza partita.
4. Ridurre stati pagamento duplicati.
5. Uniformare gli ID futuri.
6. Classificare movimenti senza categoria.

---

# 110. Aperto — documenti

1. Eliminare decisioni basate sul nome file.
2. Completare backfill relazioni.
3. Bonificare collegamenti protocollo.
4. Verificare blob non referenziati.
5. Non creare nuovi endpoint originali paralleli.

---

# 111. Aperto — HR

1. Eliminare fork residui.
2. Riparare bonifici con cedolino orfano.
3. Ridurre coda bonifici.
4. Verificare doppio conteggio acconto.
5. Portare tutti gli ingressi cedolino sul motore unico.

---

# 112. Aperto — Menu / B&B / Cassa

1. Applicare migrazioni prodotto unico.
2. Verificare registro migrazioni.
3. Verificare `public.menu_products`.
4. Verificare `bb_prodotti`.
5. Verificare codice PRD.
6. Provare voucher.
7. Provare ordine hotel.
8. Ripubblicare Menu da Lotti.
9. Collegare ricette senza doppioni.
10. Esportare migrazioni Cassa/Catalogo mancanti.

---

# 113. Aperto — IVA / LIPE

1. Completare 6013.
2. Completare 6099.
3. Credito annuale.
4. Compensazione orizzontale.
5. Conguaglio dicembre.
6. Unificare credito precedente.
7. Implementare confronto LIPE con soglia di piccolo scostamento configurata.
8. Evidenziare le componenti dello scarto.
9. Creare attese tributo da LIPE quando F24 manca.
10. Collegare quietanza con protocollo alle attese LIPE senza creare F24 fittizi.

---

# 114. Aperto — F24

1. Consolidare F24 ↔ banca.
2. Eliminare matching duplicati.
3. Gestire modelli senza data/saldo.
4. Completare riscontro contributi.
5. Correggere parser storici solo con PDF reali.
6. Mai forzare F24 non quadrato.

---

# 115. Aperto — Drive

1. Rendere sostenibile una verifica completa periodica.
2. Continuare bonifica relazioni.
3. Collegare originali HR quando determinabili.
4. Eliminare vecchi sync non canonici.

---

# 116. Aperto — Lotti

1. Smaltire arretrato.
2. Consolidare ricerca web.
3. Risolvere unità non convertibili.
4. Confermare mapping.
5. Migrare foto residue a Storage.
6. Non inventare scadenze o lotti.

---

# 117. Aperto — Flotta e verbali

1. Popolare l'anagrafica veicoli con i contratti documentati.
2. Registrare lo storico assegnazioni con `dal/al`.
3. Marcare `GW980EP` come targa corretta e non creare `QW980EP`.
4. Tenere `GG473WT` da verificare perché compare in un verbale ma non nella flotta nota.
5. Escludere i verbali personali `DW730ZF`.
6. Confermare le date non provate, in particolare GA304TA e FR788JG.
7. Collegare le fatture del noleggiatore ai relativi verbali quando documentato.
8. Conservare separate sanzione e spesa gestione/rinotifica.
9. Generare proposta trattenuta soltanto dopo pagamento documentato e conducente certo.
10. Inviare al consulente la nota nel mese successivo al pagamento.
11. Valutare in futuro un controllo presenze come alert, mai come assegnazione automatica del conducente.

---

# 118. Aperto — B&B

1. Attivare SumUp solo con chiave configurata.
2. Chiudere SQL obsolete quando possibile.
3. Logout sessione titolare DB.
4. Configurare URL recensioni.
5. Configurare WhatsApp solo per recensioni.
6. Completare varianti.
7. Rivedere prezzi extra tavolo.
8. Rimuovere demo al lancio.

---

# 119. Aperto — sicurezza Git

Nella cronologia sono esistiti segreti reali.

Prima:

ruotare credenziali.

Solo dopo autorizzazione:

eventuale riscrittura cronologia.

Riscrivere Git non revoca le credenziali.

---

---

# 119A. Aperto — motore universale di riconciliazione

1. Uniformare i livelli `PREVISTO`, `PREDISPOSTO`, `DOCUMENTATO`, `TROVATO_IN_BANCA`, `PARZIALMENTE_RICONCILIATO`, `RICONCILIATO`, `DA_VERIFICARE` senza cancellare gli stati specialistici già necessari ai domini.
2. Rendere esplicite le allocazioni uno-a-molti, molti-a-uno e molti-a-molti con importo allocato al centesimo, fonte, destinazione, certezza, metodo, autore/algoritmo e timestamp.
3. Trattare PartenoPay come origine/portale del flusso pagoPA, non come motore contabile indipendente.
4. Modellare cartelle, rottamazioni, dilazioni INPS e avvisi bonari come posizione principale → eventuale piano → rate → pagamento/prova → banca, senza trasformare ogni rata in un debito scollegato.
5. Versionare le regole normative che cambiano nel tempo, incluse scadenze e condizioni delle rateizzazioni; non cablare nel codice limiti che dipendono dalla normativa vigente.
6. Collegare il calendario fiscale previsionale a scadenze normative, storico aziendale, documenti reali e dati operativi, distinguendo sempre previsione, calcolo, documentazione, predisposizione, pagamento e riconciliazione.
7. Fare alimentare alla tesoreria le uscite fiscali e finanziarie previste senza trasformarle in debiti certi prima della prova o del documento autorevole.


---

# 120. Verifica delle modifiche

Per ogni modifica pertinente:

1. test mirati;
2. suite backend quando necessaria;
3. test frontend;
4. build;
5. `git diff --check`;
6. revisione avversariale;
7. commit dei soli file pertinenti;
8. push branch;
9. PR finale;
10. merge su `main`;
11. verifica CI;
12. verifica health;
13. verifica commit pubblicato;
14. controllo live del flusso.

---

# 121. Revisione avversariale

Prima del merge chiedersi:

1. La chiave esiste sui dati reali?
2. Ho dichiarato fatto qualcosa che non ho verificato?
3. Esiste già un altro motore?
4. Sto trasformando un dato sconosciuto in zero?
5. Sto usando il nome file come prova?
6. Sto creando una seconda fonte?
7. Ho aggiornato fatto e relazioni?
8. Il secondo giro resta idempotente?
9. Una prova documentale viene confusa con una prova bancaria?
10. Una proiezione UI viene confusa con il fatto canonico?

---

# 122. Idempotenza

Il secondo ingest della stessa fonte deve produrre:

`nuovi = 0`

e nessuna nuova scrittura contabile.

Se crea un secondo fatto:

il flusso è difettoso.

---

# 123. Verifica live

Non dichiarare completato perché:

- compila;
- test verdi;
- HTTP 200;
- pagina visibile.

Verificare:

- fatto;
- relazioni;
- deduplica;
- stato;
- pagamento;
- prova;
- scrittura;
- risultato UI.

---

# 124. Regola finale

Prima di creare qualcosa di nuovo chiedersi:

**“Esiste già il motore che dovrebbe fare questa cosa?”**

Se sì:

**correggere quello.**

Non aggiungere:

- secondo parser;
- secondo writer;
- secondo stato;
- secondo archivio;
- seconda riconciliazione;
- seconda fonte autorevole;
- secondo endpoint equivalente.

L'obiettivo di GestionaleCloud è che ogni evento reale esista una sola volta e che documenti, obblighi, pagamenti, prove, contabilità e interfaccia siano collegati attraverso la stessa catena di dati.
