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

Ultimo aggiornamento: 15/07/2026.

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
| F24 commercialista | Email da mittenti attendibili | ogni ora (**attivo** dal 13/07/2026, `ENABLE_EMAIL_F24_SYNC` — parser non ancora validato su F24 reali) |
| Verbali/multe | Email da mittenti attendibili | ogni ora (**attivo** dal 13/07/2026, `ENABLE_EMAIL_VERBALI_SYNC`) |

Regola non negoziabile: **le fatture arrivano SOLO da Drive, mai da Gmail né da PEC**.
Se una scansione email trova un file che sembra una fattura elettronica, non la importa:
genera un avviso di anomalia (qualcuno sta mandando fatture per il canale sbagliato).

**Rimosso (18/07/2026, scelta utente)**: lo scanner delle notifiche email Aruba
(`noreply@fatturazioneelettronica.aruba.it`) che creava "fatture attese" e poteva
registrare in automatico un anticipo in Prima Nota da una semplice notifica, prima
che il documento vero arrivasse. Nessun dato/fattura viene più creato o scaricato
dalla casella PEC/email per questo canale; il tab Provvisori mostra solo le fatture
reali già importate da Drive in attesa di conferma cassa/banca.

Ogni documento entra in "Documenti / Import" con uno stato di lavorazione:
trovato → importato → classificato → elaborato dal parser → record gestionale creato.
Se il parser fallisce: stato di errore + avviso, il documento resta consultabile.

---

## 2-bis. Pagina "Scarica Documenti da Email" (Documenti)

Aggiunta 15/07/2026 dopo una segnalazione dell'utente. La pagina ha **tre viste**,
che leggono da fonti diverse — non sono la stessa lista mostrata in modo diverso:

- **Per Mittente**: raggruppa i documenti "non associati" (non ancora collegati a
  un fornitore/pratica) per l'ente/mittente che li ha mandati — pensata per
  smaltire un arretrato, es. vecchie ricevute Agenzia Entrate Riscossione mai
  lavorate.
- **Tutti i Documenti**: l'elenco completo di ciò che il sistema ha scaricato via
  email, con categoria, mittente, oggetto, data email, dimensione e stato.
- **AI Estratti**: i documenti che l'intelligenza artificiale ha già letto ed
  estratto (numero, importo, date...).

**Cosa scarica il job automatico** (ogni ora, `gmail_full_scan_task`): tutte le
cartelle della casella, filtrando **solo per parole chiave amministrative**
(circa 50 termini generici tipo "fattura", "f24", "bolletta", "enel", "verbale",
"cedolino"...) — **mai le fatture italiane**, che arrivano solo da Drive/SDI (§3).

**Mittenti attendibili — LA LISTA È IL VANGELO** (regola vincolante utente
18/07/2026): la posta si scarica **SOLO** dai mittenti configurati nella pagina
**Mittenti Email**. Nessuna eccezione:

| Canale | Filtro mittente | Dove si configura |
|---|---|---|
| Cedolini (email) | Sì, attivo | Mittenti Email → tipo "Cedolino" |
| Verbali/multe (email) | Sì, attivo | Mittenti Email → tipo (dedicato ai verbali) |
| Fatture estere (PDF) | Sì, attivo | Mittenti Email → tipo "Fattura estera (PDF)" |
| **Scansione generica ("Documenti")** | **Sì, whitelist assoluta**: accetta qualunque mittente presente in Mittenti Email (di qualsiasi tipo, attivo); **lista vuota = non scarica NULLA** | Mittenti Email (tutti i tipi) |

Prima del 18/07/2026 valeva "lista vuota = nessuna restrizione", ed erano
entrati documenti da mittenti mai autorizzati (es. saveris2.net, pec.kimbo.it,
PEC legalmail via pec.fatturapa.it). Ora esiste anche la pulizia retroattiva:
`POST /api/email-download/pulizia-non-attendibili` (admin, prima `dry_run=true`)
elimina dai vari archivi email i documenti il cui mittente non è in lista,
**insieme agli alert associati**. Dalla finestra alert, il click su un alert
porta direttamente al documento in questione (fattura, prima nota, F24...).

