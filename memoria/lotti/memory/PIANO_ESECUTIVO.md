# PIANO ESECUTIVO — cosa resta da fare, in che ordine, come si collauda
Aggiornato il 25/07/2026. Ricostruito rileggendo TUTTI i documenti di audit
(AUDIT_FLUSSI, AUDIT_QUANTITA_UNITA, AUDIT_SICUREZZA, AUDIT_NAVIGAZIONE,
AUDIT_VISIVO_MOBILE_TABLET, AUDIT_IMPORT_DATABASE, AUDIT_REGISTRI_STAMPE,
AUDIT_SCHEDULER_TEMPERATURE) e PIANO_REFACTOR.

Regola di questo piano: **niente si dichiara fatto senza un collaudo**. Per
ogni voce è scritto CHI collauda e COME. I collaudi che il banco di prova non
può fare (stampa vera, tablet reale, dati veri) sono marcati «serve Enzo».

---

## GIÀ CHIUSO (per non ridiscuterlo)

Ciclo operativo: richiamo che blocca i lotti, dedup fatture senza P.IVA,
doppio tocco che non duplica, eliminazione fattura sicura, stop alle
conversioni tra unità incompatibili. Quantità: bevande a confezione nel food
cost, centilitri, cartoni non più trattati come grammi, cascata magazzino
multi-lotto. Registri: anomalie di temperatura non riscrivibili cambiando le
soglie, righe mai saltate, "N/D" al posto delle celle vuote, registro ASL non
più troncato, lotti archiviati e mai cancellati. Accessi: dipendenti solo
sulle card del tablet, gestionale col PIN del titolare, otto comandi che
riscrivono registri storici ora riservati all'amministratore. Ricette:
proposta senza duplicati, compilazione di massa, dosi portate a 1 kg, ricetta
bloccata col PIN, card "Dose di oggi".

---

## TRANCHE 1 — Buchi nei registri — **CHIUSA 25/07/2026**

**Perché**: oggi, se il server resta spento un giorno, quel giorno sparisce
dai registri senza dire perché; e nella sanificazione una casella vuota può
voler dire "non fatto" oppure "nessuno l'ha registrato" — davanti all'ASL
sono due cose molto diverse.

1. **Giorni non rilevati marcati a database.** Quando lo scheduler riparte
   dopo un fermo, i giorni passati senza lettura vengono scritti come "non
   rilevato" con il motivo, invece di restare buchi.
   *(AUDIT_SCHEDULER_TEMPERATURE §2.3 — oggi la stampa è onesta, il dato no)*
2. **Sanificazione: distinguere "non fatto" da "non registrato"** nello schema
   e nell'export. *(AUDIT_REGISTRI_STAMPE §2)*
3. **Tracciabilità fatture-ricette: avviso "mostrate 500 righe di N"** nella
   stampa HTML (il CSV è già completo). *(AUDIT_REGISTRI_STAMPE §5)*

**FATTO**: nuovo motore `marca_giorni_non_rilevati` in `haccp_auto.py`,
lanciato dal job delle 07:00 (e quindi anche dal recupero al riavvio). Regole
di prudenza: non tocca mai un giorno che ha già un valore, non marca OGGI (la
giornata è aperta), non marca prima della prima rilevazione mai fatta su
quell'apparecchio, e non inventa nessuna temperatura. In sanificazione il
giorno passato senza registrazioni diventa "N/D", che il report NON conta più
come sanificazione eseguita (prima qualunque valore non vuoto contava come
fatta). La stampa scrive il motivo nel tooltip; il registro tracciabilità
dichiara "Mostrate le prime 500 righe di N".

**Collaudo fatto sul banco**: scheda con letture a −6 e −1 giorno e quattro
giorni vuoti in mezzo → 12 marcature sui frigoriferi, 8 sui congelatori, 1
scheda sanificazione; secondo giro a zero (idempotente); report HACCP con 20
celle "N/D" che dichiarano il motivo; export sanificazione con 12 "N/D" e 6
"X" e la legenda; pagina Sanificazione che mostra la differenza a colpo
d'occhio. 11 test automatici nuovi (`tests/test_registri_buchi.py`).
**Serve Enzo**: stampare un registro mensile vero e guardarlo.

---

## TRANCHE 2 — Sicurezza — **CHIUSA 25/07/2026**

**Perché**: restano comandi che cambiano listini e cataloghi in blocco senza
chiedere chi sei.

