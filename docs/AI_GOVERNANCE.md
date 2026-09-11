# AI Governance — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-11
storage_architecture: supabase-runtime-drive-originals
-->

## Scopo

L'AI nel GestionaleCloud è un componente supervisionato. Può leggere, estrarre,
classificare, confrontare, proporre e motivare. Non può trasformare una fonte in
una prova che quella fonte non contiene.

## Classi di risultato

Ogni elaborazione AI deve distinguere almeno:

- `verificato`: sostenuto da una fonte leggibile e identificabile;
- `probabile`: inferenza utile ma non sufficiente per un'azione irreversibile;
- `non_verificato`: campo assente, ambiguo o non dimostrabile;
- `conflitto`: due o più fonti affidabili non concordano.

Ogni output strutturato deve includere, quando applicabile:

- `source_type` e identificatore della fonte;
- campi estratti con provenienza;
- `confidence` soltanto come supporto, mai come prova;
- `uncertain_fields`;
- `conflicts`;
- `possible_links`;
- `automatic_actions_allowed`;
- `human_review_required`.

## Confini di evidenza

1. Un movimento bancario reale può provare un addebito/accredito bancario.
2. Un PDF di bonifico prova la disposizione/documentazione del bonifico, non
   automaticamente l'addebito.
3. Un cedolino prova il contenuto retributivo leggibile nel documento, non il
   pagamento.
4. Una fattura prova il debito/documento, non il pagamento.
5. Una ricevuta PagoPA e un movimento bancario sono prove distinte finché non
   vengono collegate in modo univoco.
6. Una proposta AI o una similarità per importo/data/descrizione non è una prova.
7. Una corrispondenza ambigua resta `Da verificare`.

## Contratto documentale operativo

Lo stato operativo di un documento (`nuovo`, `processato`, `errore`) è distinto
dallo stato della sua evidenza (`verificato`, `probabile`, `non_verificato`,
`conflitto`). Un documento processato non diventa quindi automaticamente una
fonte verificata.

L'anteprima canonica di importazione deve precedere la conferma, essere non
mutante e legare la conferma all'hash SHA-256 del file e al tipo rilevato. Il
solo nome file non autorizza una riclassificazione automatica. Le estrazioni AI
restano proposte revisionabili e non scrivono direttamente fatti operativi nei
registri contabili, fiscali, bancari o del personale.

## Regole per agenti decisionali

Gli agenti CFO, Tesoreria, Contabile, Fiscale e Acquisti devono restituire:

- fatto osservato;
- fonti;
- ragionamento sintetico verificabile;
- proposta;
- impatto previsto;
- rischio;
- prerequisiti mancanti;
- livello operativo richiesto;
- necessità di conferma umana.

Livelli:

- L0: lettura e sintesi;
- L1: proposta motivata;
- L2: preparazione di un'azione reversibile, senza eseguirla se non autorizzata;
- L3: azione sensibile solo con conferma umana e MFA quando previsto;
- L4: vietato per operazioni autonome irreversibili o ad alto impatto.

## Metodo per sviluppo e refactoring

Ogni task AI sul repository segue questa sequenza:

1. **Censimento**: file, endpoint, componenti, dipendenze, persistenza e test.
2. **Contratto**: definire comportamento attuale e comportamento atteso.
3. **Evidenze**: separare ciò che è osservato da ciò che è ipotizzato.
4. **Rischio**: classificare impatto su dati, contabilità, sicurezza e UI.
5. **Modifica minima**: riusare il codice esistente e ridurre duplicazioni.
6. **Verifica**: test automatici, build, query o endpoint reali pertinenti.
7. **Regressione**: controllare che il cambiamento non alteri le regole di prova.
8. **Tracciabilità**: commit e motivazione leggibili.

## Supabase

Supabase è il registro operativo strutturato. Google Drive conserva gli originali.
Google Sheets è solo compatibilità transitoria/rollback e non deve essere scelto
per nuovi flussi.

Le RPC privilegiate devono:

- autenticare esplicitamente il chiamante applicativo;
- usare un segreto che non sia esposto nel browser;
- fissare `search_path`;
- usare privilegi minimi;
- validare input e limiti;
- essere idempotenti quando scrivono;
- non esporre dati tramite errori dettagliati.

## Definition of done per funzioni AI

Una funzione AI è pronta soltanto quando:

- output e schema sono deterministici abbastanza da essere testati;
- esistono casi positivi, nulli, ambigui e conflittuali;
- le fonti sono citabili/ricostruibili;
- nessuna azione irreversibile deriva dalla sola confidence;
- gli errori degradano in `Da verificare` invece di inventare dati;
- il flusso è verificato con dati reali o fixture rappresentative;
- non introduce un secondo archivio canonico.