**Campi talvolta vuoti ("-") in "Tutti i Documenti"**: "Mittente"/"Da Email" sono
vuoti per i documenti arrivati da **Google Drive** (es. Libro Unico/cedolini
sincronizzati dalla cartella Drive dedicata) — è corretto, quei documenti non
hanno un mittente email. La colonna "Data Doc." (la data scritta sul documento,
diversa dalla data dell'email) risulta invece **sempre vuota per qualunque
documento**: nessun servizio di importazione la valorizza oggi — non è un dato
mancante solo per le Buste Paga, è una colonna non ancora collegata a nessuna
fonte.

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
3. La fattura eredita il metodo di pagamento del fornitore. **REGOLA
   aggiornata dall'utente il 18/07/2026** (supera la 17/07 "banca =
   registrata subito"): all'ingresso della fattura XML,
   - fornitore con metodo **Cassa** (contanti) → l'uscita viene registrata
     **subito** in Prima Nota Cassa e la fattura risulta pagata contanti
     (il contante non lascia traccia da riconciliare);
   - fornitore con metodo **Banca** → la fattura resta **Provvisoria**
     finché la **riconciliazione** (estratto conto, PayPal o carta) non
     trova l'addebito reale: è la riconciliazione a registrare l'uscita
     in Prima Nota Banca e a marcare la fattura pagata;
   - fornitore **Misto**, senza metodo, o con metodo ambiguo (paypal,
     carta, da_configurare) → **Provvisoria**: confermi tu la divisione
     tra cassa e banca, e solo dopo nascono i movimenti veri.
   La registrazione usa il writer canonico dei pagamenti (riferimento
   FATT-{id}, idempotente: mai due movimenti per la stessa fattura,
   anche su reimport).
3-bis. **Cambio del metodo di pagamento in anagrafica fornitore** (18/07/2026):
   quando salvi un metodo diverso, il sistema **riprocessa da solo la Prima
   Nota** dell'anno corrente: le registrazioni nate col metodo sbagliato
   (es. fattura in Banca di un fornitore ora a Cassa, o riga banca mai
   riconciliata con l'estratto conto) tornano in **Provvisoria** e la
   fattura torna "da pagare", pronta per essere confermata dal lato giusto.
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
   **Corretto 15/07/2026**: il parsing AI di fatture e F24 da foto/PDF non
   testuale (`/api/ai-parser/parse-fattura`, `/parse-f24`) usava due
   percorsi di classificazione paralleli e divergenti dal motore unico —
   niente fallback sulla tabella statica per le fatture (un fornitore non
   ancora configurato restava sempre "non classificato" anche quando il
   contenuto delle righe bastava), e una mappatura tributi F24 hardcoded
   con ID di fantasia per gli F24. Ora entrambi passano dallo stesso
   motore usato ovunque altro (`classifica_fattura_con_learning`,
   `classifica_f24_per_tributo`).
   **Deducibilità IRES/IRAP/IVA**: esistono 5 tabelle indipendenti nel
   codice con le stesse percentuali per categoria (centro di costo
   ufficiale, più altri 4 motori di categorizzazione/bilancio/calcolo
   imposte) — non ancora unificate su un'unica fonte. **Bug corretto
   15/07/2026**: una di queste (`categorizzazione_contabile.py`, voce
   "carburante") deduceva il carburante al 100% invece del 20% corretto
   per auto aziendali a uso promiscuo (art. 164 TUIR) — le altre 4 fonti
   usavano già tutte 20%, coerenti tra loro. Per la stessa fattura di
   carburante il gestionale poteva mostrare contemporaneamente €100 e €20
   di costo deducibile a seconda della pagina interrogata. Le altre voci
   delle 5 tabelle non sono state riconciliate voce per voce: se noti un
   altro numero che non torna tra due pagine, segnalalo.
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
9. **"Elimina fattura" non cancella mai dal database** (verificato 15/07/2026):
   di default il bottone Elimina fa un'archiviazione ("soft delete" — la
   fattura resta nel database con `status/entity_status="deleted"`, così come
   righe, Prima Nota e scadenze collegate; i movimenti di magazzino vengono
   annullati, gli assegni collegati solo sganciati). La cancellazione fisica
   esiste (`hard_delete=true`) ma **nessuna pagina la usa**: dall'interfaccia
   non è raggiungibile. **Corretto il 15/07/2026**: la pagina Archivio
   Fatture e il dettaglio fattura ora escludono `entity_status/status
   ="deleted"` — una fattura eliminata non ricompare più in lista/dettaglio.

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
(bonifico, POS bancario, F24…), che vanno in Prima Nota Banca. **Prima Nota Banca
non ha questa marcatura**: un inserimento manuale diretto in banca non viene
distinto da uno automatico né controllato per duplicati.

**REGOLA CANONICA POS** (utente, 18/07/2026 — confermata e definitiva)

**Cassa** (giorno di vendita)
- **DARE**: corrispettivo totale del giorno (dall'XML del registratore).
- **AVERE** "POS Verso Banca": il **POS REALE** — quello che la sera si
  trascrive nella pagina **Coerenza POS**, direttamente nella riga del giorno,
  cioè quello che esce davvero dal terminale. NON l'elettronico dell'XML, che
  è soltanto il dato fiscale di confronto. Se la chiusura serale non è ancora
  trascritta, il vecchio movimento può mostrare temporaneamente il fallback
  XML; appena si salva il valore del terminale, Cassa e Banca vengono entrambe
  riallineate e la riga indica `quota_pos_fonte=chiusura_manuale`. Anche 0,00 è
  un valore manuale esplicito e non riattiva il fallback XML.
- "Paga in Cassa" su una fattura → uscita collegata alla fattura.

**Banca**
- **DARE**: la **stessa cifra del POS reale**, come puro **TRASFERIMENTO**
  cassa→banca (source `trasferimento_pos`, stesso `trasferimento_id`
  dell'uscita di cassa): **una sola operazione scritta su due registri**,
  come i versamenti di contanti. Mai una seconda registrazione
  indipendente, mai duplicazioni.
- L'**accredito dell'estratto conto** NON crea mai un'entrata: **riconcilia**
  il trasferimento del suo giorno di vendita (letto dalla causale NUMIA
  "DEL gg/mm/aa"), accumulando i circuiti (bancomat, carte, Amex) fino a
  concorrenza; lo stato verde viene mostrato soltanto quando il totale
  accreditato quadra con il POS reale secondo la tolleranza configurata.
- "Paga in Banca" su una fattura → uscita collegata alla fattura.

**Coerenza POS — il "non battuto"**
- Confronto giornaliero: elettronico **XML** (fiscale) vs **POS reale**
  serale (operativo). Se il reale è maggiore, la differenza è il **NON
  BATTUTO** sul registratore, evidenziato giorno per giorno con **saldo
  progressivo cumulato**: così si sa quanto battere in più nei giorni
  successivi per recuperare.
- Il campo **POS terminale (modifica)** salva il totale giornaliero in
  `chiusure_pos_manuali`, aggiorna l'uscita POS della Prima Nota Cassa e il
  trasferimento atteso della Prima Nota Banca con lo stesso
  `trasferimento_id`. Non modifica mai `corrispettivi.pagato_elettronico`.
- **Importa totali POS** accetta piu' righe `AAAA-MM-GG;importo`: tutte le
  righe vengono validate prima della scrittura e poi passano dallo stesso
  motore idempotente dell'editor giornaliero.
- L'estratto conto resta il terzo controllo: l'accredito della banca deve
  combaciare col trasferimento (invariante del collaudo notturno
  "trasferimento_pos_speculare": uscita cassa POS = entrata banca POS,
  stesso giorno, stesso importo).
- Tutte le scritture di Prima Nota stanno migrando al **motore unico**
  (`app/services/scritture_contabili.py`): un test-guardia vieta nuovi
  punti di scrittura diretta.
- **Bug grave corretto 16/07/2026 — la Banca mostrava solo uscite.** I saldi
  della Prima Nota escludevano l'intera categoria "Corrispettivi POS", ma
  quella categoria la scrivono due percorsi diversi: vecchie chiusure POS
  isolate e il trasferimento canonico Cassa→Banca. Il trasferimento usa il POS
  reale del terminale quando disponibile e il fallback XML solo finché manca
  l'inserimento manuale; l'estratto conto lo riconcilia senza duplicarlo.
  Risultato: ~204.000€ di incassi POS 2026 sparivano dai saldi banca. Adesso
  l'esclusione distingue per **origine** del movimento, non per categoria:
  - trasferimento POS Cassa→Banca → **conta** (fonte manuale, oppure fallback
    XML finché non viene compilata la chiusura);
  - chiusure POS di verifica (serale mobile, import pos.xlsx) → escluse;
  - la vecchia copia integrale dell'estratto conto dentro Prima Nota Banca
    (sync legacy, usato in passato per gen-apr 2026) → esclusa dai saldi:
    duplicava sia i pagamenti fatture (già registrati dai flussi del
    gestionale, contati due volte) sia gli accrediti POS. I movimenti
    restano nel database, semplicemente non vengono più sommati.
  Anche la vista Banca della pagina Prima Nota (che affianca estratto conto
  reale e movimenti del gestionale) ora nasconde gli accrediti POS del
  provider dalle somme: sono la stessa moneta della quota POS giornaliera
  già in elenco.
- **Riporto iniziale modificabile a mano (16/07/2026)**: nelle schede Cassa
  e Banca della pagina Prima Nota la card "Riporto iniziale" ha una matita:
  puoi impostare a mano il saldo al 1° gennaio dell'anno (es. il riporto che
  viene dal 2025). Quando è impostato **sostituisce** il riporto calcolato
  dai movimenti degli anni precedenti in tutti i punti che usano la funzione
  unica di saldo (Prima Nota, Bilancio, Finanziaria, Stats) — utile quando
  lo storico a sistema è parziale e il riporto calcolato non è affidabile.
  Endpoint: `GET/PUT /api/prima-nota/saldo-iniziale`,
  `DELETE /api/prima-nota/saldo-iniziale/{tipo}/{anno}` (tornare al calcolato).
- **Pulizia duplicati corrispettivi in Prima Nota (16/07/2026)**: verificato
  live che vecchie pipeline smantellate avevano lasciato in cassa 1066
  entrate "Corrispettivi" per 149 corrispettivi reali (37 giorni con 26
  copie), 50 giorni con l'uscita POS doppia (categoria "POS" oltre a "POS
  Verso Banca") e 37 "Girofondi POS". Il rebuild
  (`POST /api/corrispettivi/rebuild-prima-nota`) ora ripulisce TUTTE le
  righe generate dai corrispettivi (per source, qualunque categoria) e
  ricrea per ogni giornata SOLO i due movimenti canonici di cassa (entrata
  totale + uscita quota POS verso banca) più l'entrata POS in banca; i
  movimenti manuali (versamenti, pagamenti fatture) non vengono toccati.
  Il rebuild inoltre non crea mai due entrate per lo stesso
  (giorno, matricola, totale) anche se in collection restano documenti
  corrispettivi duplicati.
- **Import "pulito per anno" da Drive (16/07/2026)**: in Admin → Fatture,
  card "Import per anno (Drive)": selezioni l'anno e premi "Importa". Il
  sistema legge la data dentro ogni file delle cartelle Drive (fatture e
  corrispettivi) e importa nel flusso contabile attivo SOLO i documenti di
  quell'anno; gli altri finiscono in archivio storico per consultazione.
  In più, i documenti dell'anno scelto già archiviati in passato (quando
  era attivo un altro anno: il file su Drive è ormai in Elaborate e il
  sync non lo rivedrebbe mai) vengono **ripresi dall'archivio** e fatti
  entrare nel flusso attivo — i corrispettivi con i due movimenti canonici
  di cassa + POS banca, le fatture ripassando l'XML originale salvato
  nella pipeline completa (fornitore, prima nota provvisoria, eventi).
  Endpoint admin: `POST /api/config-import/importa-anno` (imposta anche
  l'anno attivo condiviso, `PUT /api/config-import/anno`).
- **REGOLA (utente, 16/07/2026): in contabilità restano SOLO i dati
  dall'anno operativo 2026 in poi.** I dati di anni precedenti (movimenti
  2021-2022 da vecchi backfill, fatture 2021-2022, salari 2023-2025,
  partite aperte 2023-2024 — 4.236 documenti in totale) sono stati
  eliminati definitivamente il 16/07/2026 con
  `POST /api/prima-nota/pulizia-pre-anno` (endpoint admin, dry_run di
  default per contare prima di eliminare). Da allora i riporti di cassa e
  banca partono da 0 e si impostano a mano con la card "Riporto iniziale"
  (vedi sopra). Se in futuro rientrano dati di anni vecchi (reimport
  storici), la stessa pulizia è rieseguibile.

**REGOLA PAGAMENTI BANCA (utente, 18/07/2026 — supera quella del 17/07)**:
una fattura NON diventa mai "pagata" solo perché il fornitore ha metodo
banca. La fattura con fornitore "banca" resta **provvisoria** finché la
**riconciliazione** (estratto conto bancario, PayPal o carta) non trova
l'addebito reale: è la riconciliazione a registrare l'uscita in Prima Nota
Banca e a marcare la fattura pagata. Solo il fornitore a metodo **cassa**
(contanti) viene registrato subito in Prima Nota Cassa, perché il contante
non lascia traccia da riconciliare.

**Provvisoria**
- Fatture di fornitori "misto" o senza metodo (divisione manuale) E fatture
  di fornitori "banca" in attesa dell'addebito reale in estratto conto.

**Corretto 15/07/2026 — pagamento fattura registrato a mano in Cassa/Banca ora
marca sempre la fattura come pagata.** Prima di questa correzione, registrare a
mano in Prima Nota Cassa (o Banca) il pagamento di una fattura specifica
(`fattura_id` collegato a un'uscita) creava il movimento ma **non aggiornava lo
stato della fattura**: una riconciliazione bancaria successiva la trovava ancora
"da pagare" e, se trovava un match per importo/fornitore, creava un **secondo
movimento reale** per la stessa fattura (doppio conteggio). Ora un'uscita
Cassa/Banca con `fattura_id` marca sempre `pagato=true`, `stato_pagamento=
"pagata"`, `metodo_pagamento` e l'id del movimento collegato — stesso
comportamento del flusso "Paga in Cassa/Banca" da scheda fattura. Un'entrata
(es. corrispettivo) collegata per errore a un `fattura_id` non tocca invece
nulla: non rappresenta mai un pagamento fornitore.

**Fatture ESTERE via email** (Integrazioni → Mittenti Email)
- Le fatture **italiane** arrivano sempre via SDI/Aruba/Drive in XML (FatturaPA):
  non si scaricano mai da Gmail. Lo SDI è un sistema **solo italiano**: i
  fornitori **esteri** non ci passano e mandano un semplice **PDF** in
  allegato via email — ma non si può sapere in anticipo chi sono: si
  scoprono solo dopo aver ricevuto la prima fattura.
- Quando ne arriva una, in **Integrazioni → Mittenti Email** aggiungi
  l'indirizzo/dominio del mittente scegliendo il tipo "Fattura estera (PDF)":
  da quel momento il sistema scarica automaticamente le email di quel
  mittente, **ogni ora**. Zero mittenti configurati = nessuna email
  scaricata (nessun rischio di prendere roba indesiderata).
- **Dal 14/07/2026 il PDF viene anche letto automaticamente** (stessa AI già
  usata per gli altri documenti): estrae numero, data, fornitore, imponibile,
  IVA, totale e crea una fattura vera con la stessa pipeline delle fatture
  XML italiane (fornitore auto-creato/aggiornato, **prima nota sempre
  provvisoria** — conferma manuale come per tutte le altre fatture — e
  partita aperta collegata). Da quel momento la fattura estera è visibile
  come le altre e il matching automatico **PayPal** e **bonifico bancario**
  già esistenti la aggancia da sola per importo+fornitore, e l'alert
  "fattura scaduta non pagata" scatta anche per lei come per le italiane.
  Il PDF resta comunque sempre archiviato in Documenti (categoria "Fatture
  estere (PDF)"). Se l'estrazione fallisce o non riesce a leggere numero e
  importo, non viene creata nessuna fattura: resta solo il PDF archiviato,
  da lavorare a mano (nessun dato inventato).
- Il fornitore viene agganciato/creato **esplicitamente sulla P.IVA estera**
  (formati UE non italiani inclusi, non solo l'11 cifre italiano): fatture
  successive dello stesso fornitore convergono sullo stesso record invece
  di restare orfane, ed è un segnale in più di lettura corretta oltre al
  nome. La nazione viene dedotta dal prefisso della P.IVA (es. "DE..." →
  Germania), per non marcare per errore un fornitore estero come "P.IVA
  italiana non standard".
- **Coda di verifica + rating di affidabilità** (pagina **Fatture estere
  da verificare**, link dalla pagina Mittenti Email e alert cliccabile):
  ogni fattura estera importata dall'AI entra in questa coda finché
  l'utente non conferma o corregge i dati letti (numero, data, fornitore,
  P.IVA, imponibile, IVA, totale) confrontandoli col PDF originale (link
  diretto al PDF nella stessa riga). Se correggi un campo, la fattura
  viene aggiornata con il valore giusto (compresi i campi speculari
  italiani, e se cambi numero/P.IVA/data anche la chiave di dedup e la
  scadenza vengono ricalcolate); se l'importo era sbagliato e la partita
  aperta collegata non ha ancora ricevuto nessun pagamento, viene
  corretta anche quella (se invece è già parzialmente pagata NON viene
  toccata in automatico, per sicurezza). Ogni conferma/correzione
  alimenta uno storico per fornitore ("X/Y letture corrette") mostrato
  sulla stessa pagina, così nel tempo si vede quali fornitori l'AI legge
  sempre bene e quali richiedono più attenzione.
- La stessa pagina permette di configurare anche altri tipi di documento
  (cedolino, PagoPA, INPS, INAIL, PayPal, cartella esattoriale) se un giorno
  servisse un mittente attendibile per quei canali.

**MODELLO SEMPLICE della Banca (regola utente 17/07/2026, "rifatta da
zero")**: la Prima Nota Banca è un registro di SOLE operazioni del
gestionale — Corrispettivi POS, Versamento Banca, Prelevamento Banca,
Fatture, Utenze, F24, Stipendi, Assegni, Pagamento PayPal — identico alla
Cassa: riporto iniziale modificabile + operazioni. **L'estratto conto NON
viene più fuso nella vista Banca**: resta nella pagina Riconciliazione
come controllo di quadratura. Prima la fusione contava DUE VOLTE le stesse
uscite (il pagamento registrato dal gestionale e l'addebito bancario hanno
spesso date diverse e la de-duplicazione per data+importo non li
agganciava): la vista mostrava 601.859€ di uscite contro 344.437€ reali.

**Categorie = OPERAZIONI (regola utente 17/07/2026)**: in Prima Nota la
categoria dice l'operazione, sintetica al massimo — mai la classificazione
della banca; il dettaglio (chi, cosa, riferimento) sta nella descrizione.
Le voci operative della Banca sono: Fatture, Utenze, Versamento Banca,
Prelevamento Banca, Corrispettivi POS, Pagamento PayPal, Rimborso, Assegni,
Commissioni bancarie, F24, Stipendi, Altro. Le righe dell'estratto conto
mostrate nella vista Banca vengono tradotte al volo in queste voci
(`mappa_categoria_ec`, campo calcolato `categoria_canonica` — la
classificazione bancaria originale resta intatta sulla riga di estratto
conto): prima la causale (PayPal — che la banca classifica in 3 modi
diversi —, versamento contanti, prelievo, utenza), poi la tassonomia del
CSV (Fornitori/Servizi/Assicurazione/Leasing → Fatture, Utenze → Utenze,
Operazioni Finanziarie → Commissioni bancarie, Tasse → F24, Risorse Umane →
Stipendi, Ricavi residui → Rimborso, resto → Altro).

**Categorie unificate (17/07/2026)**: un solo nome per concetto, ovunque:
- **"Fatture"** = tutti i pagamenti di fatture fornitori (prima convivevano
  anche "Pagamento fornitore", "Fornitori", "fornitori");
- **"Versamento Banca"** = contanti che vanno da cassa a banca (prima anche
  "Versamento" e "trasferimento_interno" lato banca);
- **"Prelevamento Banca"** = contanti che vanno da banca a cassa (prima
  "Prelievo" e "trasferimento_interno" lato cassa).
Tutti i punti del gestionale che scrivono in prima nota usano questi nomi;
lo storico è stato rinominato con `POST /api/prima-nota/unifica-categorie`
(admin, dry_run di default, idempotente).

**Prelevamenti di contanti (doppia scrittura, 17/07/2026)**: regola speculare
al versamento — quando nell'estratto conto c'è un prelievo di contanti
(bancomat/sportello/ATM), il sistema registra l'**entrata in Prima Nota
Cassa** ("Prelevamento da banca") e l'**uscita in Prima Nota Banca**
("Prelevamento verso cassa"), categoria "Prelevamento Banca" su entrambe.
Vale sia per i nuovi import sia per il pregresso (stesso endpoint
`ripara-versamenti-cassa`, idempotente).

**Versamenti di contanti (doppia scrittura, 17/07/2026)**: un versamento di
contanti in banca è per definizione **due movimenti collegati**: un'**uscita in
Prima Nota Cassa** (il contante lascia il cassetto, categoria "Versamento") e
un'**entrata in Prima Nota Banca** (lo stesso denaro arriva sul conto). La fonte
di verità è l'**estratto conto**: ogni riga con causale versamento (la banca —
Banco BPM — scrive "VERS. CONTANTI", riconosciuta insieme alla forma estesa
"VERSAMENTO CONTANTI") genera automaticamente la doppia scrittura all'import.
Per il pregresso esiste `POST /api/estratto-conto-movimenti/ripara-versamenti-cassa`
(opzionale `?anno=`): riesamina tutte le righe dell'estratto conto e crea le
gambe mancanti in modo **idempotente** — non duplica mai un versamento già
registrato a mano (categoria "Versamento Banca") né l'entrata banca già creata
dal sync dell'import; la riga di estratto conto viene marcata riconciliata
(`tipo_riconciliazione: "versamento_contanti"`). Il versamento non è mai un
costo né un ricavo: è denaro che si sposta da cassa a banca, il patrimonio
complessivo non cambia.

**Ordine del registro (17/07/2026)**: a video i movimenti sono ordinati **dal
più recente al meno recente** (i giorni scendono da oggi verso il 1° gennaio);
dentro la stessa giornata però la lettura resta quella naturale: **prima
l'entrata del corrispettivo, poi l'uscita del POS verso banca** — mai al
contrario. La riga gialla del "Saldo iniziale 01/01" (riporto modificabile a
mano) sta quindi **in fondo all'ultima pagina**, sotto il movimento più vecchio
dell'anno.

**Saldo progressivo**: ogni movimento porta il saldo aggiornato a quel punto,
calcolato **sempre in ordine cronologico** (indipendente dall'ordine a video) e
sempre sull'elenco completo del periodo, mai sulla selezione filtrata. Un
movimento retrodatato ricalcola a cascata i saldi successivi. A parità di giorno
l'ordine di inserimento è garantito (la quota contanti in cassa e la quota POS
in banca nascono dallo stesso corrispettivo, in sequenza).

**Protezioni**: un doppio click su "Conferma" non può creare movimenti doppi
(la seconda richiesta viene rifiutata); ogni azione registra chi/quando (audit log).

**4-bis. Riparto entrate per origine** (richiesta utente 18/07/2026): sotto le
card Entrate/Uscite/Saldo di Cassa e Banca compare il dettaglio delle entrate
per tipo — POS trasferito dalla cassa, versamenti contanti, note di credito,
finanziamento soci, altre entrate (cassa: corrispettivi, prelievi da banca,
apporto soci, altre). Include il confronto diretto "uscito dalla cassa" vs
"entrato in banca" per il trasferimento POS del periodo selezionato: se non
torna (Δ ≠ 0) è segnalato in rosso — verifica visiva della REGOLA CANONICA POS
sopra, senza aprire il collaudo.

**4-ter. Finanziamento Soci** (richiesta utente 18/07/2026, tab "👥 Soci" di
Prima Nota): scheda personale per ciascuno dei quattro soci — Vincenzo
Ceraldi, Giuseppina Pane, Antonietta Ceraldi, Valerio Ceraldi. Estrazione
automatica dall'estratto conto (idempotente, `app/services/finanziamenti_soci.py`):
un bonifico in **entrata** con il nome del socio nella causale è un **apporto**
nella sua scheda; un bonifico in **uscita** verso il socio diventa **rimborso**
SOLO se la causale contiene esplicitamente rimborso/restituzione/finanziamento
(altrimenti resta fuori — es. lo stipendio a un socio dipendente non è un
rimborso del finanziamento). Ogni scheda mostra apporti, rimborsi e credito
residuo; è possibile aggiungere/eliminare movimenti a mano per i casi che la
lettura automatica non copre. Registro analitico separato: non scrive in
prima_nota_cassa/banca.

**4-quater. Carta di credito Nexi** (richiesta utente 18/07/2026): le singole
spese con la carta Nexi **non arrivano mai** in estratto conto bancario — solo
l'**addebito mensile** (riga con "NEXI" in causale, che salda il mese
precedente). Ogni volta che l'estratto conto viene importato o arriva posta,
`app/services/nexi_carta.py` cerca questi addebiti e: se manca lo statement
carta Nexi del periodo, genera l'alert "Estratto conto Nexi mancante"
(chiedendo di allegarlo — bottone dedicato nella tab Banca di Prima Nota,
PDF, stessa pipeline di parsing usata per il download automatico via email);
se lo statement c'è, confronta l'addebito con la somma delle operazioni
carta del periodo (tolleranza 0,01€) e segnala se non quadra.

---

## 5. Corrispettivi e coerenza POS (calendario accrediti)

Regola di fondo: **il confronto POS↔banca usa sempre il calendario di giorni
lavorativi e festivi, mai il semplice mese contabile.** Uno slittamento spiegato dal
calendario non è un'anomalia e non genera mai avvisi.

1. Nella tabella giornaliera inserisci il totale mostrato dal terminale nel
   campo **POS terminale (modifica)** e premi **Salva** (oppure Invio). Il dato
   fiscale XML resta invariato e viene usato solo per la FASE 1.
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
Banca) riconosce soltanto i movimenti positivi dell'estratto conto con causale di
incasso POS NUMIA e riferimento **`DEL gg/mm/aa`**. Quel riferimento è il giorno
dell'operazione: tutti i circuiti con lo stesso giorno sono sommati e confrontati
con il POS terminale manuale di quel medesimo giorno. La data contabile della
banca non decide l'abbinamento. Le righe NUMIA di remunerazione DCC, commissione
o fattura sono sempre escluse.
Nota (fix 12/07/2026): prima il caricatore non cercava la parola "NUMIA" e
filtrava su un campo `tipo` non sempre valorizzato, quindi non agganciava gli
accrediti NUMIA e la card "Accrediti banca mancanti" mostrava un falso disavanzo
(soldi in realtà incassati e presenti in banca).

**Nota sul corrispettivo manuale provvisorio** (audit 15/07/2026): il pulsante
rapido "Corrispettivo" nel tab Prima Nota Cassa crea una riga cassa segnata
esplicitamente `provvisorio: true`, pensata per essere **sostituita** quando
arriva il vero XML del corrispettivo. Il pulsante "Ricostruisci da corrispettivi"
in Pulizia Prima Nota (§ sotto) la cancella fisicamente insieme alle righe
automatiche per rigenerarle dai corrispettivi reali: è il comportamento voluto
per quella riga provvisoria, ma se per una data non esiste (ancora) nessun
corrispettivo XML corrispondente, il pulsante la elimina senza ricrearne una al
suo posto — la cassa di quel giorno resta scoperta senza un avviso esplicito.

**Un solo registratore telematico, matricola che può cambiare** (fix 15/07/2026,
precisazione utente): l'attività ha **un unico registratore di cassa**, non più
punti vendita — ma la sua matricola/ID dispositivo può cambiare nel tempo (es.
al risigillo triennale obbligatorio in occasione della verifica fiscale
periodica). Il controllo duplicati dei corrispettivi guarda data **+ dispositivo
emittente**, non solo la data: questo evita che un corrispettivo con la matricola
nuova (dopo un risigillo) venga scartato come "duplicato" di uno con la matricola
vecchia sulla stessa data, o viceversa. Prima di questa correzione il controllo
guardava solo la data e ignorava la matricola: un corrispettivo con ID diverso
dall'ultimo registrato poteva sparire del tutto da Prima Nota invece di essere
salvato, con l'incasso — sia contanti che elettronico — sistematicamente perso
per quella giornata. Per riparare lo storico: pagina **Pulizia Prima Nota →
"Quadratura corrispettivi da Drive"** (ripassa gli XML originali e recupera
quelli mai salvati) seguito da **"Ricostruisci da corrispettivi"** (rigenera
Cassa/Banca dai corrispettivi ora completi).

**Export mensile per il commercialista** (pagina Commercialista, bottone
"🗂️ Export ZIP completo", `GET /api/commercialista/export-completo/{anno}/{mese}`
— riscritto e collegato al bottone il 15/07/2026, prima l'endpoint esisteva
ma non era raggiungibile da nessuna pagina). Lo ZIP contiene **solo**:
- **Prima Nota Cassa** e **Prima Nota Banca** del mese (CSV);
- **Assegni emessi** nel mese (CSV) — solo quelli davvero consegnati a un
  beneficiario (stato diverso da "vuoto"/"compilato"), non i numeri ancora
  in bianco;
- i **PDF delle fatture ESTERE** ricevute via email nel mese (cartella
  `fatture_estere/` dentro lo ZIP) — **mai** le fatture italiane, che
  arrivano sempre via SDI/XML e il commercialista riceve già da quel
  canale. Le fatture estere sono riconosciute dal campo interno che le
  identifica in modo univoco (`source="email_gmail_estera"`, l'unico punto
  del sistema che le crea), e il PDF viene recuperato dall'archivio email
  (`documents_inbox`) tramite il collegamento salvato sulla fattura.
Non include più fatture italiane, corrispettivi, riepilogo IVA o buste
paga come nella versione precedente: sono dati che il commercialista
riceve già da altri canali.

---

## 6. Riconciliazione bancaria (estratto conto ↔ prima nota banca)

Riscritta il 15/07/2026 per rispecchiare il motore realmente in produzione
(`app/services/riconciliazione_bancaria.py`, "motore A" — la versione precedente
di questo paragrafo descriveva un algoritmo a soglie fisse mai davvero
implementato).

**Da dove arrivano i movimenti banca**: l'estratto conto (CSV/Excel Banco BPM,
cartella Drive dedicata **o** upload manuale dalla pagina Prima Nota) viene letto
riga per riga; ogni riga diventa un movimento in `estratto_conto_movimenti` con
un'impronta propria (data+importo+descrizione): ricaricare lo stesso estratto non
duplica nulla. Il motore di riconciliazione gira **subito dopo ogni import** e poi
di nuovo ogni 30 minuti (scheduler), sempre e solo sui movimenti non ancora
riconciliati.

