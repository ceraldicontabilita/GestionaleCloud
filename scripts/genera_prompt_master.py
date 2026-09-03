"""Rigenera PROMPT_MASTER.md dal codice e dai cataloghi correnti.

Il file prodotto e' l'unica specifica normativa del progetto. Le appendici
meccaniche (pagine, variabili ed endpoint) impediscono che il prompt diverga
dalla superficie realmente versionata.
"""
from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-08-21"


PAGE_PURPOSES = {
    1: "Login sicuro, sessione, MFA e redirect alla destinazione autorizzata.",
    2: "Area riservata separata, con accesso dedicato e movimenti auditabili.",
    3: "Dashboard derivata dai registri, con indicatori cliccabili e nessun saldo hardcoded.",
    4: "Inserimento rapido idempotente di corrispettivi, versamenti, pagamenti, apporti e presenze.",
    5: "Archivio unico fatture ricevute, PDF/XML, provenienza, pagamento e spostamento Cassa/Banca.",
    6: "Corrispettivi giornalieri, aliquote, mezzi di pagamento e scritture Cassa/POS senza duplicati.",
    7: "Anagrafica fornitori univoca, fatture, residui, IBAN, metodo e merge controllato.",
    8: "Prima Nota Cassa/Banca/SumUp/Soci come viste coerenti del ledger, raggruppate per giorno.",
    9: "Audit Prima Nota con liste esatte, dry-run, correzione deterministica e rollback.",
    10: "Flotta ricostruita da fatture di noleggio, contratti, targhe e storico driver.",
    11: "Riconciliazione verbali, veicoli, driver, pagamenti, quietanze e documenti.",
    12: "Costi noleggio per veicolo: canoni, pedaggi, verbali, bollo e riparazioni.",
    13: "Fascicolo del verbale con PDF, importo, targa, trasgressore, driver e prove.",
    14: "Piano dei conti gerarchico, regole versionate e movimenti collegati.",
    15: "Bilancio calcolato da scritture valide, quadratura e drill-down.",
    16: "Verifica bilancio con anomalie spiegate e link alla scrittura origine.",
    17: "Libro giornale progressivo, bilanciato, filtrabile, esportabile e auditabile.",
    18: "Controllo mensile con lista per ogni anomalia e stato di risoluzione.",
    19: "Calendario fiscale con fonte, scadenza, stato, promemoria e documento collegato.",
    20: "Cespiti, documento origine, ammortamenti Decimal, dismissioni e storia.",
    21: "Posizione finanziaria, flussi, debiti, crediti e finanziamenti soci non duplicati.",
    22: "Chiusura esercizio con checklist, anteprima, conferma forte, audit e rollback.",
    23: "Budget versionato e confronto consuntivo per mese, conto e centro.",
    24: "Mutui, rate, quota capitale/interessi, banca e residuo riconciliato.",
    25: "Analisi contabili avanzate come viste derivate, con formule e drill-down.",
    26: "Simulazione utile obiettivo separata dai consuntivi e senza scritture reali.",
    27: "Previsioni acquisti basate su storico e scadenze, senza ordini automatici.",
    28: "Suggerimenti di apprendimento con evidenza, confidenza, approvazione e revoca.",
    29: "Scadenziario fornitori con residui, parziali, prove e alert navigabili.",
    30: "Ritenute per percipiente, periodo, aliquota, F24 e quadratura annuale.",
    31: "Indice unico delle riconciliazioni con code, stati e contatori navigabili.",
    32: "Riconciliazione bancaria deterministica, candidati motivati e operation_id.",
    33: "F24 con PDF, righe tributo, quietanza, banca e ricerca per codice.",
    34: "Riconciliazione stipendi per dipendente, IBAN, periodo e regola del giorno 25.",
    35: "Riconciliazione documenti con originale, classificazione, candidati e provenienza.",
    36: "Archivio bonifici con CRO/TRN, beneficiario, periodo, descrizione e associazioni persistenti.",
    37: "Assegni distinti per numero/data/importo, fatture collegate e casi ambigui.",
    38: "PayPal interconnesso con banca, fatture, Prima Nota e prove tramite operation_id.",
    39: "Coerenza fra corrispettivi, POS, commissioni, giorni di vendita e accrediti.",
    40: "Import documenti/ZIP con validazione, salvataggio reale, hash e report.",
    41: "Archivio documenti indicizzati con metadati, originale, relazioni e viewer.",
    42: "Controlli di coerenza riproducibili con query, lista, severita e risoluzione.",
    43: "Movimenti banca con riga fonte, classificazione e stato di associazione.",
    44: "Fascicolo per commercialista con registri, documenti, manifest e quadrature.",
    45: "Pianificazione di attivita e adempimenti derivati, assegnati e notificati.",
    46: "Visure con soggetto, tipo, stato e documento, senza richieste esterne automatiche.",
    47: "Agenti e automazioni con scopo, permessi, run, log, esito e disattivazione.",
    48: "Configurazione ingest email F24, query, mittenti, test e ultima scansione.",
    49: "Configurazione AI tramite riferimenti a segreti, modello, limiti e health.",
    50: "Integrazioni API con scope, token ruotabili, OpenAPI, rate limit e revoca.",
    51: "PagoPA con IUV, ente, avviso, ricevuta, banca e scelta nei casi ambigui.",
    52: "Mittenti email attendibili con canale, documento atteso, priorita e audit.",
    53: "Admin con salute, job, errori, configurazione non sensibile e azioni protette.",
    54: "MFA amministrativa, enrollment, revoca, recovery e step-up authentication.",
    55: "Elaborazioni batch idempotenti con progresso, errori per record e retry selettivo.",
    56: "Alias legacy temporaneo verso elaborazioni, senza componente o router duplicato.",
    57: "Utenti, ruoli, attivazione, reset sicuro e audit senza auto-elevazione.",
    58: "Mappa gestionale generata dal catalogo con moduli, route, flussi e health.",
    59: "IVA, liquidazioni, fatture, corrispettivi, F24, periodi e quadrature.",
    60: "Fatture estere, paese, valuta, integrazione/autofattura e trattamento IVA.",
    61: "Dati ISA derivati, tracciabili, quadrati ed esportabili senza valori inventati.",
    62: "Indice Drive autorevole per metadati, hash, percorso e stato indicizzazione.",
    63: "Atti amministrativi con ente, protocollo, originale, scadenze e notifiche.",
    64: "Situazione fiscale unificata con F24, dichiarazioni, quietanze e anomalie.",
}


