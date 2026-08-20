# Audit professionale end-to-end della contabilita

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data del collaudo: 5 agosto 2026  
Repository: `ceraldicontabilita/GestionaleCloud`  
Ambito: fatture passive, Prima Nota, nota provvisoria, estratti conto, assegni, piano dei conti, previsioni acquisti, F24, IVA, ritenute, router, endpoint e interfaccia React.

## Esito esecutivo

Il codice locale e stato corretto e il collaudo automatico e concluso senza errori bloccanti:

- 1.016 test backend superati;
- 2 test saltati intenzionalmente dalla suite;
- 78 test frontend superati su 13 file;
- build React di produzione completata;
- compilazione Python completata;
- 1.045 operazioni OpenAPI su 969 percorsi documentati;
- nessuna collisione runtime tra metodo HTTP e percorso;
- nessun errore rilevato da `git diff --check`.

Questo audit non ha cancellato, riscritto o riconciliato automaticamente dati aziendali reali. Le verifiche sui dati 2026 sono state eseguite in sola lettura; le correzioni riguardano il codice e le sue protezioni.

## Evidenze 2026 verificate in sola lettura

### Fatture e Prima Nota

- 272 fatture attive nel periodo verificato;
- 144 fatture marcate come pagate e 128 non pagate;
- tutte le fatture verificate dispongono delle righe di dettaglio;
- nessun duplicato attivo rilevato con la chiave contabile controllata;
- 126 collegamenti visibili verso Prima Nota;
- 32 fatture marcate come pagate avevano soltanto registrazioni di Prima Nota eliminate logicamente o riferimenti non piu validi.

La precedente logica poteva quindi nascondere fatture dalla nota provvisoria fidandosi del solo flag `pagata`. La nuova logica ricostruisce l'evidenza contabile effettiva e rimette tra le posizioni da verificare le fatture prive di una registrazione attiva e, per i pagamenti bancari, prive di un identificativo finanziario riconoscibile.

### Movimenti e duplicati

- 411 movimenti Cassa e 1.035 movimenti Banca nel perimetro 2026 letto;
- nessun duplicato operativo certo con chiave stretta;
- 193 somiglianze con chiave rilassata, principalmente costi e commissioni bancarie ricorrenti: non sono state eliminate perche la sola somiglianza non costituisce prova di duplicazione;
- nessun identificativo di evidenza bancaria riutilizzato nei movimenti controllati.

### Assegni

- 91 assegni attivi verificati;
- nessun numero assegno duplicato;
- 18 collegamenti a fatture e 81 riferimenti a evidenze bancarie.

### Previsioni acquisti

- 1.207 righe statistiche 2026;
- copertura delle 272 fatture verificate;
- nessun duplicato sulla combinazione fattura e descrizione normalizzata.

## Correzioni implementate

### Previsioni acquisti

- aggiunta la quantita acquistata nell'anno corrente;
- mantenuta separata la quantita dell'anno precedente;
- aggiunte differenza assoluta e variazione percentuale;
- eliminato il falso `Spesa totale: euro 0,00` quando il costo non e disponibile: l'interfaccia segnala ora che il costo manca;
- migliorata l'etichetta prodotto e mantenuta la deduplicazione delle righe.

### Prima Nota e nota provvisoria

- la presenza del solo flag `pagata` non vale piu come prova;
- una registrazione eliminata logicamente non chiude piu la fattura;
- per la banca servono riferimenti riconoscibili a estratto conto, movimento bancario, PayPal, Nexi, carta o altra fonte finanziaria;
- i pagamenti in contanti restano confermati solo da una registrazione Cassa attiva;
- le fatture senza evidenza sono esposte nella nota provvisoria o nella sezione in attesa di banca;
- il contatore della scheda include entrambe le categorie;
- la manutenzione rimuove anche alias e identificativi residui dalle registrazioni automatiche incoerenti.

### Assegni e carnet

- eliminata la collisione tra il router assegni corretto e il vecchio endpoint pubblico;
- generazione carnet trasformata da molte chiamate sequenziali a una verifica unica e un inserimento multiplo;
- mantenuti gli zeri iniziali nella numerazione;
- aggiunto indice univoco e sparso sul numero assegno;
- caricamento delle fatture associabili spostato su un endpoint leggero con soli campi necessari e deduplicazione.