**Come cerca un pagamento (per le USCITE)**: per ogni movimento banca in uscita non
riconciliato, cerca fra le fatture fornitore **non pagate** con importo compatibile
(uguale ±0,05€, o "a rata" fra il 50% e il 200%) e assegna un punteggio:
- +10 se l'importo combacia esattamente (+5 se combacia solo al ±10%, +2 se è solo
  "plausibile" come rata);
- +5 se il nome del fornitore compare nella causale (+3 se somiglia soltanto);
- +5 se il numero fattura compare nella causale;
- +2 se la data del movimento è vicina alla scadenza fattura (±7gg), **-5** se la
  data è irrealistica (pagamento prima della fattura o oltre ~13 mesi dopo — scarta
  quel candidato anche se l'importo tornasse per puro caso);
- se il fornitore ha metodo "Cassa" in anagrafica, un match sulla sola banca viene
  scartato a meno che il punteggio non sia già molto alto (evita falsi positivi:
  un fornitore che paghi sempre in contanti non deve "agganciarsi" a un movimento
  bancario casuale con lo stesso importo).

**Cosa succede in base al punteggio:**

| Punteggio | Condizione | Cosa fa il sistema |
|---|---|---|
| **≥ 15** | importo + fornitore/numero fattura in causale | segna la fattura **pagata**, crea il movimento in Prima Nota Banca, propaga l'evento "fattura pagata" — tutto automatico |
| **10–14** | solo importo + un altro indizio, **un solo** candidato con data plausibile | pagata automaticamente ma a confidenza media |
| **10–14** | più fatture con punteggio simile, o data non plausibile | **non decide**: crea un "dubbio" (`operazioni_da_confermare`) con l'elenco dei candidati e un alert — la scelta resta tua |
| **= 10** | solo importo, **un solo** candidato con quell'importo esatto | pagata automaticamente (bassa confidenza, ma univoco) |
| **= 10** | più fatture con lo stesso importo esatto | "dubbio", stessa logica di cui sopra |
| **nessun candidato** | — | il movimento resta **non riconciliato**: nessuna fattura si sblocca da sola |

**F24** (uscite): se la causale contiene "F24" e l'importo torna (±0,05€) con un F24
non ancora riconciliato, lo segna pagato in automatico e propaga l'evento.
**Versamenti di contanti** (entrate, causale con "vers"/"contanti"): se esiste già
in Prima Nota Cassa l'uscita "Versamento" della stessa data/importo, la concilia e
crea la corrispondente entrata "voce in dare" in Prima Nota Banca (prima del
15/07/2026 questa voce banca non veniva mai creata: il contante risultava uscito
dalla cassa senza mai arrivare in banca — bug corretto). **Accrediti POS**
(causale con "NUMIA" o simili): non creano una nuova entrata (la quota POS è già
in Prima Nota Banca dal corrispettivo, vedi §5) — marcano solo riconciliato il
movimento per non contare due volte lo stesso incasso.

**Riconciliazione Assegni** (`app/routers/bank/assegni_auto_match.py`, 4
livelli L1-L4, N:M): tra le fatture candidate a un assegno **non compaiono
mai** i fornitori che arrivano solo su carta di credito o addebito bancario
(al limite bonifico) — mai su assegno. Lista dettata dall'utente il
18/07/2026: Amazon, ABC acquedotto, Fastweb, PayPal, Enel, Leasys (Plan/
Italia), Arval. Vale per l'auto-match, le proposte di associazione manuale e
i suggerimenti di correzione. Nel modale di collegamento manuale (e nella
lista "assegni ambigui" da risolvere a mano) il **totale delle fatture
selezionate** e la **differenza con l'importo dell'assegno** sono mostrati
in tempo reale mentre spunti le fatture — niente calcolatrice.

**Rate FatturaPA e conferma umana (20/07/2026).** Il parser conserva tutti i
blocchi `DatiPagamento` e tutti i relativi `DettaglioPagamento`, nell'ordine
del documento. Il piano XML genera una scadenza separata per ciascuna rata;
la chiave `fattura + blocco + rata` e un indice univoco rendono la creazione
idempotente anche in caso di replay concorrenti. Una rata resta visibile come
`aperta` anche quando richiede verifica: il sistema aggiunge i motivi della
verifica, non la nasconde con uno stato escluso dalle query esistenti.

Il piano XML descrive **quando e quanto si dovrebbe pagare**, ma non prova che
il pagamento sia avvenuto. Per una fattura con piu' rate e' quindi vietato
creare da Provvisori un unico movimento Banca/Cassa pari al totale documento.
L'auto-match assegni e' sempre una **anteprima senza scritture**; ogni proposta
L1-L4 deve essere confermata esplicitamente. Alla conferma il server ricalcola
la proposta sullo stato corrente, riserva gli assegni contro doppi clic e crea
un movimento per ogni evidenza reale. Le quote vengono applicate alle singole
scadenze in ordine di data, con chiave evidenza idempotente: lo stesso assegno
non puo' chiudere una seconda rata e un solo incasso non chiude mai tutte le
scadenze della fattura.

**Se non trova nulla di tutto questo**, il movimento banca resta "non riconciliato"
ma **non sparisce mai**: subito dopo l'import, un passaggio generico crea comunque
una riga in Prima Nota Banca con categoria "Da categorizzare" (o quella letta dal
file, se presente) collegata al movimento originale — così ogni euro che passa in
banca è sempre visibile e ricategorizzabile a mano, mai perso in silenzio.

Esiste anche la **riconciliazione manuale**: colleghi tu un movimento banca a una
riga di prima nota. Se nel frattempo il sistema aveva già riconciliato quella riga,
la tua richiesta viene rifiutata con un conflitto (mai una sovrascrittura muta).

Le righe già riconciliate non rientrano mai nei giri successivi (né dello scheduler
né di un nuovo import). Un movimento va "in verifica" solo su tua azione.

**Corretto 15/07/2026**: un movimento "dubbio" resta `riconciliato=False` finché non
lo confermi, quindi lo scheduler (ogni 30 minuti) lo rielabora ad ogni passaggio.
Prima di questa correzione, ogni rielaborazione creava un **nuovo** record
duplicato in "operazioni da confermare" per lo stesso movimento, invece di
riusare quello già aperto: il conteggio dei dubbi cresceva ogni mezz'ora finché
non intervenivi. Ora, se per quel movimento esiste già un'operazione aperta, non
ne viene creata una seconda.

---

## 7. F24 e Quietanze

Distinzione non negoziabile: **l'F24 è il documento DA pagare; la quietanza è la
prova UFFICIALE dell'avvenuto pagamento.** Sono due archivi separati che il sistema
collega — mai confusi. Per questo **non esiste** un bottone "segna F24 pagato": un
F24 risulta pagato solo quando gli viene collegata una quietanza.

- Gli F24 arrivano via email dal commercialista (mittenti attendibili — canale
  attivo dal 13/07/2026, `ENABLE_EMAIL_F24_SYNC`; parser non ancora validato
  su F24 reali, vedi §13). Le **quietanze** entrano da DUE porte
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
- **Corretto 15/07/2026**: un F24 PDF caricato dalla pagina **Import Documenti**
  (classificazione automatica del tipo file) passava dal workflow "parser paghe"
  (`f24_parser.py`, collection separata `f24_pagamenti`, tributi/distinte/
  riconciliazione dedicati) e non compariva **mai** nella lista F24 né nel
  conteggio "F24 da pagare" di Scadenze, che leggono solo la collezione
  canonica `f24_unificato`. Ora ogni F24 caricato da lì genera anche un
  record "ponte" nella collezione canonica (stesso F24, stesso stato), così
  resta visibile ovunque — senza toccare il flusso parser-paghe originale,
  che continua a funzionare come prima.

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

### 7-bis. Ritenute d'acconto (pagina Ritenute, 18/07/2026)

Le fatture XML con blocco **DatiRitenuta** (RT01 persone fisiche / RT02
società) generano una riga nella sezione **Ritenute**: importo memorizzato,
**scadenza il 16 del mese successivo** alla data fattura. Il motore poi:
1. cerca l'**F24 con codice tributo 1040** e stesso importo e lo **associa**
   alla ritenuta (l'F24 arriva dalla commercialista — mai ricostruito in
   automatico, come da SPECIFICA F24);
2. legge lo stato di pagamento dell'F24 (quietanza/estratto conto) e
   classifica: **pagata puntuale** (entro il 16), **pagata con
   ravvedimento** se nell'F24 ci sono anche i codici del ravvedimento —
   **8906** (sanzione ridotta sostituti d'imposta) + **1989** (interessi) —
   oppure **in ritardo SENZA ravvedimento** (da sistemare);
3. senza F24 in archivio la riga resta "da pagare" e, superata la
   scadenza, "SCADUTA da versare".
I codici del ravvedimento sono memorizzati anche nella sezione codici
tributo (`/api/ritenute/codici-ravvedimento`; in anagrafica F24 sono
censiti pure 8904/1991 per l'IVA e 8901/1990 per l'IRPEF). Aggiornamento
con il bottone "Aggiorna da fatture e F24" o via `POST /api/ritenute/scan`.

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
  paga**: ogni ora il sistema li scarica, li deduplica per hash MD5 (stesso campo
  `file_hash` usato per la dedup dei cedolini email) e li immette nella stessa
  pipeline di elaborazione; i file lavorati vengono spostati nella sottocartella
  Drive `Elaborate`. **Non esiste un canale di upload manuale generico per i
  cedolini**: solo email e questa cartella Drive.
- **Quadratura settimanale (domenica alle 5:15)**: ripassa TUTTI i PDF nella
  sottocartella Elaborate e verifica che ciascuno abbia il suo documento nel
  gestionale; un buco (file spostato in Elaborate ma mai arrivato al gestionale)
  viene **recuperato automaticamente**, rielaborandolo. **Corretto 15/07/2026**:
  questo controllo verificava solo che il file fosse arrivato nel gestionale, non
  che fosse davvero diventato un cedolino vero in contabilità (un parsing fallito
  o un dipendente non riconosciuto lasciavano il documento bloccato per sempre,
  senza nessun avviso). Ora la stessa quadratura verifica anche questo: se un
  documento (Drive o email) resta "non processato" per più di 6 ore, genera un
  alert `CEDOLINO_MAI_PROCESSATO` con l'elenco dei file bloccati (consultabile
  anche a mano, `GET /api/cedolini/drive/quadratura-completa`).
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
- **La creazione automatica del movimento stipendio e la riconciliazione
  cedolino↔banca/cassa SONO attive** (nota corretta 15/07/2026: questa sezione
  diceva il contrario, non era più vero). Ogni cedolino elaborato crea un
  movimento in `prima_nota_salari` e un accantonamento TFR mensile; la
  riconciliazione con l'accredito reale in banca/cassa è automatica per importo
  e nome dipendente.
- **Import storico bonifici da Excel (20/07/2026)**: il foglio puo' contenere
  insieme `IMPORTO BUSTA` e `IMPORTO ACCONTO`: vengono importati **entrambi**
  sulla stessa riga, mantenendo distinti il netto busta e il pagamento
  documentato. Le righe con la sola busta vengono conservate; quelle prive di
  entrambi gli importi vengono ignorate. `IMPORTO ACCONTO` non diventa mai un
  movimento bancario verificato per il solo fatto di essere nel foglio. Le
  righe sono idempotenti e ancora **non riconciliate**. Nessun cedolino viene
  collegato in questa fase: il confronto successivo richiede nome, periodo e
  importo coerenti, mentre lo stato "riconciliato" richiede anche l'evidenza
  univoca nell'estratto conto.
- **Riprocessamento AI cedolini (20/07/2026)**: il modello documentale non e'
  piu' uno snapshot Anthropic ritirato scritto nel codice. Usa
  `ANTHROPIC_DOCUMENT_MODEL`, poi `ANTHROPIC_MODEL`, con default
  `claude-sonnet-4-6`; i cedolini fino a quattro pagine vengono letti per
  intero. Ogni tentativo viene contato anche in caso di errore, evitando stati
  incoerenti come "42 errori / 0 processati".
- **Bug corretto 15/07/2026 (doppio conteggio reale)**: il canale che elabora
  davvero i PDF (parser + evento `cedolino.importato`) poteva generare **due**
  movimenti in `prima_nota_salari` per lo stesso stipendio, perché il controllo
  anti-duplicato dell'handler cercava una combinazione di campi che il
  movimento scritto dal parser non aveva mai. Ora un movimento già presente
  per lo stesso dipendente+mese+anno blocca sempre il secondo, da qualunque
  parte del sistema sia nato.
- **Bug corretto 15/07/2026 (Fondo TFR invisibile)**: il riepilogo TFR aziendale
  e il Conto Economico leggevano il fondo accantonato da un campo che viene
  valorizzato SOLO da un vecchio percorso di caricamento manuale (Libro Unico),
  mai usato in pratica: il TFR maturato dai cedolini email/Drive (il canale
  realmente attivo) risultava sempre a zero nei report, pur essendo accantonato
  correttamente "sotto al cofano". Corretto per leggere entrambi i canali.
- **Il TFR non viene mai calcolato dal sistema quando il valore reale è
  stampato sul cedolino**: il parser legge dal PDF la quota TFR del mese
  (voce "TFR mese"/"Quota anno"); questo valore reale viene usato per
  l'accantonamento mensile. Solo se il cedolino non riporta questa voce (PDF
  di formato non standard, dato non presente) il sistema ricade su una stima
  (lordo del mese / 13,5, art. 2120 c.c.), chiaramente distinguibile perché
  non è il dato stampato in busta. **Bug corretto 15/07/2026**: il canale
  email/Drive estraeva già questo valore dal PDF ma non lo passava
  all'accantonamento, che quindi usava sempre la stima anche quando il dato
  reale era disponibile.
