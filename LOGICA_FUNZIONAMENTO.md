# Ceraldi ERP — Logica di funzionamento

## 0. Accesso e sessione

- Login con **PIN** (tastierino) o email+password.
- **La sessione scade dopo 1 ora di inattività**: finché usi l'app il token
  si rinnova da solo a ogni richiesta (sessione scorrevole) e non ti
  interrompe mai; se l'app resta ferma per più di un'ora, il collegamento
  successivo richiede di nuovo il PIN. Scelta voluta: nel gestionale ci sono
  dati sensibili, niente sessioni lunghe.
- Durata regolabile con la variabile d'ambiente `ACCESS_TOKEN_EXPIRE_MINUTES`
  (default 60).

Documento di riferimento per chi usa il gestionale (amministrazione, commercialista).
Descrive come funziona davvero il sistema, letto dal codice implementato — non è una
specifica di progetto ma il comportamento reale in produzione.

Ultimo aggiornamento: 11/07/2026.

---

## 0-bis. Navigazione e pagine

- I menù (barra in alto su desktop, barra in basso + griglia su telefono)
  vengono tutti dalla **stessa configurazione unica** (`navigation.config.js`):
  una voce aggiunta lì compare ovunque, niente più menù fuori sincrono.
- Un indirizzo sbagliato mostra una **pagina "non trovata"** con l'URL
  richiesto e i link alle sezioni vere (prima riportava in silenzio alla
  Dashboard, mascherando i link rotti).
- Entrando in una pagina di un hub (Riconciliazione, Contabilità, Fatture,
  Documenti…) NON si vede più la fila dei tab di tutte le altre pagine: c'è
  solo un pulsante **«← Indietro»** (torna alla pagina precedente) e, a destra,
  un selettore discreto **«Vai a sezione»** per saltare a un'altra sezione
  dello stesso hub senza tornare al menù (serve perché alcune sezioni — es. le
  13 di Contabilità, Corrispettivi, Archivio bonifici — vivono solo dentro il
  loro hub).
- In Dashboard e Contabilità Avanzata, se un blocco non si carica per un
  errore del server compare un **avviso giallo con l'elenco dei blocchi in
  errore**: "niente dati" e "servizio in errore" non si confondono più.
- Il bottone **Auto-ripara dati** (Dashboard) chiede conferma prima di
  eseguire e riporta l'esito vero (correzioni fatte, operazioni fallite).

## 0-ter. Dashboard (la scegli tu)

- La Dashboard è comandata da DUE filtri in cima: **Anno** (globale) e
  **Mese** (con "Tutto l'anno"). Ogni numero della pagina si riferisce al
  periodo che selezioni tu — non ci sono più sezioni fisse che decidono
  cosa guardare.
- Sotto i filtri, delle **scorciatoie-domanda** ("Quanto ho incassato?",
  "Quanto ho speso?", "Quanto ho in cassa/banca?", "Quanta IVA devo?")
  portano la risposta secca del periodo in evidenza in cima.
- I dati sono in **card separate**: Fatturato/Ricavi, Acquisti/Costi,
  Utile/Margine, Cassa, Banca, IVA, Scadenze/F24, e un grafico dei 12 mesi
  (tocca una barra per filtrare le card su quel mese).
- Fonti reali per periodo: fatturato/costi/margine da controllo-gestione,
  cassa/banca da prima nota, IVA da verifica coerenza, scadenze da scadenze,
  grafico da trend mensile. Se un blocco non risponde compare l'avviso
  giallo (errore ≠ "nessun dato").

## 1. Regola decisionale (vale per tutto il sistema)

```
Caso certo     -> il sistema agisce da solo
Caso probabile -> il sistema PROPONE, decidi tu
Caso dubbio    -> resta in verifica + avviso, nessuna azione automatica
```

Il sistema non forza mai una riconciliazione o una trattenuta incerta. Tu intervieni
solo per: confermare pagamenti, correggere dati estratti, approvare trattenute,
risolvere avvisi, verificare discrepanze POS.

Altre garanzie trasversali:

- **Nessun documento viene mai importato due volte**: ogni file ha un'impronta sul
  contenuto (hash); una copia identica viene ignorata in silenzio (solo un contatore
  nei log tecnici, nessun avviso).
- **Il documento originale non viene mai modificato**: il sistema lavora su copie e
  dati estratti; l'originale resta sempre visibile con "Vedi Documento".
- **Ogni modifica manuale è tracciata** (chi, quando, valore prima/dopo — audit log).
- **Ogni errore genera un avviso risolvibile**, mai un fallimento silenzioso.

---

## 2. Flusso documenti (da dove entrano le carte)

