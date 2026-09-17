# AUDIT END-TO-END — 25/07/2026

Audit completo richiesto da Enzo: «fai un audit completo con collaudo per
capire errori reali live end to end e debug del codice».

**Come è stato fatto** (metodo `.claude/skills/audit-codice`):
1. **Fase meccanica**, oggettiva: pyflakes su tutto il server; confronto fra
   TUTTE le chiamate del frontend (456) e TUTTE le rotte reali del server
   (678); ricerca di collection MongoDB con nomi quasi uguali; ricerca di
   chiavi duplicate nei filtri Mongo; ricerca di componenti usati in pagina
   ma mai importati (la classe di errore che manda in schermata bianca e che
   la compilazione NON segnala).
2. **Collaudo end-to-end vero**: browser Chromium che apre **una per una le 43
   pagine** dell'app, con PIN da amministratore, registrando errori
   JavaScript, chiamate al server fallite, scroll orizzontale a 390px e
   pagine rimaste vuote.
3. **Verifica delle correzioni**: stesso giro rifatto dopo i fix.

**Limite dichiarato**: da questa sandbox le richieste verso internet sono
bloccate (403 del proxy), quindi NON è stato possibile interrogare
`lotti-backend-2wwb.onrender.com` né `ceraldiapp.it`. Il collaudo è stato
fatto su `backend/run_locale_test.py`, che esegue **lo stesso identico codice
del server** su un database finto (mongomock, `Gestionale_Test`): i difetti di
codice si vedono tutti, quelli che dipendono dai dati veri no. La verifica sui
dati veri resta a Enzo dalla pagina Collaudi.

---

## DIFETTI TROVATI E CORRETTI

### 1. GRAVE — «Recupera» su un lotto dava sempre errore
`backend/routers/lotti_produzione.py:772` — `POST /lotti/{id}/recupera` usava
la variabile `operation_id` senza averla mai dichiarata fra i parametri:
`NameError` alla prima riga utile, quindi **errore 500 a ogni tocco**. Il
bottone «Recupera» nella scheda del lotto (gemello digitale) non ha mai
funzionato. Corretto dichiarando il parametro; aggiunto anche il salvataggio
del risultato, così un doppio invio della stessa richiesta restituisce la
stessa risposta invece di un generico «già eseguita».
*Collaudo*: `POST /lotti/lp-1/recupera?quantita=1` → 200, quantità residua
scalata di 1; secondo invio con lo stesso `operation_id` → nessun secondo
scarico.

### 2. MEDIO — il ricalcolo scadenze moriva invece di saltare un lotto
`lotti_produzione.py:2000` — dentro il gestore dell'errore c'erano `logger`
(in questo file si chiama `_LOG_INIT`) e `lp` (la variabile del ciclo è
`lotto`): **il codice che doveva registrare il problema andava in errore lui
stesso**, facendo fallire con 500 l'INTERO ricalcolo per colpa di un solo
lotto. Corretti entrambi i nomi.

### 3. GRAVE — schermata bianca aprendo una fattura da Fornitori
`frontend/src/components/haccp/fornitori/FattureList.jsx:124` usava `<X>` (la
crocetta di chiusura) senza importarla da lucide-react. Aprendo l'anteprima
della fattura la pagina si svuotava. **La compilazione non lo segnala**: è la
stessa classe di errore già trovata tre volte in questo progetto.

### 4. MEDIO — schermata bianca nel pannello duplicati fornitori
`DuplicatiMergePanel.jsx:151` usava `<Ban>` senza importarla: bastava un
fornitore marcato «escluso» fra i duplicati.