- **Registro TFR mese per mese** (pagina Cespiti & TFR, tab "TFR"): ogni
  dipendente in elenco è espandibile e mostra il dettaglio degli
  accantonamenti mensili (periodo, quota del mese estratta dal cedolino,
  eventuale rivalutazione), oltre a liquidazioni/anticipi già erogati e
  disponibile residuo. Serve da base per imputare gli ammortamenti a rateo
  nel bilancio provvisorio. **Bug corretto 15/07/2026**: anche l'endpoint
  che alimenta questo dettaglio (`GET /api/tfr/situazione/{id}`) leggeva il
  totale solo dal campo dell'import manuale mai usato in pratica — stesso
  bug del riepilogo aziendale, corretto allo stesso modo.

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

**Scan email con priorità** (job orario, completato il 18/07/2026 — audit P1-4):
"prima completa, poi aggiungi". FASE 1: per i verbali sospesi il sistema cerca
prima la **quietanza** nelle fonti strutturate (transazioni PayPal per IUV/targa/
importo, ricevute PagoPA su Gmail, addebiti SDD PayPal in estratto conto) e in
subordine via ricerca testuale IMAP; poi cerca il **PDF** mancante tra gli
allegati già scaricati o via IMAP. FASE 2: cerca nuovi verbali (scanner Gmail
dai mittenti attendibili + cartelle email dedicate) e nuove quietanze da
associare; le quietanze senza verbale restano "orfane" in attesa. Massimo 30
completamenti per scan. On-demand: `POST /api/verbali-riconciliazione/scan-email`
(admin). Interruttore canale: `ENABLE_EMAIL_VERBALI_SYNC`.

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