SHEETS = [
    ("Documenti", "documents_inbox", "DOC"),
    ("Fatture ricevute", "invoices", "FAR"),
    ("Fatture emesse", "fatture_emesse", "FAE"),
    ("Fornitori", "fornitori", "FOR"),
    ("Dipendenti", "dipendenti", "DIP"),
    ("Cedolini", "cedolini", "CED"),
    ("Estratti conto", "estratti_conto", "ECD"),
    ("Movimenti bancari", "estratto_conto_movimenti", "ECM"),
    ("Prima Nota Cassa", "prima_nota_cassa", "CAS"),
    ("Prima Nota Banca", "prima_nota_banca", "BAN"),
    ("Bonifici", "bonifici_transfers", "BON"),
    ("Assegni", "assegni", "ASS"),
    ("Corrispettivi", "corrispettivi", "COR"),
    ("F24", "f24_unificato", "F24"),
    ("Quietanze F24", "quietanze_f24", "QF24"),
    ("PayPal", "paypal_transactions", "PAY"),
    ("Scadenze fornitori", "scadenziario_fornitori", "SCA"),
    ("Relazioni", "entity_relations", "REL"),
    ("Codici tributo", "tax_code_registry", "CTR"),
    ("Import PartenoPay", "partenopay_import_runs", "PPR"),
    ("Email PartenoPay", "verbali_email_archive", "PPE"),
    ("Verbali PartenoPay", "verbali_noleggio", "PPV"),
]