1. ~~Import e sincronizzazioni massive sotto permesso admin~~ **FATTO**:
   nove comandi passati sotto il PIN del titolare — Acquaviva (import listino
   2026, import listino PDF, sincronizza prezzi, import Alpha), listino da
   fatture, sconti merce (importa e valorizza), sincronizzazione Drive
   (manuale e riprova errori). Ognuno riscriveva cataloghi o listini interi
   senza chiedere chi fosse.
2. ~~Eliminazione di un singolo lotto riservata al titolare~~ **FATTO
   25/07/2026** — Enzo: «il dipendente deve solo produrre e vedere le ricette,
   tutto il resto lo guardo io e lo utilizzo io: metti tutto sotto PIN».
   `DELETE /lotti/{id}` e `DELETE /lotti-fornitori/{id}` sotto require_admin.
   Sul tablet, Magazzino / Lavagna / Ordini chiedono il PIN da amministratore
   (lucchetto «Solo titolare»); ai dipendenti restano i reparti di produzione,
   Produzioni al banco, Dose di oggi e la nuova scheda ricetta in sola lettura.
3. ~~Silenziamento degli avvisi del Supervisore~~ **FATTO**: nascondere un
   avviso è una decisione del titolare (i critici restano non silenziabili
   per chiunque).

**Collaudo fatto**: il test `test_endpoint_distruttivi_dichiarano_require_admin`
elenca i comandi UNO PER UNO (se ne aggiungo uno per sbaglio, il test lo dice);
sul banco, senza accesso, `listino/sync-da-fatture` e
`sconti-merce/importa-da-fatture` rispondono 401. Nessuno di questi comandi è
raggiungibile dalle card del tablet, quindi i dipendenti non perdono niente.

---

## TRANCHE 3 — Le cose che mi hai già segnalato e restano da decidere

Non le tocco finché non mi dici come le vuoi. Ognuna è mezz'ora di lavoro.

1. ~~"Genera Nuovo Lotto" nella pagina Tracciabilità è irraggiungibile~~
   **TOLTO 25/07/2026** — risposta di Enzo: «a me il lotto si genera quando
   produco una ricetta, che senso ha generare un lotto così?». Giusto: quel
   modale creava un lotto senza provenienza, senza scarico degli ingredienti.
   Rimossi finestra, stato e la funzione `handleGeneraLotto`. Il lotto nasce
   SOLO da «Registra produzione» (tablet).
2. ~~"Registri HACCP del mese" nel gemello digitale~~ **TOLTO 25/07/2026**
   (Enzo: sì). Alla domanda "a cosa serve realmente": quella pagina è il
   CRUSCOTTO di conformità di tutta l'attività — registrazioni di oggi
   (temperature positive/negative, sanificazione) e del mese (cottura, olio),
   lotti attivi, anomalie e reclami aperti, avviso rosso sui libretti sanitari
   scaduti, stampa del registro per l'ASL. Non riguarda il singolo lotto:
   resta nel menu HACCP, il collegamento dentro la scheda del lotto è sparito.
3. ~~Recall vero dal gemello digitale~~ **FATTO 25/07/2026**: gli ingredienti
   sono bottoni, si tocca "Farina 00" e si aprono i lotti prodotti con quella.
4. ~~Bottone "Segnala guasto" accanto a ogni frigorifero~~ **FATTO
   25/07/2026**: presente sotto ogni colonna in Temperature positive e
   negative; apre l'anomalia con priorità alta e porta subito ad Anomalie per
   lo spostamento dei lotti.
5. ~~Voce di menu "Frigoriferi e congelatori"~~ **FATTO 25/07/2026**: menu
   Altro → Amministrazione → «Frigoriferi e congelatori». Elenco unico dei due
   gruppi: si corregge il nome sul posto (il tasto Salva compare solo dopo che
   hai davvero cambiato il testo), si aggiunge un apparecchio, si toglie quello
   dismesso, si segnala il guasto. Riservata all'amministratore anche lato
   server: rinominare riscrive il nome su tutti i controlli già registrati.