## 12-bis. Collaudo automatico (dal 18/07/2026)

Ogni notte alle 4:30 (e a richiesta con `POST /api/collaudo/esegui`) il
sistema verifica in **sola lettura** le regole che devono essere sempre
vere — il collaudo fotografa, non corregge mai nulla da solo:

1. nessuna fattura "pagata banca" senza movimento di estratto conto
   collegato (regola vincolante 18/07);
2. nessun addebito di estratto conto registrato due volte in Prima Nota
   Banca, né righe collegate a movimenti inesistenti;
3. accrediti POS in banca ≈ elettronico dei corrispettivi XML, giorno di
   vendita per giorno di vendita (scostamenti oltre il 2% segnalati);
4. nessun documento in archivio da mittenti fuori dalla lista Mittenti
   Email, né file tecnici PEC/SDI;
5. nessun documento processato che mostri ancora badge NUOVO;
6. nessuna ritenuta d'acconto oltre scadenza senza F24 (o pagata tardi
   senza ravvedimento);
7. nessuna fattura duplicata attiva (stessa P.IVA+numero+data);
8. nessuna fattura "pagata" il cui movimento di Prima Nota è stato
   eliminato;
9. nessuna riga stipendio riconciliata senza bonifico collegato;
10. nessun movimento di Prima Nota malformato (importo non positivo,
    data vuota, tipo non valido).