| Documento | Fonte | Come |
|---|---|---|
| Fatture fornitori | **Solo Google Drive** (cartella dedicata) | controllo automatico ogni ora + subito a ogni riavvio |
| Corrispettivi RT | Google Drive (XML del registratore telematico) | ogni ora |
| Estratti conto | Google Drive (CSV/Excel Banco BPM) | ogni ora (oggi spento, in attesa di validazione) |
| Quietanze F24 | Google Drive (PDF) + upload manuale dalla pagina F24 | ogni ora (**attivo** dal 10/07/2026) |
| Cedolini | **Email** da mittenti attendibili + **cartella Drive cedolini paga** (PDF) | ogni ora (attivo) |
| F24 commercialista | Email da mittenti attendibili | ogni ora (oggi spento) |
| Verbali/multe | Email da mittenti attendibili | ogni ora (oggi spento) |
| Avvisi fattura in arrivo | **Email** da noreply@fatturazioneelettronica.aruba.it | ogni ora (attivo, solo dall'attivazione in avanti) |

Regola non negoziabile: **le fatture arrivano SOLO da Drive, mai da Gmail**. Se una
scansione email trova un file che sembra una fattura elettronica, non la importa:
genera un avviso di anomalia (qualcuno sta mandando fatture per il canale sbagliato).

**Avvisi Aruba ≠ fatture**: dalla notifica Aruba il sistema legge solo fornitore,
numero e importo e crea una "**fattura attesa**" (vedi §4): sa in anticipo cosa deve
arrivare, ma il documento vero resta quello XML che arriva da Drive.

Ogni documento entra in "Documenti / Import" con uno stato di lavorazione:
trovato → importato → classificato → elaborato dal parser → record gestionale creato.
Se il parser fallisce: stato di errore + avviso, il documento resta consultabile.

---

## 3. Fatture

1. Il file XML/P7M viene scaricato da Drive e ne vengono estratti: fornitore, partita
   IVA, numero, data, imponibile, IVA, totale, righe di dettaglio (descrizione,
   quantità, prezzi), data scadenza, modalità di pagamento.
2. **Se il fornitore non esiste ancora, viene creato automaticamente** (la partita IVA
   è la chiave). Il **metodo di pagamento del fornitore è una scelta tua** (Cassa /
   Banca / Misto / Non definito): l'XML può suggerire, ma non decide mai.
   Tre difese impediscono i "fornitori fantasma":
   - se il cedente coincide col cessionario della stessa fattura (autofatture,
     integrazioni reverse charge) **non** viene creato nessun fornitore: l'azienda
     stessa non può finire in anagrafica fornitori;
   - viene creato un fornitore solo con una **vera partita IVA** (11 cifre, con o
     senza prefisso paese): un codice fiscale personale non finisce mai nel campo
     P.IVA;
   - l'aggancio per nome (quando la P.IVA non è ancora in anagrafica) scatta solo a
     nome **identico**, mai a prefisso, e mai se il fornitore trovato ha già una
     P.IVA diversa: in quel caso è un'azienda diversa e se ne crea una nuova.
3. La fattura eredita il metodo di pagamento del fornitore:
   - **Cassa** → si paga col bottone "Paga in Cassa" (movimento in Prima Nota Cassa);
   - **Banca** → "Paga in Banca" (movimento in Prima Nota Banca);
   - **Misto** → la fattura va in Prima Nota **Provvisoria**: confermi tu la
     divisione tra cassa e banca, e solo dopo nascono i movimenti veri;
   - **Non definito** → avviso: serve una tua scelta.
4. **Data scadenza**: quella scritta in fattura è solo informativa. Diventa una
   scadenza operativa (pagina Scadenze, con avvisi) **solo se la fattura indica
   pagamento a mezzo agente** ("pagamento a mezzo agente", "rimessa diretta agente",
   ecc.).
5. Se in una riga della fattura compare **esattamente una targa** dei veicoli
   aziendali censiti, la fattura viene collegata automaticamente a quel veicolo
   (correggibile a mano). Zero o più targhe → nessun collegamento automatico.
6. "Segna pagata manualmente" esiste per i pagamenti avvenuti fuori sistema: la
   fattura risulta pagata ma senza un movimento di cassa/banca collegato.
7. **Centri di costo (Learning Machine)**: all'import ogni fattura viene
   classificata dal motore unico che consulta PRIMA ciò che hai insegnato
   (fornitore → centro di costo/keywords nella pagina Learning Machine) e
   solo come ripiego la tabella statica dei settori.
   I **settori operativi** sono quattro: **Bar/Caffetteria (CDC-01),
   Pasticceria (CDC-02), Gelateria (CDC-03), Rosticceria (CDC-04)**; i costi di
   supporto (Personale/Amministrazione/Marketing) e di struttura (affitto,
   utenze, manutenzione) stanno su centri dedicati (CDC-90/91/92, CDC-99).
   Il campo `classificazione_fonte` dice da dove viene la scelta
   (keywords personalizzate / keywords apprese / tabella statica).
8. **Documenti classificati (vista unica)**: i documenti classificati
   automaticamente dalle email e quelli analizzati dalla Learning Machine ora
   vivono in un'unica raccolta. I documenti arrivati da email compaiono nella
   pagina Learning Machine sotto la loro categoria (campo `fonte` =
   `email_classifier`), così hai un solo elenco reale invece di due separati.
   "Riclassifica Fatture" applica le tue configurazioni a tutte le fatture
   ancora in "Altri costi non classificati" O senza alcun centro di costo;
   "DA CLASSIFICARE" conta entrambe le condizioni, "CONFIGURATI" conta solo
   i fornitori con una configurazione reale.
   **Ribaltamento (contabilità analitica)**: i costi di supporto e struttura
   vengono ribaltati sui quattro settori **in proporzione ai ricavi** di ciascun
   settore. I ricavi per settore non sono tracciati: di default sono stimati
   (proporzionali ai costi diretti, con avviso "stima"); puoi impostare le quote
   reali con `POST /api/centri-costo/ribaltamento/quote-ricavo`.

**Pagina Fornitori (anagrafica).**
- La lista è a **pagine numerate** (1 · 2 · 3 …, 50 fornitori per pagina, barra sia
  sopra che sotto). Cambiare metodo, magazzino o modificare l'anagrafica aggiorna
  solo la riga: **non** si torna a pagina 1 e non si perde la posizione.
- Ogni riga mostra l'**anno dell'ultima fattura** (verde = fattura nell'anno
  selezionato → fornitore attuale; grigio = solo storico).
- Un fornitore può essere segnato **cessato** (dal menù ⋯ o dalla matita): sparisce
  dalla lista ma non viene eliminato — fatture e storico restano. Il chip "🚪
  Cessati (N)" accanto a Totale/Attivi li fa rivedere.
- Dal riepilogo **fatturato** si apre l'estratto fatture dell'anno, e da lì ogni
  fattura si visualizza col bottone **👁 Vedi** (visore in pagina, senza nuove
  schede).

---

## 4. Prima Nota (Cassa / Banca / Provvisoria)

I movimenti nascono di norma da un'azione precisa (corrispettivo, fattura,
riconciliazione). È però ammesso l'**inserimento manuale** in Prima Nota Cassa per i
casi non coperti da un'azione (piccola spesa contanti, versamento, finanziamento
soci): il movimento viene **marcato come "manuale"** (`inserimento_manuale=true`,
`origine="manuale"`) e registrato nell'audit log, così resta distinguibile dai
movimenti automatici. Restano comunque rifiutati i movimenti chiaramente bancari
(bonifico, POS bancario, F24…), che vanno in Prima Nota Banca.