CORE = r"""# PROMPT MASTER — GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> Questa è l'unica specifica normativa e atomica del progetto. Codice, test e
> configurazione live verificata prevalgono soltanto quando provano uno stato
> più recente; ogni divergenza deve aggiornare questo file nello stesso commit.

## 1. Mandato e identità

Costruire e mantenere **GestionaleCloud / Ceraldi ERP**, repository canonico
`https://github.com/ceraldicontabilita/GestionaleCloud`, produzione
`https://impresasemplice.online`, branch operativo `main`. Il prodotto serve
Ceraldi Group S.r.l. e unifica documenti, fatture, fornitori, Prima Nota,
riconciliazioni, fiscalità, personale, flotta, verbali e controlli.

Non usare vecchi repository, checkout, ZIP, audit o report come autorità. Non
reintrodurre nomi storici o repository privati non canonici. Non duplicare una
funzione per conservare compatibilità non provata: una regola, un servizio, un
router e un record canonico per ciascun concetto.

## 2. Obiettivo operativo

L'utente deve vedere dati aggiornati e interconnessi, non plance tecniche. Gli
ingest e le riconciliazioni sicure avvengono automaticamente. L'intervento
manuale esiste solo per dati realmente ambigui, correzioni autorizzate e azioni
irreversibili. Ogni contatore o alert apre la lista esatta che lo compone.

Il sistema è completato solo quando il flusso funziona end-to-end in produzione:
documento originale → entità → pagamento → banca → Prima Nota → prova →
navigazione inversa. HTTP 200, pagina visibile, build o test statico da soli non
provano il funzionamento.

## 3. Principi atomici

1. Una sola fonte autorevole per ogni fatto.
2. Una sola identità canonica per entità e un solo `operation_id` per evento.
3. Una sola pipeline di ingest per canale, condivisa da manuale e scheduler.
4. Una sola regola contabile nel dominio, mai duplicata nei router o in React.
5. Una sola scrittura per operazione: upsert idempotente prima di ogni side effect.
6. Ogni mutazione è transazionale quanto possibile, auditata e ripetibile.
7. Nessun dato senza fonte, hash, timestamp, versione parser e stato.
8. Nessun record orfano, saldo hardcoded, fixture o snapshot servito come live.
9. Nessun endpoint, pagina, componente, job o variabile senza consumer e test.
10. Le associazioni automatiche richiedono prova deterministica; altrimenti proposta.

### 3.1 Motore obbligatorio delle attese

Applicare sempre `docs/REGOLA_FISSA_ATTESE.md`. Quando entra un fatto validato,
il suo owner crea immediatamente tutti gli obblighi e le attese conseguenti.
Le evidenze future non generano l'attesa che dovrebbero provare: la soddisfano
oppure la lasciano `DA_VERIFICARE`.

Stati aperti: `ATTESO`, `DA_VERIFICARE`, `IN_ELABORAZIONE`, `ERRORE`. Stati
terminali positivi: `SODDISFATTO`, `NON_APPLICABILE`, `SUPERATO`. Il processo
si chiude solo quando tutte le attese obbligatorie sono terminali positive.
Ogni attesa conserva owner, fatto sorgente, `operation_id` ed evidenze, con
navigazione bidirezionale.

## 4. Autorità e fonti

Ordine di verità:

1. originali immutabili in Google Drive e identificatori dei sistemi esterni;
2. registri strutturati nel workbook Drive/Sheets canonico;
3. codice e test del `main` canonico;
4. configurazione effettivamente attiva in Render e job scheduler;
5. `page_catalog.json`, OpenAPI e mappe generate dal codice;
6. questo PROMPT MASTER per regole, vincoli, divieti e criteri di accettazione.

Email, allegato, fattura, disposizione, ricevuta, quietanza, transazione provider,
movimento bancario e scrittura contabile sono prove distinte. Possono condividere
`operation_id`, ma non devono essere fuse o sovrascritte.

## 5. Architettura dati Drive-only

La destinazione definitiva usa **Google Drive per gli originali** e **Google
Sheets/Excel collegato a Drive per registri, progressivi, indici e relazioni**.
Il runtime usa esclusivamente Drive/Sheets. Non esistono backend alternativi,
fallback legacy o variabili di configurazione per archivi diversi.

Workbook: `Ceraldi ERP - Registro dati`.

Albero minimo sotto la radice configurata:

```text
RADICE GESTIONALECLOUD/
├── REGISTRO DATI/       workbook, schema, manifest e report di ricostruzione
├── PARTENOPAY/          email, verbali, avvisi, ricevute e indici
├── CODICI TRIBUTO/      registri e collegamenti codice → F24 → PDF
├── QUIETANZE/           quietanze e prove documentali
└── DICHIARAZIONI/       IVA, Redditi, 770, ISA e altri originali fiscali
```

Le sottocartelle di dominio esistenti possono essere indicizzate senza spostare
gli originali. Nessun job rinomina, sposta, cestina o elimina originali senza
autorizzazione esplicita. Credenziali e ID sensibili non entrano nei documenti.

Ogni foglio ha almeno:

`progressivo, canonical_id, operation_id, data, anno, tipo, importo, valuta,
descrizione, stato, documento_id, fattura_id, movimento_bancario_id, source,
source_external_id, file_hash, parser_version, created_at, updated_at,
payload_schema_version, payload_json`.

- `progressivo`: assegnato una volta per foglio, stabile, mai riciclato;
- `canonical_id`: identità deterministica e univoca dell'entità;
- `operation_id`: UUID/ULID condiviso dalle prove dello stesso evento;
- `file_hash`: SHA-256 dell'originale, mai MD5 per decisioni nuove;
- `source`: canale e identificatore esterno;
- importi: `Decimal`, valuta esplicita, mai float;
- date backend: ISO-8601 con timezone; UI italiana `gg/mm/aaaa`.

Il payload completo è JSON versionato e ricostruibile; i campi di ricerca sono
colonne tipizzate. Payload grandi sono compressi/chunked senza perdere dati.

## 6. Identità, deduplicazione e relazioni

Prima di scrivere: normalizza → calcola hash/chiave → cerca record e sorgente →
confronta payload → crea o aggiorna. Il secondo ingest della stessa fonte deve
produrre `nuovi=0` e zero nuove scritture contabili.

Una corrispondenza certa richiede importo esatto al centesimo quando pertinente,
segno e valuta, più identità/provenienza/riferimento compatibile. L'importo da
solo non è mai prova. Più candidati significa `proposed`: mostra `Scegli
fattura`, `Scegli driver`, `Scegli verbale` o equivalente, con motivazione.

Il registro relazioni conserva `relation_id`, `operation_id`, entità sorgente e
destinazione, tipo relazione, regola, confidenza, stato, creatore/validatore e
timestamp. Navigazione obbligatoriamente bidirezionale.

## 7. Gmail e posta elettronica

Gmail/IMAP acquisisce F24, quietanze, cedolini, verbali, ricevute e altri
documenti autorizzati. Le fatture elettroniche italiane provengono dal canale
Drive/SDI; una fattura italiana per email è un'anomalia da conservare, non una
seconda fonte canonica.

Regole Gmail:

- ricerca esaustiva con `in:anywhere`, incluse etichette, archivio, spam/cestino
  solo in lettura quando richiesto dal mandato;
- paginazione fino a esaurimento, mai solo la prima pagina;
- normalizzazione mittenti, alias, PEC e wrapper di consegna;
- conservazione di Gmail message ID, thread ID, internal date, RFC Message-ID,
  mittente/destinatari, oggetto, label, query, raw EML quando autorizzato,
  allegati, MIME type, dimensione e SHA-256;
- deduplica fra Gmail, Drive e upload con provenienze multiple conservate;
- fuso scheduler `Europe/Rome`; watermark e lock distribuito;
- job giornalieri idempotenti con conteggi letti/nuovi/aggiornati/invariati/
  ambigui/errori e ultimo cursore;
- i mittenti attendibili sono configurati e auditati, mai dedotti per sempre da
  un solo messaggio;
- non marcare letto, non spostare, non etichettare, non cancellare e non
  rispondere automaticamente salvo mandato specifico;
- errori di parsing conservano email e allegato e generano una coda visibile.

PartenoPay: conserva email, verbale, avviso, ricevuta PagoPA/PayPal e movimento
banca come evidenze diverse. Matching driver = targa normalizzata + data/ora
infrazione + storico assegnazioni. Intestazione alla società non identifica il
driver. Job giornaliero, alert entro cinque giorni e nessun pagamento automatico.

## 8. Drive e documenti

Ogni Drive file conserva file ID, parent ID/percorso osservato, nome, MIME,
dimensione, modifiedTime, MD5 fornito da Drive se presente, SHA-256 calcolato,
permessi osservabili, webViewLink e tutte le occorrenze duplicate. L'hash uguale
non autorizza la perdita di provenienza.

Pipeline unica: acquisisci senza distruggere → inventaria → valida MIME/ZIP →
calcola hash → classifica → estrae → valida campi → upsert → collega → verifica.
Un upload reale non può terminare “analizzato senza salvare”. Gli ZIP sono
protetti da traversal, bomb, estensioni vietate e limiti di dimensione.

Pulizia Drive: solo copie esatte, hash forte/MD5 Drive coerente, permesso
`canTrash`, anteprima completa e autorizzazione. Usare Cestino, mai eliminazione
permanente. Nessuna pulizia è completa senza verifica owner-side e stato finale.

## 9. Fatture e fornitori

Fattura unica per identità fiscale emittente, numero normalizzato, data,
tipo/SDI e hash. PDF/XML e metadati restano collegati. Lo stato pagamento deriva
da prove e allocazioni; pagamenti parziali e misti hanno righe esplicite.

Spostare una fattura fra Cassa e Banca modifica metodo/relazioni e scritture con
lo stesso ID: non crea una seconda fattura. Il fornitore è univoco per P.IVA/CF
normalizzato; merge conserva alias, IBAN, documenti e audit.

Regole SDD configurabili associano descrizioni come FASTWEB o WORLDPAY a un
fornitore, ma la regola produce automaticamente un pagamento solo con identità,
periodo e importo compatibili. Il dubbio mostra candidati.

## 10. Prima Nota, Cassa e Banca

Motore unico `scritture_contabili`: nessun router o import scrive direttamente
scritture parallele. Ogni operazione genera movimenti bilanciati, idempotenti e
collegati alla fonte.

La UI raggruppa tutte le operazioni in card giornaliere con numero, totale e
saldo progressivo verificabile. Cassa, Banca, SumUp e Soci sono sezioni dello
stesso modello, non database indipendenti.

Versamento contanti: uscita Cassa + entrata attesa Banca con stesso
`operation_id`; la riga estratto conto riconcilia l'attesa. Un versamento
manuale in Cassa crea subito l'entrata attesa in Banca. Nessun doppio ricavo.

L'estratto conto crea una riga bancaria canonica per riferimento esterno o
fingerprint data/valuta/importo/causale/numero progressivo. Reimportare lo stesso
estratto non duplica. Prima Nota Banca non è una copia cieca dell'estratto:
registra solo eventi con causale contabile nota o categorie bancarie ammesse.

Assegni con importo ricorrente non sono duplicati se numero/data differiscono.
Bonifici conservano CRO/TRN, ordinante, beneficiario, descrizione e periodo.
Finanziamenti soci richiedono identità movimento, non il solo importo.

## 11. Corrispettivi, POS, SumUp e Numia

Il ricavo nasce dal corrispettivo RT. Vendita POS, chiusura terminale, credito
gestore, commissione e accredito bancario sono fatti distinti.

Per ogni giorno: corrispettivo → quota contanti in Cassa e quota POS come
credito gestore; payout → chiusura del credito; commissione separata. Il giorno
di vendita non viene sostituito dalla data di accredito. SumUp e Numia restano
circuiti separati. Giorni mancanti, importi discordanti e payout multi-giorno
generano liste esplicite.

Le fonti owner sono distinte: SumUp corrente arriva automaticamente dall'API;
Numia corrente viene inserito manualmente ogni sera dalla chiusura dei
terminali; Numia storico viene ricostruito dagli export operativi CSV/XLSX su
Drive, deduplicati per ID transazione e accorpati per giorno vendita. Ciascun
totale giornaliero crea subito il credito/accredito atteso del proprio gestore.
L'estratto conto bancario non crea mai il fatto POS: raggruppa `NUMIA-AMEX`,
`NUMIA-INTER`, `NUMIA-BNCMT`
e `NUMIA-PGBNT` per il giorno `DEL gg/mm/aa`, somma al centesimo e soddisfa
l'attesa esistente. Senza un'unica attesa resta `DA_VERIFICARE`: la banca non
può creare retroattivamente la chiusura POS.

## 12. PayPal, PagoPA, bonifici e assegni

PayPal collega transaction ID, controparte, email, valuta, importo, data,
fattura, addebito/accredito banca e Prima Nota tramite `operation_id`. La logica
vale per tutti i movimenti, non per singoli esempi. Conversioni valuta e fee
sono righe distinte.

PagoPA collega IUV, ente, avviso, ricevuta, verbale/F24 quando pertinente e
movimento bancario. Ricevuta provider e prova bancaria hanno stati distinti.

## 13. F24, tributi e dichiarazioni

F24 PDF, delega, righe tributo, credito, quietanza e movimento bancario sono
entità separate. Indicizzazione bidirezionale: codice tributo → periodo → F24 →
PDF → quietanza → banca; PDF → tutte le righe. Filtri per anno, periodo, codice,
sezione, stato quietanza e riconciliazione.

`pagato` richiede evidenza coerente. In assenza della prova documentale usare
`attesa quietanza`; in assenza del movimento usare uno stato banca distinto.
Non usare `attesa fattura` per verbali o pagamenti che non generano fattura.

Dichiarazioni IVA, Redditi, 770 e ISA restano originali Drive collegati a
periodi, F24 e indici; non inferire valori fiscali mancanti.

## 14. Personale, cedolini e ritenute

Cedolino, dipendente, periodo, bonifico, acconto, trattenuta e Prima Nota sono
collegati. Il periodo selezionato è persistente. Bonifico prima del 25 suggerisce
il mese precedente; dal 25 può riferirsi al mese corrente anche se il cedolino
arriverà a fine mese. Nome/CF/IBAN e causale confermano; importo diverso è
possibile per acconti/trattenute e richiede allocazione.

## 15. Noleggio, veicoli, driver e verbali

Le fatture noleggiatore alimentano automaticamente targa, fornitore, marca,
modello, contratto, canoni e periodo. Le schede incomplete non compaiono nel
flusso normale: vanno in coda di qualità. Le assegnazioni driver hanno intervallo
temporale; il driver del verbale è quello attivo alla data/ora del fatto.

L'importo del verbale viene dal PDF/avviso e deve superare controlli OCR; mai
derivarlo dal numero. Il PDF verbale è sempre associabile manualmente. Stati:
`documento salvato`, `da verificare`, `attesa pagamento`, `attesa quietanza`,
`pagato documentale`, `riconciliato banca`.

## 16. Contabilità, bilancio e controlli

Piano conti CEE ufficiale, registrazioni Dare/Avere bilanciate, libro giornale
progressivo, bilancio derivato, IVA per periodo, cespiti, mutui, budget e
chiusura. Ogni totale ha formula e drill-down. Simulazioni non scrivono sul
consuntivo. Chiusura esercizio richiede checklist, anteprima, conferma forte,
audit e rollback.

### 16.1 Tracciabilità alimentare e HACCP

La tracciabilità alimentare NON è un modulo nativo del gestionale: dal
03/09/2026 (ordine del titolare, regola «un solo sistema per funzione»)
l'area `/tracciabilita`, il router `/api/haccp` e i fogli `haccp_*` sono
stati rimossi. Ricezioni, lotti, registri, ricette, produzioni e
attrezzature vivono nell'app Lotti originale montata pari pari a
`/lotti` (login e archivio propri). Il gestionale le fornisce soltanto
il feed fatture `/api/integrations/lotti/*`; fatture, fornitori, prodotti,
corrispettivi e ordini restano le entità canoniche di GestionaleCloud.
Allo stesso modo la pagina «Cedolini paga» (`/salari`) è stata sostituita
dall'app HR (AppDipendenti) montata a `/hr`: nel gestionale restano solo
l'ingestione cedolini, la Prima Nota salari e la riconciliazione stipendi.

## 17. UX e accessibilità

Navigazione per moduli, anno globale coerente, layout semplice. Stati loading,
vuoto, dati, parziale, errore e retry per ogni pagina. Filtri persistono in URL
quando condivisibili. Tabelle responsive, importi allineati, date italiane,
focus visibile, tastiera, contrasto e semantic HTML.

Modali sopra ogni overlay, focus trap, `Esc`, pulsante Chiudi e click esterno
solo se non perde dati. Aprire “Vedi fattura” non deve lasciare la finestra sotto
un'altra. Azioni distruttive indicano oggetto, impatto, recuperabilità e audit.

## 18. Alert, automazioni e agenti

Ogni alert contiene query riproducibile, elenco record, motivazione, severità,
fonte e azione. I falsi positivi si correggono nella regola. Le automazioni
hanno lock distribuito, idempotency key, watermark, retry limitato, dead-letter,
metriche e ultimo esito. Nessun job parte in ogni worker web.

Agenti AI operano in sola lettura o proposta per default. Nessuna associazione
ambigua, pagamento, cancellazione, movimento di originali o modifica esterna è
eseguita senza autorizzazione esplicita e controllo deterministico.

## 19. Sicurezza e privacy

RBAC per pagina/endpoint, MFA admin, password hash forte, sessioni scadenti,
CSRF dove applicabile, CORS esplicito, rate limit, validazione input/upload,
protezione ZIP, query parametrizzate, log strutturati senza segreti o dati
integrali non necessari. Segreti solo in secret store Render/locale non
versionato; mai `.env`, token, password, PIN, service-account JSON o URL con
credenziali nel repository, nei fogli o nei log.

Ogni mutazione registra attore, correlation ID, sorgente, prima/dopo, timestamp
UTC e risultato. L'utente può accedere solo ai dati del ruolo autorizzato.

## 20. Divieti assoluti

- pagamenti automatici;
- associazioni definitive ambigue;
- cancellazione o spostamento automatico di email/documenti originali;
- eliminazione permanente Drive; usare Cestino solo con autorizzazione;
- matching per solo importo;
- float per denaro;
- dati demo/hardcoded/fallback storico in produzione;
- route, endpoint, job, pagina, componente o variabile senza consumer/test;
- doppia pipeline Gmail/Drive o doppio motore Prima Nota;
- scritture contabili dirette fuori dal motore unico;
- segreti nel codice, documentazione, log o workbook;
- dichiarare collaudato con solo HTTP 200, build o test statico;
- eliminare il backend transitorio prima di ricostruzione e cutover verificati.

## 21. API, errori e compatibilità

FastAPI modulare, schemi request/response tipizzati, errori con `code`, `message`,
`details`, `correlation_id`, paginazione e limiti. Autorizzazione nel backend.
L'OpenAPI generato dal codice è il contratto tecnico. Gli endpoint senza FE,
scheduler, integrazione, MCP o test restano in quarantena e non si ricreano.

Alias legacy: misurare gli accessi, reindirizzare al canonico senza duplicare
logica e rimuovere dopo zero consumer. Nessuna risposta finta per conservare un
endpoint morto.

## 22. Configurazione e variabili

Tutte le variabili riconosciute dal codice sono elencate nell'appendice generata.
I valori sensibili non sono mai stampati. Ogni variabile nuova richiede
descrizione, tipo, default sicuro,
ambiente, proprietario, rotazione se segreta, test startup e rimozione quando
non ha più consumer.

## 23. Test e gate

Per ogni pagina: accesso, deep-link/refresh, loading/vuoto/dati/parziale/errore,
filtri, importi/date, modali, responsive, relazioni, alert, idempotenza e audit.

Per ogni ingest: prima esecuzione, seconda identica, duplicato cross-canale,
formato invalido, interruzione, retry e concorrenza. Per ogni riconciliazione:
caso certo, nessun candidato, più candidati, parziale, storno e navigazione
inversa. Test monetari al centesimo.

Gate release: lint, unit, integration, contract, build, E2E isolato, scansione
segreti, zero riferimenti obsoleti, migrazioni idempotenti, backup/rollback,
CI verde, commit servito in `/api/health`, controllo live di dati e job.

Gate Drive-only: tutti i fogli presenti e versionati; conteggi, digest, somme e
relazioni equivalenti; scrittura/lettura riuscite; ricostruzione completa da
Drive in ambiente isolato; rollback provato; nessun backend alternativo attivo.

## 24. Procedura di sviluppo e pubblicazione

Sincronizza `origin/main`; lavora in branch/worktree pulito; preserva modifiche
locali altrui; modifica una funzione atomica; aggiungi solo file pertinenti;
esegui test mirati e suite; controlla diff/segreti; commit descrittivo; push/PR;
CI; merge autorizzato; deploy; verifica live e rollback se i gate falliscono.

## 25. Criterio finale “nessun dato morto”

Un dato esiste solo se ha fonte, identità, schema, consumer, stato e percorso di
ricostruzione. Un file/codice esiste solo se importato o invocato, coperto da
test e necessario a una route/job/integratore attivo. Audit datati e vecchi
porting non restano nel repository: Git conserva la storia. Le mappe generate
si rigenerano dal codice e non si correggono a mano.
"""