Ogni violazione diventa un **alert "Collaudo automatico"** in dashboard
(cliccabile); quando il check torna pulito, l'alert si risolve da solo.
Report completi in `GET /api/collaudo/ultimo` e `/storico`.

Esiste anche il **collaudo UI** (`scripts/collaudo_ui.mjs`): un browser
vero apre ogni pagina del gestionale e registra errori JavaScript,
chiamate API fallite e pagine vuote — senza mai premere bottoni che
modificano i dati.

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

---

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

Durata sessione: vedi §0 (1 ora di inattività, rinnovo automatico durante l'uso).

Regola di sicurezza sui ruoli (20/07/2026): il valore storico `user` viene
normalizzato a **Operatore** per non bloccare gli account esistenti. Un JWT con
ruolo mancante o sconosciuto viene invece rifiutato e non può mai ottenere
privilegi amministrativi per fallback. I login amministrativi emettono
esplicitamente `admin`.

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

Disaster recovery (20/07/2026): il ripristino Atlas si collauda sempre su una
destinazione temporanea distinta e in sola lettura. Lo script
`scripts/verifica_ripristino_mongodb.py` confronta inventario, conteggi, indici
e hash di campione senza stampare URI o documenti. La procedura completa è in
`memoria/DISASTER_RECOVERY_MONGODB.md`; backup attivo, retention, RPO e RTO
devono essere confermati nella dashboard Atlas e non sono dedotti dal codice.

---

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
- **Restano** (scelta 13/07/2026): Previsioni Acquisti (tab in Contabilità).
- **Dipendenti — solo dati contabili/fiscali** (scelta 14/07/2026): il
  gestionale HR completo (contratti di lavoro, libretti sanitari,
  regolamento aziendale, presenze/turni disciplinari, ecc.) è un programma
  **esterno** a questo gestionale. Qui nel modulo Dipendenti restano solo i
  dati che servono alla contabilità: anagrafica minima (per collegare CF↔
  cedolino), cedolini paga e TFR. Rimossi dal codice: CRUD contratti
  (`contratti_dipendenti`), CRUD e import massivo libretti sanitari
  (`libretti_sanitari`), relativi alert/scadenze/report PDF.

---

## 15. Libro Giornale e Libro Mastro (Contabilità → Libro Giornale)

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
- **Corretto 15/07/2026**: ogni riga del Libro Giornale/Mastro mostra ora
  anche il **conto ufficiale CEE** corrispondente (colonna "Conto CEE
  ufficiale"), oltre al codice operativo interno (es. "05.01.01") usato dal
  motore di registrazione. Prima i due report più usati dal commercialista
  mostravano SOLO il codice operativo interno, senza mai passare dalla
  conversione ufficiale (`app/services/mapping_piano_conti.py`) — in
  contrasto con la regola vincolante "piano dei conti solo CEE ufficiale".
  Il codice operativo resta comunque visibile (serve alla ricostruzione
  pari-pari della contabilità, art. 2216 c.c.); il conto CEE si aggiunge,
  non lo sostituisce. Se per un codice operativo non esiste ancora un
  mapping ufficiale, la colonna resta vuota — segnale che va aggiunto in
  `OPERATIVO_A_UFFICIALE`.

**Chiusura Esercizio / Apertura Nuovo Esercizio** (pagina Chiusura Esercizio)
- **Bug gravissimo corretto 15/07/2026**: il bottone "Apri nuovo esercizio"
  calcolava il saldo cassa/banca dell'anno appena chiuso e lo inseriva come
  movimento "Riporto" in Prima Nota Cassa/Banca per il 1° gennaio del nuovo
  anno. Ma il saldo mostrato in Prima Nota (§4) è **già automaticamente
  cumulativo** su tutta la storia (somma tutti i movimenti reali con data
  precedente al 1° gennaio dell'anno in corso): il movimento "Riporto" si
  sommava quindi IN PIÙ al saldo già portato avanti dai movimenti veri,
  **raddoppiando** il saldo cassa/banca ad ogni apertura d'esercizio (e
  l'errore restava per sempre nello storico, peggiorando ad ogni chiusura
  successiva). Verificato che nessuna chiusura era mai stata eseguita in
  produzione prima della correzione: nessun dato reale è stato corrotto.
  Ora "Apri nuovo esercizio" salva solo il riepilogo saldi (consultabile da
  `GET /saldi-iniziali/{anno}`) senza creare alcuna scrittura contabile
  aggiuntiva — il riporto resta automatico come sempre.

---

## 16. Stato Patrimoniale: Immobilizzazioni, Fondo TFR e Voci di Bilancio Manuali

Richiesta utente 15/07/2026: poter comporre un vero bilancio di esercizio,
non solo cassa/banca/crediti/debiti. **Bug corretto**: fino a questa data lo
Stato Patrimoniale (pagina Bilancio) non includeva MAI le immobilizzazioni
né il Fondo TFR, pur essendo entrambe voci reali di bilancio — il patrimonio
netto (calcolato per differenza attivo-passivo) risultava quindi sempre
sovrastimato.

- **Immobilizzazioni (attivo)**: somma di due fonti, mai sovrapposte —
  1) i cespiti tracciati nella pagina Cespiti & TFR (`valore_residuo`,
  già al netto del fondo ammortamento), filtrati per data di acquisto non
  successiva alla data del bilancio; 2) le voci inserite a mano (vedi sotto)
  con codice CEE nei macro-gruppi 03/05/07 (immobilizzazioni immateriali,
  materiali, finanziarie) — per saldi di apertura, avviamento o beni non
  tracciati da una fattura XML.