**Cassa**
- Conferma di un corrispettivo giornaliero → l'incasso viene **diviso per natura**:
  in Prima Nota **Cassa** entra **solo la quota contanti** (categoria "Corrispettivi
  contanti"); la quota elettronica NON tocca mai la cassa. Il saldo di cassa è quindi
  il contante effettivo.
- "Paga in Cassa" su una fattura → uscita collegata alla fattura.

**Banca**
- La **quota elettronica/POS** dello stesso corrispettivo entra in Prima Nota **Banca**
  come entrata "Corrispettivi POS", **in attesa di conciliazione** con l'accredito reale
  che arriverà dal provider (il POS è in viaggio verso la banca). Non è mai un'uscita di
  cassa: è un'entrata bancaria da riscontrare.
- "Paga in Banca" su una fattura → uscita collegata alla fattura.
- Registrazione di un accredito POS in estratto conto → concilia la voce "Corrispettivi
  POS" attesa (vedi §5), non crea un movimento nuovo.

**Provvisoria**
- Solo fatture di fornitori "misto", in attesa della tua divisione cassa/banca.

**Fatture attese (avvisi email Aruba)** — nel tab Provvisori
- Quando Aruba avvisa che una fattura è stata recapitata, il sistema crea una
  "fattura attesa" con fornitore, numero e importo letti dalla mail, e il
  suggerimento cassa/banca preso dal metodo del fornitore (stesso motore di tutto
  il resto).
- **Registrazione automatica (scelta del 10-07-2026)**: se il fornitore ha metodo
  certo (Cassa o Banca), l'anticipo viene registrato **da solo** in prima nota,
  marcato "annunciata da email, XML in arrivo" (nei Provvisori compare "✓ anticipo
  (auto)"). Se il metodo è Misto o non definito, la scelta resta tua, a un tap
  (💵/🏦) dal tab Provvisori.
- Quando l'XML vero arriva (da Drive o quadratura Elaborate), il sistema **riscontra**
  l'attesa per numero+importo: il movimento anticipato viene agganciato alla
  fattura — **mai due movimenti per la stessa fattura**.
- Solleciti a due stadi: dopo **3 giorni** senza XML il sistema ripassa da solo la
  cartella Elaborate di Drive (recupero mirato: sa già cosa cercare) e, se manca
  ancora, avviso "Fattura annunciata ma XML mai arrivato"; dopo **12 giorni** (il
  termine normativo di emissione/trasmissione allo SDI della fattura immediata)
  scatta l'allarme critico "oltre termine": va sollecitato il fornitore o
  verificato il canale Drive.
- Vale solo dall'attivazione in avanti: il pregresso resta coperto dalla quadratura
  Drive settimanale.

**Saldo progressivo**: ogni movimento porta il saldo aggiornato a quel punto, in
ordine cronologico. Un movimento retrodatato ricalcola a cascata i saldi successivi.
A parità di giorno l'ordine di inserimento è garantito (la quota contanti in cassa e
la quota POS in banca nascono dallo stesso corrispettivo, in sequenza).

**Protezioni**: un doppio click su "Conferma" non può creare movimenti doppi
(la seconda richiesta viene rifiutata); ogni azione registra chi/quando (audit log).

---

## 5. Corrispettivi e coerenza POS (calendario accrediti)

Regola di fondo: **il confronto POS↔banca usa sempre il calendario di giorni
lavorativi e festivi, mai il semplice mese contabile.** Uno slittamento spiegato dal
calendario non è un'anomalia e non genera mai avvisi.

1. Inserisci corrispettivo manuale reale e POS della chiusura serale, poi Conferma.
2. Il sistema calcola la **data prevista di accredito** del POS:
   - vendita lun–ven → primo giorno lavorativo dopo il giorno successivo
     (venerdì → lunedì, se non festivo);
   - vendita sab/dom → primo lunedì (o martedì, secondo contratto POS) successivo,
     spostato avanti se festivo.
   Le festività nazionali sono popolate automaticamente per anno.
3. Il corrispettivo resta "in attesa accredito". Quando l'accredito compare in banca
   lo registri dalla pagina Riconciliazione: il sistema confronta l'importo
   accreditato col POS atteso dei giorni coperti —
   entro tolleranza → **riconciliato**; oltre → **discrepanza reale** (da verificare).
4. Avvisi automatici SOLO se il calendario non spiega la differenza:
   - accredito in ritardo (data prevista + tolleranza superate, nessun accredito);
   - discrepanza di importo banca vs atteso;
   - POS manuale ≠ POS dell'XML del registratore oltre tolleranza.

**Provider degli accrediti POS: NUMIA.** Gli accrediti del POS in banca arrivano
dal provider **NUMIA** (SumUp/Satispay non sono usati). La FASE 2 (POS reale vs
Banca) riconosce come accredito i movimenti in entrata dell'estratto conto la cui
descrizione/categoria contiene "NUMIA" (o le diciture bancarie POS generiche).
Le entrate sono identificate per **importo positivo**, non per un campo interno.
Nota (fix 12/07/2026): prima il caricatore non cercava la parola "NUMIA" e
filtrava su un campo `tipo` non sempre valorizzato, quindi non agganciava gli
accrediti NUMIA e la card "Accrediti banca mancanti" mostrava un falso disavanzo
(soldi in realtà incassati e presenti in banca).

---

## 6. Riconciliazione bancaria (estratto conto ↔ prima nota banca)

**Da dove arrivano i movimenti banca**: l'estratto conto (CSV/Excel Banco BPM,
cartella Drive dedicata) viene letto riga per riga; ogni riga diventa un movimento
bancario con saldo progressivo. Ogni riga ha un'impronta propria: ricaricare lo
stesso estratto non duplica nulla.