def parse_endpoints() -> list[dict[str, str]]:
    rows = {}
    source = (ROOT / "memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md").read_text(encoding="utf-8")
    for raw in source.splitlines():
        if not raw.startswith("| `"):
            continue
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if len(cells) < 9 or " " not in cells[0]:
            continue
        method, path = cells[0].strip("`").split(" ", 1)
        row = {"method": method, "path": path, "router": cells[1], "decision": cells[7], "reason": cells[8]}
        key = (method, path)
        if key in rows and rows[key] != row:
            raise RuntimeError(f"Endpoint in conflitto: {key}")
        rows[key] = row
    return list(rows.values())


def settings_variables() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    path = ROOT / "app/config.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Settings":
            continue
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id.isupper():
                name = item.target.id
                result[name] = {
                    "type": ast.unparse(item.annotation),
                    "default": ast.unparse(item.value) if item.value is not None else "required",
                    "source": "app/config.py",
                }
    return result


def direct_environment_names() -> dict[str, set[str]]:
    patterns = [
        re.compile(r"(?:os\.)?getenv\([\"']([A-Z][A-Z0-9_]+)"),
        re.compile(r"os\.environ\.get\([\"']([A-Z][A-Z0-9_]+)"),
        re.compile(r"os\.environ\[[\"']([A-Z][A-Z0-9_]+)"),
        re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"),
        re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]+)"),
    ]
    found: dict[str, set[str]] = defaultdict(set)
    allowed = {".py", ".js", ".jsx", ".cjs", ".mjs", ".yaml", ".yml"}
    excluded = {".git", "dist", "node_modules", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in allowed or any(part in excluded for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for name in pattern.findall(text):
                found[name].add(path.relative_to(ROOT).as_posix())
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    for name in re.findall(r"^\s*- key:\s*([A-Z][A-Z0-9_]+)\s*$", render, re.MULTILINE):
        found[name].add("render.yaml")
    return found


def variable_group(name: str) -> str:
    if any(token in name for token in ("DR_SOURCE", "DR_RESTORE")):
        return "transitorie-vietate-nel-target"
    if name.startswith(("GOOGLE_DRIVE", "DRIVE_", "GOOGLE_SHEETS", "GOOGLE_SERVICE")):
        return "drive-sheets"
    if name.startswith(("GMAIL", "EMAIL", "IMAP", "SMTP", "FROM_EMAIL")):
        return "gmail-email"
    if name.startswith("GESTIONALE_MCP"):
        return "mcp"
    if name.startswith(("PAYPAL", "SUMUP", "OPENAPI", "TELEGRAM", "WHATSAPP")):
        return "integrazioni"
    if name.startswith(("OPENAI", "ANTHROPIC", "GEMINI", "GOOGLE_API")):
        return "ai"
    if name.startswith(("AZIENDA", "FISCAL_", "ADER_")):
        return "azienda-fiscale"
    if name.startswith(("ENABLE_", "RUN_", "SCHEDULER", "VERBALI_", "POS_", "NOLEGGIO_")):
        return "feature-job"
    if name.startswith(("ADMIN", "PIN_", "SECRET", "CORS", "ALLOW", "ALLOWED", "ACCESS_TOKEN")):
        return "sicurezza"
    if name.startswith(("SMOKE", "E2E_", "BASE_URL", "AUTH_TOKEN", "CHROMIUM", "OUT_DIR", "VERBALE_TEST")):
        return "test-tooling"
    return "app-runtime"


def sensitive(name: str) -> str:
    return "segreta" if any(token in name for token in ("SECRET", "PASSWORD", "TOKEN", "API_KEY", "PRIVATE", "PIN")) else "configurazione"


def render_pages() -> str:
    catalog = __import__("json").loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))
    pages = catalog["pages"]
    if len(pages) != len(PAGE_PURPOSES) or set(PAGE_PURPOSES) != set(range(1, len(pages) + 1)):
        raise RuntimeError("Catalogo o contratti pagina incompleti")
    lines = [f"## Appendice A — Tutte le {len(pages)} pagine", ""]
    for page in sorted(pages, key=lambda value: value["id"]):
        lines.append(
            f"{page['id']}. **{page['label']}** — `{page['path']}` — accesso `{page['access']}` — "
            f"modulo `{page['module']}` — {PAGE_PURPOSES[page['id']]} "
            f"Fonte UI: `{page['component']}`; mappa: `{page['documentation_file']}`."
        )
    return "\n".join(lines)


