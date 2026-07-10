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

Ultimo aggiornamento: 10/07/2026.

---

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

I movimenti non si inseriscono mai liberamente: nascono sempre da un'azione precisa.

**Cassa**
- Conferma di un corrispettivo giornaliero → **due movimenti**: entrata per l'intero
  corrispettivo, uscita per il POS elettronico (che è in viaggio verso la banca).
  Il netto in cassa è il contante effettivo.
- "Paga in Cassa" su una fattura → uscita collegata alla fattura.

**Banca**
- "Paga in Banca" su una fattura → uscita collegata alla fattura.
- Registrazione di un accredito POS → entrata con categoria "pos_accreditato".

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
A parità di giorno l'ordine di inserimento è garantito (l'uscita POS segue sempre
l'entrata corrispettivo).

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

---

## 8. Cedolini e Dipendenti

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

## 9. Scadenze operative

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

## 10. Verbali, veicoli e trattenute

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

## 11. Noleggio auto e contratti cessati

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

## 12. Cosa è acceso e cosa è spento oggi

| Canale | Stato | Perché |
|---|---|---|
| Fatture da Drive | **Attivo** | parser validato su file reali |
| Corrispettivi da Drive | **Attivo** | validato su file reale del registratore |
| Cedolini via email | **Attivo** | validato su un file reale; sotto osservazione |
| Estratti conto da Drive | Spento | in attesa di export reale Banco BPM di conferma |
| Quietanze da Drive | **Attivo** (scelta 10/07/2026) | stesso motore dell'upload manuale: dedup per impronta, matching automatico F24, quadratura domenicale 5:45 |
| F24 via email | Spento | nessun F24 reale mai visto dal parser |
| Verbali via email | Spento | nessun verbale reale mai visto dal parser |

Il principio è sempre lo stesso: **un canale si accende solo dopo che il suo parser
è stato verificato su documenti veri** — meglio nessun dato che dati sbagliati.