**Il matching automatico** confronta ogni movimento banca non riconciliato con le
righe di Prima Nota Banca non riconciliate:

- **Filtri duri** (un candidato che non li passa non viene proprio considerato,
  qualunque cosa dica la descrizione):
  - stesso segno (entrata con entrata, uscita con uscita);
  - differenza importo entro **2,00 €**;
  - distanza tra le date entro **5 giorni**.
- La somiglianza del testo (descrizione/causale) serve **solo** a scegliere tra più
  candidati già validi — mai a far passare un candidato con importo o data fuori
  soglia.

**Classificazione:**

| Esito | Condizione | Cosa fa il sistema |
|---|---|---|
| **Certo** | un solo candidato, stesso importo (±0,01 €) e stessa data | collega automaticamente le due righe (operazione atomica: o entrambe o nessuna) e registra la riconciliazione come "auto confermata" |
| **Probabile** | un solo candidato ma non esatto; oppure più candidati con un vincitore netto | crea una **proposta**: le righe restano non riconciliate finché non confermi (o rifiuti) tu |
| **Dubbio** | nessun candidato, o più candidati troppo vicini tra loro | apre un "dubbio" con l'elenco dei candidati, **mai** una scelta automatica |

Esiste anche la **riconciliazione manuale**: colleghi tu un movimento banca a una
riga di prima nota. Se nel frattempo il sistema aveva già riconciliato quella riga,
la tua richiesta viene rifiutata con un conflitto (mai una sovrascrittura muta).

Le righe già riconciliate (incluse quelle POS, che nascono già riconciliate) non
rientrano mai nei giri successivi. Un movimento va "in verifica" solo su tua azione.

Nota: le soglie (2 €, 5 giorni, ecc.) sono valori di partenza ragionevoli, mai
ancora tarati su un ciclo reale di dati — quando la banca inizierà a popolarsi
davvero andranno riviste.

---

## 7. F24 e Quietanze

Distinzione non negoziabile: **l'F24 è il documento DA pagare; la quietanza è la
prova UFFICIALE dell'avvenuto pagamento.** Sono due archivi separati che il sistema
collega — mai confusi. Per questo **non esiste** un bottone "segna F24 pagato": un
F24 risulta pagato solo quando gli viene collegata una quietanza.

- Gli F24 arrivano via email dal commercialista (mittenti attendibili — canale oggi
  spento in attesa di file reali di conferma). Le **quietanze** entrano da DUE porte
  con lo STESSO motore (parsing, dedup per impronta md5, matching automatico):
  la cartella **Google Drive dedicata** (controllo ogni ora, file spostati in
  `Elaborate`, quadratura domenicale ore 5:45 che recupera i buchi) e l'**upload
  manuale** dalla pagina F24. La stessa quietanza caricata due volte non crea
  mai doppioni.
- Un controllo giornaliero genera avvisi per F24 in scadenza (entro 7 giorni) o
  scaduti e non ancora quietanzati.
- **Matching automatico F24↔Quietanza**: prima condizione assoluta, **stesso codice
  fiscale** (senza, il candidato non esiste proprio); poi importi (±0,01 € per il
  certo, ±2,00 € per il probabile), finestra di 10 giorni sulla data, e la
  sovrapposizione dei codici tributo come spareggio. Stessa scala
  certo/probabile/dubbio della banca: il certo si applica da solo, il resto aspetta te.
  (Un pagamento può precedere la scadenza: qui il "certo" non richiede stessa data.)

**Motore tributi (specifica vincolante, 10/07/2026 — dettagli in
memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md).**
- Ogni riga F24 viene **classificata** per natura (costo / ritenuta / credito /
  sanzione / regolarizzazione / pagamento), ente (Erario, INPS, Regione, Comune,
  INAIL) e deducibilità. **Il saldo F24 non è mai automaticamente un costo**:
  ritenute IRPEF (1001…), addizionali (3802/3847/3848), crediti compensati
  (1701/6869) e sanzioni (8906) non sono costi del personale.