def render_sheets() -> str:
    lines = ["## Appendice B — Fogli e progressivi Drive/Sheets", "", "| Foglio | Nome logico | Prefisso |", "|---|---|---|"]
    lines.extend(f"| {title} | `{logical}` | `{prefix}` |" for title, logical, prefix in SHEETS)
    return "\n".join(lines)


def render_variables() -> str:
    configured = settings_variables()
    direct = direct_environment_names()
    names = sorted(set(configured) | set(direct))
    lines = [
        "## Appendice C — Tutte le variabili rilevate", "",
        "> Inventario dei nomi, non dei valori. I valori sensibili devono restare nel secret store.", "",
        "| Variabile | Gruppo | Sensibilità | Tipo/default dichiarato | Sorgenti |", "|---|---|---|---|---|",
    ]
    for name in names:
        item = configured.get(name, {})
        type_default = "non dichiarato in Settings"
        if item:
            if sensitive(name) == "segreta":
                type_default = f"`{item['type']}` / valore non riportato"
            else:
                default = item["default"].replace("|", "\\|")
                type_default = f"`{item['type']}` / `{default}`"
        sources = set(direct.get(name, set()))
        if item:
            sources.add(item["source"])
        source_text = ", ".join(f"`{source}`" for source in sorted(sources))
        lines.append(f"| `{name}` | {variable_group(name)} | {sensitive(name)} | {type_default} | {source_text} |")
    lines.extend([
        "", "Regole: alias duplicati Drive/email vanno migrati verso un nome canonico e poi rimossi; "
        "una variabile senza consumer non va mantenuta; tutte le variabili `transitorie-vietate-nel-target` "
        "sono escluse dalla ricostruzione Drive-only.",
    ])
    return "\n".join(lines)