- **Fondo TFR (passivo)**: somma degli accantonamenti TFR (`tfr_accantonamenti`,
  entrambi gli schemi/canali — vedi §9) fino alla data del bilancio incluso
  il mese selezionato: un bilancio a giugno 2026 include gli accantonamenti
  fino a giugno 2026, non quelli successivi.
- **Voci di bilancio manuali** (nuova sezione in fondo alla pagina Bilancio,
  tab Stato Patrimoniale): per capitale sociale, riserva legale, riserva
  straordinaria, risultati portati a nuovo e immobilizzazioni non derivabili
  automaticamente. Usa SOLO i codici del piano dei conti CEE ufficiale
  (regola vincolante CLAUDE.md), ristretti alle voci di Stato Patrimoniale —
  endpoint `GET/POST/DELETE /api/voci-bilancio/`. Una sola voce per
  (codice, anno): salvare di nuovo lo stesso codice nello stesso anno
  aggiorna l'importo, non lo duplica.
- **Capitale e riserve manuali sono solo informative**: il patrimonio netto
  del bilancio resta calcolato per differenza (attivo - passivo), così lo
  Stato Patrimoniale è sempre in pareggio; le voci di capitale/riserve
  inserite a mano sono mostrate a confronto ("di cui da voci inserite a
  mano") ma MAI sommate nel totale, perché potrebbero non coincidere
  esattamente col plug (es. utile dell'esercizio in corso non ancora
  chiuso) — sommarle romperebbe l'uguaglianza attivo=passivo.
- **Ammortamenti a rateo mensile** (pagina Bilancio, quando si seleziona un
  mese specifico invece di "Anno intero"): mostra, solo a titolo
  informativo, l'ammortamento maturato dai cespiti fino a quel mese —
  rateo lineare da inizio anno (`quota annuale ordinaria / 12 × mesi
  trascorsi`, stesso calcolo del pulsante "Ammort. {anno}" di Cespiti &
  TFR ma diviso per mese). Endpoint `GET /api/cespiti/calcolo-rateo/{anno}/{mese}`,
  solo preview come l'analogo `/calcolo/{anno}`: non scrive mai sul
  registro cespiti. Serve per imputare un ammortamento coerente in un
  bilancio provvisorio infra-annuale, senza toccare l'ammortamento
  definitivo (quello resta registrato solo a fine anno).
- **Cespiti creati automaticamente dalle fatture XML**: da questa data, ogni
  fattura passiva importata (email o upload manuale) fa scattare in
  automatico lo stesso riconoscimento del bottone "Scan Fatture XML" di
  Cespiti & TFR (parole chiave su descrizione riga + soglia 200€): se una
  riga fattura viene riconosciuta come attrezzatura/impianto/mobilio/ecc.,
  il cespite viene creato subito, senza bisogno di lanciare lo scan a mano.
  Lo scan manuale resta utile solo per il backfill delle fatture importate
  prima di questa data. Anti-duplicato: stessa chiave (descrizione + valore)
  tra scan manuale e trigger automatico, non crea mai due cespiti per la
  stessa riga fattura. **Bug corretto nello stesso intervento**: lo scan
  manuale confrontava un dedup_key troncato a 100 caratteri contro
  descrizioni salvate troncate a 200 — per righe con descrizione tra 100 e
  200 caratteri il confronto non coincideva mai, rischiando un duplicato ad
  ogni riscan.

---

## 17. Decisioni AI: anti-rumore semantico e versioni

Dal 20/07/2026 il registro degli agenti distingue tra una nuova **rilevazione**
e una nuova **decisione**:

- se problema, fatti, regole e azione proposta non cambiano, il sistema non
  crea un'altra scheda: incrementa `occurrence_count` e aggiorna `last_seen_at`;
- identificativi tecnici della sorgente, timestamp e metadati di scansione non
  bastano da soli a creare una nuova decisione;
- se cambiano i fatti sostanziali o l'azione, viene creata una nuova `version`;
  la versione precedente resta integra nell'audit ed e' marcata `superseded`;
- una versione superata non puo' essere approvata o eseguita;
- l'API e la pagina mostrano per impostazione predefinita una sola decisione
  corrente per problema. Lo storico resta disponibile con il parametro
  `includi_storico=true` e non viene cancellato o migrato automaticamente;
- il raggruppamento riconosce anche le chiavi delle decisioni storiche create
  prima di questa regola, senza modificare i record di produzione.
- ogni scheda espone fonti applicative minimizzate, regole applicate e ruolo
  approvatore; dopo approvazione o rifiuto conserva anche identita', data e
  nota dell'amministratore, senza eseguire l'azione proposta.

La regola non introduce un intervallo temporale arbitrario: il riuso dipende
dall'identita' semantica e dalla fotografia sostanziale, non dai minuti
trascorsi. Nessuna azione operativa viene eseguita dal motore decisionale.

---

## 18. Cash flow 13 settimane: anomalie e qualita' dati

La regola `CF13W-002` mantiene gli scenari base, prudente e stress e aggiunge
evidenze strutturate, tutte calcolate senza scritture operative:

- se lo scenario base scende sotto zero, segnala la prima settimana negativa;
- se solo lo scenario stress scende sotto zero, lo evidenzia come attenzione;
- record senza data, importo o classificazione restano esclusi e sono mostrati
  separatamente, senza valori stimati;
- le scadenze gia' decorse restano riportate nella prima settimana e sono
  esposte come anomalia distinta;
- la schermata mostra copertura, conteggi per motivo di esclusione e anomalie.

Non e' stata introdotta alcuna nuova soglia configurabile: il saldo negativo
e la presenza di dati incompleti sono condizioni esatte. L'agente CFO resta in
shadow mode e non crea pagamenti, movimenti contabili o disposizioni bancarie.

---

## 19. Tesoreria shadow: liquidita' e riconciliazioni operative

La fotografia Tesoreria usa esclusivamente servizi di lettura e aggregati
minimizzati:

- i saldi cassa e banca provengono dal motore unico della Prima Nota, incluse
  le esclusioni canoniche e gli eventuali riporti manuali configurati;
- le chiusure POS manuali vengono confrontate soltanto con accrediti NUMIA
  realmente presenti nell'estratto conto e dotati del giorno operativo `DEL`;
- remunerazioni, commissioni e fatture NUMIA non sono prove di accredito POS;
- per assegni, bonifici e PayPal vengono esposti solo conteggio e totale degli
  elementi ancora senza riconciliazione completa;
- nomi, beneficiari, IBAN, causali e identificativi di transazione non entrano
  nello snapshot decisionale.

Il controllo POS attende sette giorni, valore esplicito e parametrico coerente
con la finestra gia' usata dal gestionale, prima di classificare una chiusura
come priva di evidenza bancaria. Una differenza di importo viene valutata al
centesimo, senza tolleranze percentuali o soglie economiche arbitrarie.

Liquidita' negativa produce una proposta L3; code di riconciliazione ed
evidenze POS mancanti o non coerenti producono raccomandazioni L1. L'agente non
riconcilia, non modifica saldi e non crea pagamenti o accrediti sintetici.

---

## 20. Crediti shadow: aging e bozze interne

L'agente Crediti legge le fatture emesse aperte e usa soltanto le scadenze e
gli importi residui esplicitamente registrati. Se il residuo non e' presente,
usa il totale meno l'importo pagato solo quando entrambi sono dati numerici
validi. Non stima date o importi mancanti.

- distingue esattamente crediti scaduti e non ancora scaduti rispetto alla
  data di esecuzione;
- aggrega gli scaduti per mese di scadenza, senza fasce arbitrarie;
- esclude note di credito, fatture chiuse e residui nulli;
- espone solo conteggi, totali e date aggregate, senza nomi o identificativi
  cliente;
- prepara nel registro decisionale una bozza generica L3, da verificare con
  le evidenze bancarie e con la posizione del cliente;
- non dispone di alcun canale di invio: email, PEC, notifiche e comunicazioni
  esterne restano disabilitate anche dopo l'approvazione della proposta.

I record senza scadenza o importo sono esclusi dall'aging e generano una
raccomandazione L1 di qualita' dati. L'agente gira una volta al giorno e al
riavvio, subordinato all'interruttore globale delle automazioni AI.

---

## 21. Compliance shadow: permessi, audit e code documentali

Il controllo Compliance e' interamente in sola lettura e fornisce agli agenti
solo contatori e percentuali:

- sugli account PIN considera esclusivamente utenti attivi e segnala ruoli non
  canonici o nomi mancanti; non legge PIN, hash o salt e non modifica account;
- sul registro audit misura la presenza dei campi canonici (identificativo,
  data, modulo, azione, attore e riferimento entita'); i record legacy restano
  integri e non vengono completati o eliminati automaticamente;
- sulla coda documentale conta elementi pendenti, in errore, privi del payload
  MongoDB o ancora non associati; non legge filename, contenuti o anagrafiche.

Le anomalie di permesso producono una proposta L3, perche' qualunque cambio di
ruolo o disattivazione richiede una scelta dell'amministratore. Audit incompleto
e code documentali producono raccomandazioni L1. Un documento pendente o non
associato non viene definito legalmente mancante: e' soltanto un elemento da
verificare nel relativo flusso operativo. Nessun record viene creato, associato,
corretto o eliminato dall'agente.