- **Scadenza naturale** = 16 del mese successivo al periodo; la pagina di
  analisi mostra data pagamento, giorni di ritardo e stato (nei termini /
  in ritardo / non pagato). **RC01** = regolarizzazione di un periodo
  precedente: mai imputata al mese corrente.
- **Associazione F24↔cedolini** solo con periodo, causale, posizione e
  soggetto coerenti — con motivazione leggibile (la Chat sa spiegare perché
  un F24 è stato associato o escluso). DM10 e RC01 dello stesso debito non
  vengono mai sommati due volte; se risultano **entrambi pagati** scatta
  l'alert "POSSIBILE DOPPIO PAGAMENTO" con quota capitale vs sanzioni.
- **Quietanza senza F24** (Caso 3): il modello non viene mai ricostruito;
  la quietanza resta come prova di pagamento non associata, con alert
  bloccante "F24 mancante — prego caricare il modello F24 corrispondente".
- **Quietanza AdE → scadenza completata**: quando la quietanza dell'Agenzia
  delle Entrate viene abbinata a un F24, le scadenze corrispondenti nel
  **Calendario Fiscale** (Versamento ritenute, Contributi INPS, Liquidazione
  IVA del periodo pagato) vengono segnate **completate** in automatico. Il
  mese si ricava dalla **data di pagamento** della quietanza: ritenute e INPS
  sul mese di versamento, IVA sul mese di competenza (versamento il 16 del
  mese dopo). Sono esclusi i ravvedimenti e **RC01** (regolarizzazione di
  periodo precedente, mai imputata al mese corrente). La marcatura è
  tracciabile (salva quietanza e F24 di origine) e non tocca le scadenze già
  completate a mano; un problema qui non blocca mai l'import della quietanza.
- API: `/api/f24-analisi/{id}`, `/api/f24-analisi/{id}/associazione`,
  `/api/f24-analisi/doppi-pagamenti`. La Chat usa gli strumenti
  `spiega_f24` e `doppi_pagamenti_f24`.