def render_drive_folders() -> str:
    configured = settings_variables()
    direct = direct_environment_names()
    names = sorted(
        name
        for name in set(configured) | set(direct)
        if ("DRIVE" in name or "GDRIVE" in name) and "FOLDER" in name
    )
    lines = [
        "## Appendice C.1 — Tutte le cartelle Drive configurabili",
        "",
        "Questa tabella è l'inventario canonico degli alias di cartella. Gli ID sono configurazione, non identità di dominio: ogni alias deve puntare a una sola cartella e ogni cartella deve avere manifest, provenienza e permessi verificati.",
        "",
        "| Variabile cartella | Default dichiarato | Sorgenti/consumer |",
        "|---|---|---|",
    ]
    for name in names:
        item = configured.get(name, {})
        default = item.get("default", "non dichiarato").replace("|", "\\|")
        sources = set(direct.get(name, set()))
        if item:
            sources.add(item["source"])
        source_text = ", ".join(f"`{source}`" for source in sorted(sources))
        lines.append(f"| `{name}` | `{default}` | {source_text} |")
    lines.extend(
        [
            "",
            "Gli alias senza valore vanno configurati nel secret/config store di Render. Non creare cartelle parallele per aggirare un alias mancante; risolvere e documentare la cartella canonica.",
        ]
    )
    return "\n".join(lines)