6. ~~Rinominare "Cella Fresca Nord" in "Cella 1"~~ — **lo fa Enzo**, ora dalla
   nuova pagina «Frigoriferi e congelatori» (prima serviva cliccare
   sull'intestazione della colonna in Temperature).

**Collaudo**: per ognuna, prova sul banco + **serve Enzo** dal telefono.

---

## TRANCHE 4 — Prezzi e pesi che ancora si basano su stime

**Perché**: alcuni costi si appoggiano a valori inventati dal sistema quando
manca il dato vero. Non sono errori di calcolo: sono dati mancanti.

1. **Elenco dei prodotti senza peso reale**: oggi, quando un ingrediente è a
   pezzi e non sappiamo quanto pesa, il sistema usa 50 grammi. Serve la lista
   di questi prodotti, con un posto dove metti il peso vero una volta sola.
   *(AUDIT_QUANTITA_UNITA §5)*
2. **Secondo motore prezzo al chilo** nella sincronizzazione del dizionario:
   non applica il moltiplicatore del cartone (oggi tamponato da un limite di
   sicurezza). *(§6, gravità bassa)*
3. **Placeholder "TEMP"**: se il server cade nell'attimo esatto della
   produzione, un collegamento resta senza numero di lotto. Finestra di
   millisecondi, nessun caso noto, ma va chiuso generando il numero prima.
   *(AUDIT_IMPORT_DATABASE §2.1)*

**Collaudo**: io — test con dati finti su ogni caso; per il punto 1 anche una
verifica sui numeri veri del food cost prima/dopo aver inserito i pesi.
**Serve Enzo** per inserire i pesi veri dei prodotti.

---

## TRANCHE 5 — Aspetto: finire la bonifica

**Perché**: restano punti fuori dalle regole del design, e uno riguarda i
documenti che stampi e consegni.

1. **Stampe con colori vietati**: il report HACCP e il registro lotti usano
   blu e viola negli stampati. *(AUDIT_REGISTRI_STAMPE §1.5)*
2. **Emoji dentro i bottoni** del tablet e del Backoffice: vanno sostituite
   con le icone, ma richiede rimettere mano al codice dei bottoni, non è solo
   colore. *(AUDIT_VISIVO §1 dei rimandati)*
3. **Backoffice troppo lungo**: 408 prodotti tutti insieme, la pagina diventa
   lunghissima sul telefono. Serve "mostra altri" o pagine.
4. Dettagli minori: verde acceso in Fornitori, indicatore di scorrimento nella
   griglia temperature, grigi freddi residui.

**Collaudo**: io — screenshot prima/dopo alle quattro dimensioni e stampa di
prova generata sul banco. **Serve Enzo** per guardare una stampa vera.

---

## TRANCHE 6 — Pulizia del codice (solo quando le altre sono chiuse)

Ordine da PIANO_REFACTOR, sempre col metodo "fotografia prima, divisione,
confronto dopo": VenditaBancoView, ColazioneAcquaviva, OrdiniView,
CatalogoFornitore, Gelati; poi lato server food_cost.py, ricette.py e per
ultimo lotti_produzione.py (il più delicato, si tocca solo se serve).

**Collaudo**: confronto pixel e confronto dei dati inviati al server, come
già fatto per Fornitori, Lotti, Backoffice e il modale Registra lotto.
**Rischio**: basso sui primi, alto su lotti_produzione.

---

## TRANCHE 7 — "Verifica integrità gestionale" (la pagina che certifica i dati)

Proposta già scritta in AUDIT_IMPORT_DATABASE §5: una pagina che con un tocco
controlla dieci cose — fatture senza lotti, lotti senza fattura, movimenti che
puntano a lotti spariti, registri con giorni mancanti, prodotti senza peso,
ricette senza dosi, temperature fuori soglia mai giustificate — e dice cosa
non torna, con il link per andare a sistemarlo.

Costo stimato: circa una giornata. Da fare **dopo** le tranche 1, 2 e 4,
altrimenti segnalerebbe problemi che stiamo già chiudendo.

**Collaudo**: io sul banco con dati sporchi costruiti apposta; poi **serve
Enzo**: lanciarla sui dati veri e vedere se quello che segnala ha senso.

---

## COSA SERVE DA TE (in ordine di urgenza)

1. Le sei decisioni della TRANCHE 3 (bastano sei sì/no).
2. Il giro vero dal tablet dopo l'ultimo aggiornamento: card "Dose di oggi",
   ricetta bloccata, scelta del frigorifero, "Cerca questo lotto".
3. Una stampa vera del registro mensile, guardata con calma.
4. I pesi reali dei prodotti a pezzi (TRANCHE 4), quando avrai la lista.

## COME PROCEDO SE NON DICI NIENTE

TRANCHE 1 e 2 sono chiuse (25/07/2026). Vado avanti con la 4 (prezzi e pesi
stimati), poi la 5 (aspetto e stampe), poi la 6 (pulizia del codice), la 7
per ultima.

Nessuna domanda aperta: le tranche 1, 2 e 3 sono chiuse.