### 5. MEDIO — la pagina Corrispettivi si svuotava tutta per un riquadro solo
`CorrispettiviView.jsx` caricava i cinque riquadri con `Promise.all`: se UNO
solo non aveva dati (tipico la previsione, che vuole abbastanza storico) si
perdevano **tutti e cinque** e restava un messaggio rosso. Passato a
`Promise.allSettled`: ogni riquadro va per conto suo, il messaggio compare
solo se non arriva proprio niente e adesso dice cosa fare («carica i file
XML»). *Collaudo*: col database vuoto la pagina mostra comunque le festività
in arrivo, prima era una schermata rossa.

### 6. TECNICO — la pagina Acquisti non era collaudabile e dava 500 sul banco
Il filtro «prodotti non ordinabili» usava
`{"$not": {"$regex": ..., "$options": "i"}}`. Su MongoDB vero funziona, ma il
banco di prova non lo sa eseguire: `GET /prodotti-master` rispondeva **500** e
la pagina più usata dell'app (Acquisti/Ordini) restava fuori da ogni collaudo
automatico. Sostituito con `(?i)` dentro il pattern: identico per MongoDB,
funziona ovunque. 5 punti corretti fra `prodotti_master.py` e
`controllo_dati.py`. *Collaudo*: `GET /prodotti-master` → 200.

### 7. GRAVE (nel collaudo, non nell'app) — il test del FIFO era scaduto
`tests/test_e2e_flussi.py` seminava due lotti con date SCRITTE A MANO
(01/06/2026 e 01/07/2026). La regola di Enzo del 23/07/2026 dice: si parte dal
lotto più vecchio **degli ultimi 60 giorni** (uno di mesi fa non rappresenta
più il fornitore vero in etichetta), gli altri restano in riserva. Col passare
dei giorni il lotto "vecchio" è uscito dalla finestra e **il test ha
cominciato a fallire da solo, senza che nessuno toccasse il codice**: un test
con la data fissa smette di controllare quello che dice di controllare, e nel
frattempo nessuno controllava più la regola più importante dell'app.
Corretto: tutte le date dei lotti nei test sono ora relative a OGGI
(`_data_fattura(giorni_fa)`), quindi il rapporto fra i lotti resta lo stesso
per sempre. **Aggiunto anche il test che mancava**
(`test_fifo_lotto_oltre_60_giorni_va_in_riserva`): un lotto di 200 giorni fa
NON deve essere toccato finché c'è quello recente. Il comportamento dell'app
era ed è corretto: era il collaudo a essersi guastato.

---

## COSA È RISULTATO SANO

- **43 pagine su 43**: zero errori JavaScript, zero scroll orizzontale a
  390px (regola Enzo), nessuna pagina rimasta vuota.
- **456 chiamate del frontend**: nessun bottone che punta a una rotta
  inesistente (le 18 segnalate dal confronto automatico sono tutte percorsi
  costruiti a runtime — verificate una per una).
- **89 collection MongoDB**: nessun nome quasi-uguale (nessuna scrittura persa
  per un errore di battitura).
- **Nessuna chiave duplicata** nei filtri Mongo (la trappola
  `{"$ne": a, "$ne": b}`, dove il primo filtro sparisce in silenzio).
- Il resto del server: nessun nome non definito rimasto (pyflakes pulito sui
  casi gravi).

---

## SEGNALAZIONI — servono decisioni di Enzo, non le ho toccate

### A. ~~I PIN dei dipendenti sono salvati IN CHIARO nel database~~ **RISOLTO**
Enzo: «procedi per i pin, si usa la soluzione migliore». Entrando nel codice
sono venuti fuori TRE problemi, non uno:

1. **PIN in chiaro nel database** (`pin_chiaro`) accanto a quello cifrato, con
   un comando che li restituiva tutti: chi leggeva il database leggeva i PIN,
   e la cifratura non proteggeva niente.
2. **PIN scritti anche nel CODICE**, quindi finiti nella cronologia del
   repository.
3. **Il più serio: cambiare il PIN a un dipendente NON revocava il vecchio.**
   A ogni riavvio del server la lista scritta nel codice rimetteva il PIN di
   partenza dentro `pin_chiaro`, e siccome il login controllava PRIMA quello,
   il PIN vecchio tornava valido. In pratica una revoca non era una revoca.