def render_endpoints() -> str:
    endpoints = parse_endpoints()
    active = [row for row in endpoints if row["decision"] == "tenere"]
    quarantine = [row for row in endpoints if row["decision"] != "tenere"]
    counts = Counter(row["decision"] for row in endpoints)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in endpoints:
        grouped[row["router"]].append(row)
    lines = [
        "## Appendice D — Tutti i router e tutti gli endpoint", "",
        f"Route table sorgente: **{len(endpoints)}**; attivi da ricreare: **{len(active)}**; "
        f"quarantena: **{len(quarantine)}** (`verificare` {counts['verificare']}, `admin-only` {counts['admin-only']}).", "",
        "`attivo` significa da ricreare con contratto e test; `quarantena` significa non esporre nel nuovo runtime finché consumer, autorizzazione e test non sono provati. L'elenco è completo e include entrambe le categorie.", "",
    ]
    for router in sorted(grouped):
        rows = sorted(grouped[router], key=lambda row: (row["path"], row["method"]))
        lines.extend([f"### Router `{router}` ({len(rows)})", ""])
        for row in rows:
            state = "attivo" if row["decision"] == "tenere" else f"quarantena: {row['decision']}"
            lines.append(f"- **{state}** — `{row['method']} {row['path']}` — {row['reason']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    sections = [
        CORE.strip(),
        render_pages(),
        render_sheets(),
        render_variables(),
        render_drive_folders(),
        render_endpoints(),
        "## Appendice E — Provenienza della specifica\n\n"
        f"Rigenerato il {TODAY} dal contenuto versionato con `python scripts/genera_prompt_master.py`. "
        "Fonti: codice, `page_catalog.json`, `app/config.py`, `render.yaml`, mappe endpoint generate e test correnti. "
        "Nessun valore di credenziale è incluso.",
    ]
    output = "\n\n".join(section.rstrip() for section in sections) + "\n"
    (ROOT / "PROMPT_MASTER.md").write_text(output, encoding="utf-8", newline="\n")
    print(
        f"PROMPT_MASTER.md: {len(output.splitlines())} righe; "
        f"{len(PAGE_PURPOSES)} pagine; {len(parse_endpoints())} endpoint sorgente; "
        f"{len(settings_variables() | {name: {} for name in direct_environment_names()})} variabili"
    )


if __name__ == "__main__":
    main()
