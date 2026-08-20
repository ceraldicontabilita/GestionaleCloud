# Audit pagina per pagina: Contabilita, PayPal e Assegni

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data audit: 5 agosto 2026
Repository: `ceraldicontabilita/GestionaleCloud`
Ambiente osservato: applicazione di produzione, anno globale 2026
Metodo: apertura reale di ogni pagina, attesa del caricamento, verifica DOM,
mappatura pagina-route-endpoint-collection, confronto tra fonti e test di regressione.

> Questo documento non contiene importi, documenti o credenziali aziendali. I
> valori reali sono stati usati soltanto per individuare gli scarti e non sono
> copiati nel repository pubblico.

## Esito sintetico

Il problema principale non era un singolo errore grafico: pagine diverse
leggevano fonti diverse e presentavano i risultati come se fossero equivalenti.
In particolare, il Bilancio di Verifica ricostruiva le scritture dalle fonti
operative, mentre Libro Giornale e Libro Mastro usavano il registro definitivo.
La conseguenza era uno sbilancio strutturale e un numero di movimenti non
confrontabile.

Le correzioni mantengono separate tre evidenze:

1. documento operativo (fattura, corrispettivo, assegno, transazione PayPal);
2. registrazione contabile definitiva (`movimenti_contabili`);
3. prova finanziaria esterna (estratto conto, quietanza F24, sorgente PayPal).

Una quadratura del registro non viene piu presentata come completezza se
esistono documenti ancora non registrati.

## Matrice pagina per pagina

| Pagina | Endpoint principale | Esito audit | Intervento |
|---|---|---|---|
| `/contabilita` | `/api/piano-conti` | conti ripetuti e saldo banca da fonte diversa dalle altre pagine | deduplica per codice, indice univoco, saldo contabile da Prima Nota; lo scarto bancario resta separato |
| `/contabilita/bilancio` | `/api/bilancio/stato-patrimoniale` | caricamento valido; saldo coerente con Prima Nota, patrimonio netto di quadratura da leggere con cautela | mantenuta fonte contabile; non trasformato lo scarto in una rettifica automatica |
| `/contabilita/verifica` | `/api/contabilita-gestionale/bilancio-verifica` | grave: ricostruzione da fonti operative, duplicazioni e sbilancio | collegata esclusivamente a `movimenti_contabili`; aggiunto backlog dei documenti non registrati |
| `/contabilita/giornale` | `/api/contabilita-gestionale/libro-giornale` | fonte corretta ma registro incompleto | mantenuto registro unico; l'incompletezza resta bloccante e visibile |
| `/contabilita/controllo` | endpoint POS/corrispettivi e banca | scarti reali tra RT, chiusure manuali, POS e banca | nessuna compensazione inventata; evidenze mantenute distinte per riconciliazione |
| `/contabilita/calendario` | `/api/fiscalita/calendario/{anno}` | ritenute e INPS associate al mese sbagliato; scadenze generate non aggiornate | periodo al mese precedente, agosto al 20, slittamento weekend, upsert senza perdere completamenti |
| `/contabilita/cespiti` | `/api/cespiti` | pagina funzionante; classificazioni e ammortamenti richiedono verifica documentale | nessuna riclassificazione automatica senza prova; rischio residuo documentato |
| `/contabilita/finanziaria` | `/api/finanziaria/summary` | filtri soft-delete incompleti; errore backend trasformato in zeri; IVA presentata come definitiva | filtri corretti, errore visibile, IVA etichettata come stima documentale classificata |
| `/contabilita/chiusura` | endpoint chiusura esercizio | correttamente bloccata da documenti non contabilizzati e mesi mancanti | mantenuto blocco; nessuna chiusura forzata |
| `/contabilita/budget` | endpoint budget | stato vuoto valido, non errore | nessuna generazione di valori fittizi |
| `/contabilita/mutui` | endpoint mutui | stato vuoto valido | nessuna generazione di finanziamenti fittizi |
| `/contabilita/avanzata` | `/api/contabilita/disponibilita-liquide` | saldi calcolati con filtri e riporto diversi dalle altre pagine | introdotto servizio unico dei saldi; Prima Nota ed Estratto Conto esposti separatamente con scarto |
| `/contabilita/utile` | `/api/centri-costo/utile-obiettivo` | percentuale su target prorata mostrata come annuale; valore positivo mostrato come “gap” | percentuale annuale, gap non negativo e surplus separato |
| `/contabilita/previsioni-acquisti` | endpoint previsioni | mancava evidenza esplicita della quantita corrente e il costo zero era ambiguo | quantita anno corrente/precedente/delta esplicite; costo mancante distinto da costo zero |
| `/riconciliazione/paypal` | `/api/paypal-statements/*`, `/api/paypal-api/*` | movimenti bancari senza sorgente PayPal non segnalati; API non configurata invisibile; doppio conteggio cambi | banner anomalia, stato configurazione senza segreti, conversioni T02 escluse dal doppio conteggio |
| `/riconciliazione/assegni` | `/api/assegni/*` | carnet lento, timeout fatture, salute calcolata includendo fogli vuoti | insert batch, endpoint fatture leggero, statistiche per anno sui soli assegni operativi, carnet vuoti separati |

## Controlli contabili applicati

- Un solo registro definitivo per Bilancio di Verifica, Giornale e Mastro.
- DARE e AVERE verificati su ogni scrittura registrata.
- Backlog di fatture e corrispettivi separato dalla quadratura.
- IVA del corrispettivo letta dal dettaglio XML quando disponibile; il 10% e'
  soltanto fallback storico.
- Ripartizione contanti/POS non quadrata bloccata come `da_verificare`.
- Saldo contabile banca e saldo Estratto Conto non si sostituiscono a vicenda.
- Fogli vuoti di un carnet esclusi da salute, beneficiario e fattura.
- Conversioni valuta PayPal collegate alla transazione e non sommate due volte.
- Nessun dato aziendale cancellato o corretto automaticamente durante l'audit.

## Calendario fiscale

Per agosto 2026 il generatore usa il 20 agosto per IVA periodica e ritenute del
mese precedente, coerentemente con lo Scadenzario ufficiale dell'Agenzia delle
Entrate:

<https://www1.agenziaentrate.gov.it/servizi/scadenzario/main.php?entroil=20-08-2026&op=2&tipologia=C&vista=1>

Il calendario e' un supporto operativo. L'importo dovuto, l'avvenuto pagamento
e l'eventuale ravvedimento devono continuare a dipendere da liquidazione, F24,
quietanza e movimento bancario verificati.

## Rischi residui prima del deploy

1. Il registro definitivo deve essere popolato con le registrazioni mancanti;
   il software ora mostra il backlog ma non inventa scritture.
2. Le classificazioni dei cespiti richiedono controllo sui documenti sorgente.
3. Gli scarti POS/RT/banca richiedono le chiusure manuali e le evidenze reali.
4. PayPal richiede sorgente documentale oppure configurazione server API.
5. Le correzioni diventano operative sul sito solo dopo merge e deploy della PR.

## Criterio di accettazione

La correzione e' accettabile soltanto se:

- test backend completi verdi;
- test frontend verdi;
- build di produzione riuscita;
- nessuna collisione router/metodo;
- pagine desktop e mobile mostrano loading, errore e stato vuoto distinguibili;
- verifica finale post-deploy sui medesimi URL.