**Come è stato risolto** (`routers/tablet_operatori.py`, `auth.py`,
`routers/ordini_fornitori.py`):
- il PIN si verifica con bcrypt come prima; per non dover provare bcrypt su
  tutti a ogni accesso c'è `pin_lookup`, un'impronta HMAC-SHA256 calcolata col
  segreto dell'applicazione (che sta nelle variabili d'ambiente di Render, NON
  nel database): serve solo a trovare la riga giusta, da sola non permette di
  risalire al PIN, e il controllo vero resta bcrypt;
- `pin_chiaro` non viene più scritto e viene **cancellato all'avvio** dai
  documenti esistenti, dopo aver calcolato l'impronta: nessuno resta fuori;
- nessun PIN è più nel codice: alla prima installazione i dipendenti nascono
  senza PIN, e l'amministratore nasce con un PIN preso da `ADMIN_PIN_INIZIALE`
  (variabile Render) o generato a caso e scritto UNA volta nel log del server;
- il riavvio non riscrive più niente: un PIN reimpostato resta reimpostato;
- al posto di «Mostra PIN» c'è **«Reimposta PIN»**: la pagina Personale mostra
  solo chi ha un PIN impostato, e permette di assegnarne uno nuovo (rifiutando
  un PIN già usato da un altro dipendente);
- la verifica «questo PIN è di un amministratore?» era ripetuta in tre file
  diversi, tutti e tre leggendo il PIN in chiaro: ora c'è un punto solo
  (`pin_amministratore_valido`).

*Collaudo*: 9 test automatici nuovi (`tests/test_pin_sicurezza.py`) + prova sul
banco: accesso amministratore e dipendente OK, PIN sbagliato respinto, la
gestione PIN non restituisce nessun PIN, PIN reimpostato → il **vecchio viene
rifiutato** e il nuovo entra, PIN duplicato rifiutato, un dipendente non può
reimpostare i PIN (403). Pagina Personale verificata a video: nessun PIN
visibile, badge «PIN impostato», bottone «Reimposta PIN», zero errori JS.

**Cosa cambia per te**: niente, i PIN restano quelli di adesso. Cambia solo che
non sono più leggibili da nessuno — se un dipendente lo dimentica, gliene
assegni uno nuovo dalla pagina Personale.
**Consiglio**: già che ci siamo, reimposta il TUO PIN da amministratore. Quello
attuale è passato dalla cronologia del repository e conviene cambiarlo.

### B. Una funzione spenta che sembra accesa
`GET /tablet-operatori/nuovi-dipendenti` restituisce sempre una lista vuota:
i bottoni «Abilita dipendente proposto» e «Ignora dipendente» nella pagina
Personale non possono mai comparire, e la collection
`tablet_operatori_ignorati` viene scritta ma non letta da nessuno.
**Da decidere**: ripristinare la proposta automatica dei dipendenti (da dove?
dai libretti sanitari? da un import?) oppure togliere i bottoni.

### C. «Nessun dato» risponde «non trovato»
Gli endpoint dei corrispettivi rispondono 404 quando la collection è vuota,
invece di rispondere «va tutto bene, ma i numeri sono a zero». Dopo la
correzione al punto 5 non fa più danno, ma è una scortesia che confonde chi
legge i log. Sistemabile quando si tocca quel file per altro.

---

## PROSSIMO PASSO PER ENZO

Sulla pagina Collaudi è stato seminato **«Audit end-to-end: le correzioni sul
campo»**. In particolare vale la pena provare, sui dati veri:
1. aprire un lotto → **Recupera** (prima dava errore sempre);
2. Fornitori → aprire una fattura → chiuderla con la ✕ (prima schermo bianco);
3. Corrispettivi in un mese senza dati: deve mostrare quello che c'è, non una
   schermata rossa.