- Motore fiscale separato: costo del personale (mai risommare netto/IRPEF/
  addizionali/IVS dipendente), IRES con aliquota versionata per anno, IRAP
  autonoma dal valore della produzione con deduzioni per tipologia di
  personale (mai sottratto l'intero F24).

---

## 8. Gestione IVA (attribuzione per competenza + liquidazioni mensili)

Pagina **Gestione IVA** (menù «Altro»). Principio cardine: **la data in cui una
fattura arriva non è il mese in cui la sua IVA si usa.** Il sistema tiene sempre
separati tre momenti: *quando la fattura è ricevuta*, *a quale mese IVA è
attribuita per competenza*, *in quale liquidazione è stata effettivamente usata*.

- **Attribuzione automatica del periodo** (all'import di ogni fattura, e
  ricalcolabile col pannello «Calcola pregresso»): stesso mese →
  quel mese; ricevuta e registrata **entro il 15** del mese dopo, stesso anno →
  mese dell'operazione; **dopo il 15** → mese di ricezione; **a cavallo d'anno**
  (operazione a dicembre, ricevuta a gennaio) → **gennaio, mai retroattribuita a
  dicembre**.
- **Calcola pregresso**: il pannello in cima alla pagina rilegge DAVVERO tutte
  le fatture di acquisto (o solo l'anno scelto) e ricalcola l'IVA — non è una
  stima e non tocca l'IVA già usata in una liquidazione confermata. L'esito è
  **memorizzato e sempre visibile** (fatture lette, attribuite, da verificare,
  aggiornate, già utilizzate, ripartizione per anno, data dell'ultimo calcolo):
  non serve ripetere il calcolo su periodi diversi per essere certi di cosa è
  stato letto.
- **IVA disponibile non utilizzata**: elenco delle fatture la cui IVA è
  attribuita per competenza ma non ancora inserita in nessuna liquidazione, con
  totale in cima. Le note di credito (TD04/TD08) non contano come credito.
- **Liquidazione mensile**: scegli mese e IVA vendite, premi «Calcola». Il
  sistema seleziona solo le fatture del periodo **non ancora usate** e mostra
  incluse/escluse (con il motivo di ogni esclusione) e il saldo (a debito o a
  credito, col credito del mese precedente riportato). Il calcolo **non** tocca
  ancora nulla: è una bozza.
- **Conferma**: marca l'IVA delle fatture incluse come *utilizzata* legandola
  alla liquidazione. Da quel momento la **stessa fattura non può rientrare in un
  altro mese** — è il blocco alla doppia detrazione. Una liquidazione confermata
  non si sovrascrive: per correggerla va **riaperta** (libera di nuovo le sue
  fatture) oppure **rettificata** (la vecchia resta come storico, ne nasce una
  nuova versione). Ogni movimento IVA per fattura resta tracciato.
- **Riepilogo annuale**: la pagina mostra, per l'anno scelto, l'IVA divisa per
  categoria (utilizzata, non utilizzata, rinviata, indetraibile, rettificata,
  recuperata in dichiarazione, da verificare), l'IVA vendite, l'IVA detraibile
  annuale e il saldo finale (debito o credito), più il conteggio delle
  **anomalie** trovate (bloccanti e avvisi: IVA negativa, retroattribuzione a
  cavallo d'anno, date mancanti, fatture da verificare, IVA ferma da mesi).
- **Azioni manuali** sulla singola fattura (con motivazione tracciata):
  escludi, reincludi, rinvia, segna indetraibile, segna recuperata in
  dichiarazione annuale, correggi il periodo attribuito. Un'azione non è
  ammessa su un'IVA **già confermata** in una liquidazione: prima va riaperta.
- **Dashboard del mese**: per il mese scelto la pagina mostra l'IVA attribuita
  al mese, quella **ricevuta nel mese ma di competenza del mese precedente**
  (regola del 15), l'utilizzata, la non utilizzata, la rinviata e
  l'indetraibile — così si legge a colpo d'occhio lo scarto tra "quando arriva"
  e "quando si usa".
- **Chat**: puoi chiedere alla chat di spiegare l'IVA di una singola fattura;
  risponde in modo tracciabile (quando ricevuta, a quale mese attribuita, con
  quale regola, se già usata e in quale liquidazione) — esattamente la logica
  della specifica ("ricevuta l'8 febbraio, riguarda gennaio, IVA usata a
  gennaio, a febbraio non riconteggiata").

---

## 9. Cedolini e Dipendenti

- I cedolini (Libro Unico, formato Zucchetti) arrivano **via email** dallo Studio
  Ferrantini (mittenti attendibili configurati; canale attivo). Il PDF viene anche
  archiviato in copia su Drive.
- In alternativa i PDF possono essere messi nella **cartella Drive dei cedolini
  paga**: ogni ora il sistema li scarica, li deduplica per hash (stessi controlli
  dei cedolini email) e li immette nella stessa pipeline di elaborazione; i file
  lavorati vengono spostati nella sottocartella Drive `Elaborate`.
- Il parser estrae: dati anagrafici, periodo, netto, lordo, competenze, trattenute,
  IRPEF, contributi, TFR, ferie/permessi, tredicesima/quattordicesima, presenze
  giornaliere, ecc.
- **Il codice fiscale è la chiave**: il cedolino viene collegato al dipendente; se il
  dipendente non esiste ancora viene creato automaticamente; la matricola è chiave
  secondaria (uno stesso dipendente può avere più matricole nel tempo).
- Lo stesso cedolino (dipendente + matricola + mese + anno) non viene mai duplicato.
- Un PDF che contiene più di un dipendente non viene elaborato automaticamente:
  genera un avviso di verifica (mai un'elaborazione alla cieca su un formato mai
  visto).
- La creazione automatica del movimento stipendio e la riconciliazione
  cedolino↔banca/cassa non sono ancora attive (fase successiva della roadmap).

---

## 10. Scadenze operative

La pagina Scadenze mostra **solo** le scadenze che richiedono davvero attenzione:

1. fatture con **pagamento a mezzo agente** non ancora pagate;
2. **F24 da pagare**.

Non mostra tutte le date di scadenza formali delle fatture (sarebbero rumore), né i
cedolini (lo stipendio è un obbligo mensile con un suo ciclo dedicato, non una
"scadenza dubbia da sorvegliare").

Urgenza calcolata a video: **scaduta** / **imminente** (entro 7 giorni) / normale.
Azioni disponibili: Paga in Cassa / Paga in Banca / Segna già pagata (solo fatture) /
Sposta in verifica (fatture e F24 — l'avviso lo genera poi il sistema).

---

## 11. Verbali, veicoli e trattenute

**Flusso verbale**: email da mittente attendibile → estrazione di numero verbale,
targa, importo, date → collegamento al veicolo (targa) e al conducente assegnatario
→ ricerca del pagamento in prima nota (cassa e banca, finestra ampia di 90 giorni
perché le multe si pagano anche molto dopo la notifica; vale anche l'importo
ridotto) → stessa scala certo/probabile/dubbio.

**Regola non negoziabile sulla trattenuta**: se il verbale è di una targa aziendale,
con un conducente assegnato, e il pagamento risulta fatto dalla società, il sistema
**crea solo una PROPOSTA di recupero in busta paga**. La trattenuta:

1. viene proposta dal sistema (mai applicata);
2. la confermi tu, indicando esplicitamente mese e anno di competenza;
3. la comunichi al consulente del lavoro (passaggio tracciato);
4. quando arriva il cedolino di quel mese, il sistema ti avvisa di verificare che la
   trattenuta ci sia davvero — la chiusura finale resta una tua conferma manuale.

Se il cedolino atteso non arriva, avviso dedicato.

**Ciclo di vita della trattenuta** (endpoint `/api/trattenute-verbali`): stati
`proposta → confermata → comunicata_consulente → in_attesa_cedolino →
recuperata_in_busta | non_trovata_nel_cedolino | esclusa | da_verificare`.

- La proposta nasce quando il pagamento della società risulta accertato
  (upload quietanza manuale o pipeline quietanze email); il mese cedolino
  suggerito è **il mese successivo al pagamento** (formato AAAA-MM).
- **Conferma** = sempre tua, con mese cedolino esplicito; puoi anche
  **rimandare** a un altro mese (da proposta/confermata) o **escludere**
  con motivo. Ogni passaggio finisce nell'audit log.
- All'import del cedolino del mese atteso il sistema cerca nel testo le voci
  "trattenuta verbale", "multa", "recupero verbale", "trattenuta dipendente",
  "addebito auto" (maiuscole/minuscole indifferenti): se trovata, la trattenuta
  passa a `recuperata_in_busta` e il verbale viene marcato recuperato; se il
  cedolino arriva **senza** la voce scatta l'avviso "Trattenuta verbale non
  trovata nel cedolino" e lo stato `non_trovata_nel_cedolino`. Il controllo è
  best-effort: non blocca mai l'import del cedolino.
- La verifica **non guarda solo il cedolino appena importato**: un ripescaggio
  giornaliero (ore 8:30) riesamina i **cedolini vecchi già archiviati** nel
  gestionale (arrivati da posta o Drive in qualsiasi momento) per le trattenute
  confermate/comunicate/in attesa, cercando la voce nei cedolini dal mese
  suggerito in poi, con le stesse regole e gli stessi avvisi del controllo
  all'import. Se il cedolino del mese atteso non è ancora in archivio, la
  trattenuta resta com'è. Lancio manuale:
  `POST /api/trattenute-verbali/retro-verifica`. Nessun dato viene mai
  cancellato.
- **Report per il consulente**: `/api/trattenute-verbali/report-consulente`
  esporta in Excel dipendente, matricola, codice fiscale, targa, numero
  verbale, data infrazione, importi, mese cedolino suggerito, stato e nota.

**Veicoli**: anagrafica gestita a mano (targa, marca, modello, conducente, stato
contratto attivo/cessato).

---

## 12. Noleggio auto e contratti cessati

Principio del modulo (specifica 10-07-2026): auto/targa → contratto → fatture e
costi → pagamenti → driver assegnato → verbali → eventuali trattenute → report.

- **Anagrafica veicolo**: targa, marca/modello, società di noleggio, driver,
  date, **stato contratto** (attivo/cessato/da verificare — lo cambi solo tu),
  canone previsto, fringe benefit, note, **storico assegnazioni**.
- **Storico assegnazioni driver**: il sistema non guarda solo il driver attuale
  ma **il driver valido alla data dell'evento** — un verbale del 10/03 va a chi
  aveva l'auto il 10/03. Ogni cambio driver chiude il periodo precedente e ne
  apre uno nuovo, in automatico.
- I costi auto arrivano dalle **fatture** collegate al veicolo via targa
  (canoni, pedaggi, bollo, riparazioni, verbali rifatturati); la fattura resta
  una normale fattura fornitore e segue il giro Fornitore → metodo pagamento
  (di norma Banca) → Prima Nota → riconciliazione con l'estratto conto.
- **Regola non negoziabile**: contratto **cessato** → il sistema **non genera
  mai** l'avviso "manca la fattura di noleggio" (né scadenza canone); lo storico
  costi resta. Solo per i veicoli **attivi** controlla ogni giorno (ore 7:45)
  che arrivino fatture con regolarità: **soglia 35 giorni**
  (`NOLEGGIO_GIORNI_SENZA_FATTURA`).
- Se mancano fatture da oltre 35 giorni, il sistema **prima rilegge l'ultima
  fattura**: se contiene diciture di chiusura ("cessazione contratto", "ultimo
  canone", "restituzione veicolo", "conguaglio finale"...) genera un avviso
  **informativo** "probabile contratto cessato — conferma tu lo stato";
  altrimenti un avviso **soft** "da verificare". Mai un allarme grave immediato.
- Caso già deciso: **GG782PN Alfa Romeo Stelvio = contratto cessato** (il
  sistema lo imposta da solo solo se lo stato non è mai stato toccato).
- **Chat intelligente**: può interrogare (solo lettura) veicoli e verbali del
  noleggio — canone mensile, stato contratto, driver alla data grazie allo
  storico assegnazioni, verbali uniti dai due canali (posta + fatture) senza
  duplicati e senza mai esporre i PDF. Come per il resto della chat: risponde
  e propone, non modifica mai nulla.
- **Pannello "Controlli"** (in testa al tab Flotta Auto): riepilogo in un colpo
  solo di ciò che richiede attenzione, con chip cliccabili mostrati **solo se
  il conteggio è maggiore di zero** — verbali aperti (non pagati/chiusi, uniti
  dai due canali senza duplicati; il chip porta al tab Verbali), trattenute
  dipendenti da confermare, auto attive senza driver, fatture da associare a
  un veicolo (apre l'elenco già esistente), pagamenti dell'anno corrente verso
  i fornitori noleggio non ancora pagati/riconciliati e avvisi NOL_* aperti.
  I chip senza una sezione dedicata espandono una piccola lista (prime 10
  voci). Se il servizio non risponde o non c'è nulla da segnalare, il pannello
  semplicemente non compare. Dati da `GET /api/noleggio/riepilogo-controlli`.

---

## 13. Cosa è acceso e cosa è spento oggi

| Canale | Stato | Perché |
|---|---|---|
| Fatture da Drive | **Attivo** (ogni ora, scelta 13/07/2026) | parser validato su file reali |
| Corrispettivi da Drive | **Attivo** | validato su file reale del registratore |
| Cedolini via email | **Attivo** | validato su un file reale; sotto osservazione |
| Estratti conto da Drive | Spento | in attesa di export reale Banco BPM di conferma |
| Quietanze da Drive | **Attivo** (scelta 10/07/2026) | stesso motore dell'upload manuale: dedup per impronta, matching automatico F24, quadratura domenicale 5:45 |
| F24 via email | **Attivo** (scelta 13/07/2026) | interruttore `ENABLE_EMAIL_F24_SYNC`; gli F24 email confluiscono in `f24_unificato`. ⚠️ parser non ancora validato su F24 reali: controllare i primi risultati |
| Verbali via email | **Attivo** (scelta 13/07/2026) | interruttore `ENABLE_EMAIL_VERBALI_SYNC` |

Nota: F24 e Verbali via email sono stati **accesi su richiesta esplicita**
(13/07/2026) nonostante i rispettivi parser non siano ancora stati validati su
documenti reali. Ciascuno ha un interruttore dedicato (`ENABLE_EMAIL_F24_SYNC`,
`ENABLE_EMAIL_VERBALI_SYNC`) per spegnerlo senza toccare le credenziali email.
In generale il principio resta: **un canale andrebbe acceso dopo che il suo
parser è stato verificato su documenti veri** — meglio nessun dato che dati
sbagliati. Verificare i primi F24/verbali importati da email prima di fidarsi.

## 13-bis. Utenti e ruoli (chi può fare cosa)

Scelte utente 13/07/2026. Il gestionale ora distingue tre ruoli:
- **Admin**: può tutto, incluse cancellazioni di massa, rollback e impostazioni.
  Entra col PIN configurato sul server (o email+password admin).
- **Operatore**: usa e inserisce dati, ma non accede alle sezioni Admin/Utenti
  né alle cancellazioni di massa.
- **Sola lettura**: può solo consultare; ogni tentativo di modifica è bloccato
  dal server (e vede un banner giallo "sei in sola lettura").

L'admin crea gli altri utenti dalla pagina **Utenti** (voce di menù visibile
solo all'admin): nome, ruolo e un **PIN personale** (4-12 cifre). Ogni persona
entra col proprio PIN e ottiene i permessi del suo ruolo. I PIN non sono mai
salvati in chiaro; il login è protetto da blocco anti-tentativi (5 errori →
5 minuti di attesa, vale sia per il PIN sia per email+password).

**Durata sessione**: il login vale **1 ora di inattività**; mentre lavori si
rinnova da solo (non cade mai durante l'uso), se resti fermo oltre un'ora devi
rientrare.

Sicurezza correlata (audit 13/07/2026):
- Accesso da browser esterni (CORS) chiuso al solo dominio del gestionale
  impostando `CORS_ALLOWED_ORIGINS`; finché non è impostata resta aperto (con
  avviso nei log) per non interrompere il servizio.
- Login protetto: 5 tentativi falliti → 5 minuti di blocco (email e PIN).
- Le ricerche non interpretano più caratteri speciali come comandi (niente
  regex injection); gli upload hanno un limite di dimensione.
- **Ponte ERP disattivato** (scelta utente: non in uso): l'endpoint che
  riceveva fatture dall'app esterna ora rifiuta sempre finché non lo si
  riattiva impostando `ERP_BRIDGE_SECRET`.

## 14. Cosa NON fa più questo gestionale (dominio HACCP)

Decisione canonica (13/07/2026): il gestionale è un **ERP contabile**. Tutto il
dominio HACCP — ricettario, lotti, tracciabilità, food cost, produzione/cucina,
scadenze HACCP, schede tecniche dei prodotti alimentari — è demandato all'app
esterna Tracciabilità/HACCP (ceraldiapp.it) e non esiste più qui.

In concreto:
- **Schede tecniche**: rimosse (pulsante in Fornitori, ricerca web/email, PDF
  archiviati). Le collection `schede_tecniche*` si archiviano con
  `python -m app.scripts.archivia_collection_haccp --esegui` (rinomina, non
  cancella). La funzione "completa anagrafica fornitore dagli XML delle
  fatture", che viveva nello stesso router, è stata **salvata** e spostata in
  `/api/anagrafica-fornitori/popola-fornitore/{id}` (stesso pulsante di prima
  nel form fornitore).
- **Giacenze e scorte**: il gestionale non aggiorna più la giacenza fisica dei
  prodotti e non genera più l'alert "sotto scorta" (il job delle 6:30 è stato
  rimosso). Il **Dizionario Articoli resta contabile e vivo**: le fatture
  continuano ad auto-creare/aggiornare gli articoli (matching 3 livelli, alias,
  storico acquisti, ultimo prezzo/fornitore) e ad alimentare le Previsioni
  Acquisti.
- **Restano** (scelta 13/07/2026): Previsioni Acquisti (tab in Contabilità) e
  Libretti sanitari nel modulo Dipendenti.

## Libro Giornale e Libro Mastro (Contabilità → Libro Giornale)

Il registro contabile UFFICIALE del gestionale è unico: ogni operazione
definitiva (fatture e corrispettivi registrati in contabilità, accantonamenti
e liquidazioni TFR, ammortamenti annuali) riceve un **numero di protocollo
definitivo**, con la scrittura in partita doppia (DARE = AVERE). Il
protocollo è unico e progressivo **all'interno dello stesso anno**: riparte
da 1 a ogni nuovo anno solare (es. 1/2026, 2/2026, ... poi 1/2027), come nei
principali software di contabilità; una volta assegnato è immutabile.

- Le operazioni **provvisorie** (Prima Nota Provvisoria) sono definitive ma
  non certe: restano nel registro provvisorio, modificabili, e NON compaiono
  nel libro giornale finché non vengono confermate.
- **Libro Giornale**: elenco cronologico delle scritture con protocollo,
  righe per conto e verifica di quadratura.
- **Libro Mastro**: le stesse righe riclassificate per conto (mastrini).
- **Esporta registro**: scarica il file JSON autosufficiente dell'anno.
- **Reimporta** (solo Admin): ricostruisce le operazioni PARI PARI — stessi
  protocolli, date e importi di quando furono registrate — anche dopo una
  cancellazione totale del database.