### Piano dei conti

- verificata la deduplicazione difensiva per codice;
- verificato l'indice univoco sul codice conto;
- verificata la gestione concorrente della creazione senza doppia riga visibile;
- eliminata la collisione del vecchio endpoint pubblico fornitori che alterava la mappa dei router contabili.

### F24, email e quietanze

- separato in modo rigoroso `documento presente`, `quietanza presente` e `addebito bancario verificato`;
- una quietanza senza movimento bancario non marca piu il modello come pagato;
- una dichiarazione manuale non viene piu trattata come prova bancaria;
- la riconciliazione automatica richiede data, importo e un candidato univoco;
- i casi ambigui rimangono da verificare;
- il parser estratto conto e il router banca usano la stessa regola;
- il download email riconosce prima le quietanze tramite elementi forti del documento;
- modelli e quietanze passano dai servizi canonici con hash e protezione duplicati;
- ritenute e agente fiscale usano la stessa evidenza bancaria e non chiudono piu una posizione sulla sola quietanza.

### IVA mensile e ravvedimento

- aggiunto il collegamento tra mese IVA e codici tributo da 6001 a 6012;
- separato l'importo della riga IVA dal totale complessivo del modello F24;
- mostrati scadenza, modelli candidati, ambiguita, importo IVA e prova bancaria;
- gestito il termine ordinario del giorno 16 del mese successivo, con la specificita del versamento di luglio e lo slittamento dei giorni non lavorativi;
- una posizione scaduta senza prova bancaria viene segnalata come da verificare per ravvedimento;
- sono proposti i riferimenti 8904 per la sanzione IVA e 1991 per gli interessi IVA;
- il sistema non inventa ne contabilizza automaticamente sanzioni o interessi: l'importo deve essere determinato sulla base della data effettiva, della violazione e della disciplina applicabile, con verifica professionale.

## Router ed endpoint

Sono state rimosse le sovrapposizioni che rendevano non deterministico il comportamento di alcune pagine:

- `GET /api/assegni` punta al router bancario corretto;
- `GET` e `POST /api/suppliers` puntano al modulo fornitori canonico;
- `GET /api/dashboard/stats` punta al router report corretto;
- i vecchi endpoint restano disponibili con suffisso `-legacy` e non sono inclusi nello schema pubblico principale.

E stato inoltre aggiunto l'endpoint leggero per le fatture associabili agli assegni e l'endpoint di verifica del versamento IVA mensile.

## Rischi residui e condizioni di rilascio

Nell'ambiente locale di collaudo risultano avvisi di configurazione che devono essere verificati nel servizio di produzione, senza copiare segreti nei file o nel repository:

- origini CORS non ristrette esplicitamente;
- servizio SMTP non configurato nell'ambiente locale;
- codice dell'area riservata non configurato nell'ambiente locale;
- chiave applicativa temporanea in assenza di una chiave persistente o del recupero da database;
- dati Browserslist non aggiornati, avviso non bloccante della build frontend;
- alcune API di dipendenze sono deprecate ma la suite resta verde.

Il collegamento alla casella email F24 e la presenza delle variabili nel servizio di produzione devono essere verificati sul runtime effettivo. Questo verbale non certifica che una casella non configurata localmente abbia gia scaricato i documenti reali.

## Stato del rilascio

Le modifiche sono presenti e collaudate nella copia locale del repository canonico. Non sono state distribuite automaticamente sul servizio pubblico e non sono stati modificati dati reali. Prima del rilascio occorre isolare le modifiche applicative dagli altri file gia presenti nella copia di lavoro, creare una revisione Git controllata e verificare dopo il deploy gli endpoint, la configurazione email e i conteggi in sola lettura.

## Criterio contabile adottato

Il principio applicato in tutto il flusso e il seguente:

`documento -> fattura/F24 -> registrazione contabile -> evidenza finanziaria -> riconciliazione confermata`

La presenza di un documento o di un flag non sostituisce l'evidenza finanziaria. Nessun collegamento ambiguo viene creato automaticamente e nessun duplicato viene eliminato senza una chiave certa.
