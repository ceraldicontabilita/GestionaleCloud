# Validazione logica delle 65 pagine del GestionaleCloud

Questo file è stato creato per fare due cose contemporaneamente:

1. spiegarti in modo semplice e umano come funzionano le pagine del gestionale;
2. lasciarti uno spazio dove puoi rispondere SÌ / NO / MODIFICA per confermare o correggere ogni singola logica.

Questa è la chiave di lettura:

- La fonte di verità del catalogo delle pagine è [page_catalog.json](../page_catalog.json).
- I file Markdown come questo servono a spiegare, validare e condividere la logica, ma non sostituiscono il codice e le route attive.
- I file storici e di audit in [docs/](../docs) e [memoria/](.) sono utili come riferimenti storici, ma la logica attiva va verificata su codice, route e catalogo.
- Le informazioni importanti sono: cosa prende un dato, dove lo mette, chi lo usa, cosa alimenta in altre pagine, se è automatizzato o richiede conferma.

## Come usare questo file

Per ogni pagina, puoi fare così:

- SÌ = la logica è corretta;
- NO = c’è qualcosa da correggere;
- MODIFICA = devi aggiungere o correggere la spiegazione;
- poi riscriviamo il testo e aggiorniamo i file Markdown interessati.

---

# 1) Accesso e sicurezza

## 1. Login

- Funzione: entrare nel gestionale.
- Dato che usa: username, password, sessione, profilo utente.
- Cosa alimenta: apre il resto del sistema.
- Spiegazione semplice: senza login non si può vedere nessuna pagina riservata.
- Validazione: SÌ / NO / MODIFICA

## 2. Gestione riservata

- Funzione: area di gestione accessi, utenti, autorizzazioni, configurazioni di sistema.
- Dato che usa: profili, ruoli, parametri applicativi.
- Cosa alimenta: le altre aree del gestionale.
- Spiegazione semplice: qui si decide chi può fare cosa.
- Validazione: SÌ / NO / MODIFICA

---

# 2) Dashboard e inserimento rapido

## 3. Dashboard

- Funzione: quadro generale della situazione aziendale.
- Dato che usa: fatture, scadenze, movimenti, banca, documenti, attività recenti.
- Cosa alimenta: tutte le pagine di controllo e priorità.
- Spiegazione semplice: è il centro operativo, dove vedo subito cosa sta succedendo.
- Validazione: SÌ / NO / MODIFICA

## 4. Inserimento rapido

- Funzione: creare in fretta documenti o movimenti.
- Dato che usa: informazioni già note del sistema.
- Cosa alimenta: fatture, contabilità, movimenti, documenti.
- Spiegazione semplice: serve per non perdere tempo e per standardizzare gli inserimenti.
- Validazione: SÌ / NO / MODIFICA

---

# 3) Fatture e fornitori

## 5. Archivio fatture

- Funzione: vedere tutte le fatture ricevute e/o registrate.
- Dato che usa: dati fatture, fornitori, importi, date, numeri, stato.
- Cosa alimenta: scadenze, Prima Nota, controlli fiscali, riconciliazioni.
- Spiegazione semplice: è il magazzino delle fatture.
- Validazione: SÌ / NO / MODIFICA

## 6. Corrispettivi

- Funzione: vedere incassi e movimenti dovuti ai corrispettivi, POS e pagamenti elettronici.
- Dato che usa: XML RT, accrediti, giroconti, movimenti bancari, ricevute.
- Cosa alimenta: ricavi, cassa, banca, dichiarazioni fiscali.
- Spiegazione semplice: racconta dove arriva il denaro e da dove viene.
- Validazione: SÌ / NO / MODIFICA

## 7. Fornitori

- Funzione: anagrafica fornitori, duplicati, relazioni commerciali, fatture legate a ciascun fornitore.
- Dato che usa: P.IVA, nome, alias, dati fiscali, documenti, fatture.
- Cosa alimenta: fatture, scadenze, controlli, deduplicazione, report.
- Spiegazione semplice: è la rubrica dei fornitori con il loro storico.
- Validazione: SÌ / NO / MODIFICA

## 61. Verifica fatture estere

- Funzione: controllare fatture ricevute da paesi esteri.
- Dato che usa: dati fatture, IVA estera, importi, valuta, contabilità.
- Cosa alimenta: contabilità e report di periodo.
- Spiegazione semplice: serve a controllare che le fatture non estere siano inserite correttamente.
- Validazione: SÌ / NO / MODIFICA

---

# 4) Prima Nota, cassa, personale, ritenute

## 8. Prima Nota

- Funzione: vedere e gestire la registrazione contabile delle operazioni.
- Dato che usa: movimenti contabili, documenti, fatture, cassa, banca, salari.
- Cosa alimenta: bilancio, controlli, libro giornale, gestione fiscale.
- Spiegazione semplice: è il grande libro dove ogni operazione trova il suo posto contabile.
- Validazione: SÌ / NO / MODIFICA

## 9. Pulizia Prima Nota

- Funzione: correggere anomalie, duplicati o movimenti incoerenti.
- Dato che usa: esiti della Prima Nota e log di revisione.
- Cosa alimenta: il saldo contabile corretto.
- Spiegazione semplice: è lo strumento di sanificazione del libro contabile.
- Validazione: SÌ / NO / MODIFICA

## 10. Cedolini e salari

- Funzione: gestire stipendi, cedolini, trattenute e pagamenti dipendenti.
- Dato che usa: dipendenti, periodi di lavoro, cedolini, trattenute, bonus, buste paga.
- Cosa alimenta: Prima Nota, ritenute, report fiscali, pagamenti.
- Spiegazione semplice: trasforma i dati del personale in pagamenti e registrazioni.
- Validazione: SÌ / NO / MODIFICA

## 31. Ritenute

- Funzione: gestire le trattenute e gli importi dovuti al personale o alle autorità.
- Dato che usa: cedolini, contributi, dipendenti, scadenze.
- Cosa alimenta: pagamenti, Prima Nota, dichiarazioni fiscali.
- Spiegazione semplice: le ritenute sono le cifre che vengono trattenute prima del pagamento.
- Validazione: SÌ / NO / MODIFICA

---

# 5) Flotta e verbali

## 11. Flotta noleggio

- Funzione: gestire veicoli, contratti e costi di noleggio.
- Dato che usa: veicoli, contratti, tempi, pagamenti, documenti.
- Cosa alimenta: costi, verbali, riconciliazioni, report noleggio.
- Spiegazione semplice: contiene la storia dei veicoli e dei loro costi.
- Validazione: SÌ / NO / MODIFICA

## 12. Verbali noleggio

- Funzione: registrare verbali, infrazioni e allegate ricevute o documenti collegati.
- Dato che usa: verbali, veicolo, targa, data, importo, documento di pagamento.
- Cosa alimenta: flotta, costi, pagamenti, storico del veicolo.
- Spiegazione semplice: è il registro delle multe e delle relative prove.
- Validazione: SÌ / NO / MODIFICA

## 13. Costi noleggio

- Funzione: vedere e gestire i costi del noleggio.
- Dato che usa: contratti, documenti, fatture, verbali, pagamenti, rate.
- Cosa alimenta: bilancio e reporting noleggio.
- Spiegazione semplice: aggrega i costi del servizio di noleggio in un unico posto.
- Validazione: SÌ / NO / MODIFICA

## 14. Dettaglio verbale

- Funzione: aprire e analizzare un verbale specifico.
- Dato che usa: verbale, targa, veicolo, documento, eventuale pagamento, driver.
- Cosa alimenta: la relazione tra verbale, auto e pagamento.
- Spiegazione semplice: è la scheda dettagliata di una singola multa o verbale.
- Validazione: SÌ / NO / MODIFICA

---

# 6) Contabilità e bilancio

## 15. Piano dei Conti

- Funzione: struttura dei conti di conto economico e patrimonio.
- Dato che usa: codici contabili, conti, classificazioni.
- Cosa alimenta: tutte le registrazioni contabili e il bilancio.
- Spiegazione semplice: l’elenco dei conti dove i movimenti finiscono.
- Validazione: SÌ / NO / MODIFICA

## 16. Bilancio

- Funzione: riassunto della situazione economica.
- Dato che usa: saldo di conti, movimenti, fatture, ritenute, profitto.
- Cosa alimenta: verifica e report manageriali.
- Spiegazione semplice: mostra il quadro finale del lavoro fatto.
- Validazione: SÌ / NO / MODIFICA

## 17. Verifica bilancio

- Funzione: controllare se il bilancio è coerente con i dati contabili.
- Dato che usa: conti, movimenti, bilancio, regole di controllo.
- Cosa alimenta: eventuali correzioni e report di coerenza.
- Spiegazione semplice: è il controllo di qualità del bilancio.
- Validazione: SÌ / NO / MODIFICA

## 18. Libro Giornale

- Funzione: vedere l’andamento cronologico dei movimenti contabili.
- Dato che usa: tutte le registrazioni di Prima Nota.
- Cosa alimenta: analisi storica e contabilità.
- Spiegazione semplice: è il diario dei fatti economici.
- Validazione: SÌ / NO / MODIFICA

## 19. Controllo mensile

- Funzione: monitorare le anomalie e i controlli mensili.
- Dato che usa: aggregazioni mensili, scadenze, movimenti, dichiarazioni.
- Cosa alimenta: correzioni, alert e analisi fiscal/contabile.
- Spiegazione semplice: verifica se il mese è in regola.
- Validazione: SÌ / NO / MODIFICA

## 20. Calendario fiscale

- Funzione: organizzare scadenze fiscali e obblighi di adempimento.
- Dato che usa: scadenze, tributi, date, importi, dichiarazioni.
- Cosa alimenta: alert, ritenute, pagamenti e dashboard di controllo.
- Spiegazione semplice: ricorda le scadenze senza doverle memorizzare a mente.
- Validazione: SÌ / NO / MODIFICA

## 21. Cespiti

- Funzione: gestire beni durevoli e ammortamenti.
- Dato che usa: cespiti, costo, data acquisto, valore, ammortamento.
- Cosa alimenta: bilancio, report fiscal, controlli.
- Spiegazione semplice: traccia i beni e il loro valore nel tempo.
- Validazione: SÌ / NO / MODIFICA

## 22. Finanziaria

- Funzione: gestire le componenti finanziarie, mutui, prestiti, costi e oneri.
- Dato che usa: finanziamenti, rate, interessi, scadenze.
- Cosa alimenta: bilancio, flussi di cassa, report finanziari.
- Spiegazione semplice: tiene sotto controllo i debiti e i finanziamenti.
- Validazione: SÌ / NO / MODIFICA

## 23. Chiusura esercizio

- Funzione: preparare la chiusura annuale della contabilità.
- Dato che usa: bilancio, movimenti, scadenze, dichiarazioni, saldi.
- Cosa alimenta: report di fine anno e verifica finale.
- Spiegazione semplice: è la fase finale per dire “l’anno è chiuso e verificato”.
- Validazione: SÌ / NO / MODIFICA

## 24. Budget

- Funzione: pianificare il budget aziendale.
- Dato che usa: obiettivi, spese, ricavi, vincoli, storico.
- Cosa alimenta: controllo e gestione del futuro.
- Spiegazione semplice: serve a capire quanto possiamo spendere e quanto dobbiamo guadagnare.
- Validazione: SÌ / NO / MODIFICA

## 25. Mutui

- Funzione: gestire mutui e rate finanziarie.
- Dato che usa: contratto, rata, interessi, scadenza, saldo.
- Cosa alimenta: finanziaria, bilancio, scadenze.
- Spiegazione semplice: è il registro dei debiti a lungo termine.
- Validazione: SÌ / NO / MODIFICA

## 26. Contabilità avanzata

- Funzione: gestione delle configurazioni e dei dettagli contabili più tecnici.
- Dato che usa: parametri, regole, importi e codici.
- Cosa alimenta: logica contabile di dettaglio.
- Spiegazione semplice: è il livello avanzato della contabilità.
- Validazione: SÌ / NO / MODIFICA

## 27. Utile obiettivo

- Funzione: valutare l’utile target o desiderato.
- Dato che usa: bilancio, budget, previsioni, trend.
- Cosa alimenta: decisioni aziendali e pianificazione.
- Spiegazione semplice: serve a capire se stiamo andando dove vogliamo.
- Validazione: SÌ / NO / MODIFICA

## 28. Previsioni acquisti

- Funzione: anticipare acquisti futuri.
- Dato che usa: storico acquisti, budget, scadenze.
- Cosa alimenta: pianificazione e controllo degli acquisti.
- Spiegazione semplice: aiuta a non comprare a caso.
- Validazione: SÌ / NO / MODIFICA

## 62. Dati ISA

- Funzione: archiviare o leggere dati di gruppo e classificazioni legate a ISA o rapporti di consolidamento.
- Dato che usa: dati di struttura e indicatori.
- Cosa alimenta: bilancio e analisi di gruppo.
- Spiegazione semplice: è la parte data warehouse del sistema.
- Validazione: SÌ / NO / MODIFICA

---

# 7) Automazioni, AI e controlli

## 29. Learning Machine

- Funzione: apprendimento e logica intelligente su documenti e processi.
- Dato che usa: dati storici, documenti, pattern, associazioni già fatte.
- Cosa alimenta: classificazione, deduplicazione, suggerimenti e agenti.
- Spiegazione semplice: è il motore che impara come il gestionale deve interpretare i dati.
- Validazione: SÌ / NO / MODIFICA

## 30. Scadenze

- Funzione: mostrare scadenze da rispettare.
- Dato che usa: fatture, impostazioni, rate, documenti, tributi.
- Cosa alimenta: alert e calendario di controllo.
- Spiegazione semplice: è il promemoria di tutto ciò che deve essere pagato o verificato.
- Validazione: SÌ / NO / MODIFICA

## 48. Agenti AI

- Funzione: azioni automatizzate di supporto operativo.
- Dato che usa: dati di business, documenti, logica e classificazioni.
- Cosa alimenta: flussi, alert, supporto decisionale.
- Spiegazione semplice: sono assistenti che aiutano a automatizzare le cose ripetitive.
- Validazione: SÌ / NO / MODIFICA

## 49. Impostazioni F24 email

- Funzione: configurare lo scambio e l’importazione di F24 via posta/email.
- Dato che usa: regole di lettura, canali, email autorizzate.
- Cosa alimenta: import di F24 e report fiscali.
- Spiegazione semplice: è la centralina che dice come riconoscere i F24 ricevuti per email.
- Validazione: SÌ / NO / MODIFICA

## 50. Impostazioni AI

- Funzione: configurare i parametri dell’intelligenza artificiale del sistema.
- Dato che usa: settings, regole, canali, endpoint, confidenze.
- Cosa alimenta: document classification, automazioni e assistenza AI.
- Spiegazione semplice: stabilisce come l’AI può lavorare nel gestionale.
- Validazione: SÌ / NO / MODIFICA

## 51. Integrazione OpenAPI

- Funzione: collegare il gestionale a sistemi esterni e API.
- Dato che usa: endpoint, token, ingressi e servizi esterni.
- Cosa alimenta: integrazioni, import/export e connettività.
- Spiegazione semplice: è il passaggio tra il gestionale e il resto del mondo digitale.
- Validazione: SÌ / NO / MODIFICA

## 53. Mittenti Email attendibili

- Funzione: definire quali mittenti e-mail sono affidabili per l’importazione documentale.
- Dato che usa: sender patterns, canale, autorizzazione.
- Cosa alimenta: import automatici per email, documenti, verbali, ricevute.
- Spiegazione semplice: dice al sistema: “questi mittenti sono validi, questi no”.
- Validazione: SÌ / NO / MODIFICA

---

# 8) Riconciliazioni e banca

## 32. Riconciliazione dashboard

- Funzione: riassunto globale delle riconciliazioni.
- Dato che usa: banca, documenti, movimenti, rate, associazioni.
- Cosa alimenta: decisioni di lavoro e verifiche finali.
- Spiegazione semplice: è la centralina dove vedo se tutto si incastra.
- Validazione: SÌ / NO / MODIFICA

## 33. Riconciliazione banca

- Funzione: confrontare movimenti bancari con documenti e prove.
- Dato che usa: estratto conto, movimenti, fatture, quietanze, bonifici.
- Cosa alimenta: stato riconciliato e alert di discrepanza.
- Spiegazione semplice: serve a capire se il denaro registrato coincide con quello vero in banca.
- Validazione: SÌ / NO / MODIFICA

## 34. Riconciliazione F24

- Funzione: collegare i pagamenti F24 ai documenti e alle tributarie.
- Dato che usa: F24, importi, codici tributo, documenti di pagamento.
- Cosa alimenta: saldo fiscale, pagamenti, verifiche.
- Spiegazione semplice: fa coincidere il tributo pagato con la sua prova.
- Validazione: SÌ / NO / MODIFICA

## 35. Riconciliazione stipendi

- Funzione: collegare i movimenti di stipendi e trattenute con i cedolini e i pagamenti.
- Dato che usa: salari, buste paga, movimenti banca.
- Cosa alimenta: Prima Nota, report personali e verifiche.
- Spiegazione semplice: mette in ordine i flussi del personale con i movimenti bancari.
- Validazione: SÌ / NO / MODIFICA

## 36. Riconciliazione documenti

- Funzione: collegare documenti e prove con il movimento giusto.
- Dato che usa: documenti, movimenti, importi, descrizioni, dates, path di origine.
- Cosa alimenta: stato finale di ogni documento.
- Spiegazione semplice: serve a stabilire se un documento e il pagamento appartengono allo stesso evento.
- Validazione: SÌ / NO / MODIFICA

## 37. Archivio bonifici

- Funzione: archiviare e verificare bonifici, righe e attribuzioni.
- Dato che usa: bonifici, importi, dati bancari, documenti associati.
- Cosa alimenta: riconciliazione e report di tesoreria.
- Spiegazione semplice: è il deposito dei bonifici che poi vengono incrociati con altri dati.
- Validazione: SÌ / NO / MODIFICA

## 38. Assegni

- Funzione: gestire assegni e loro riconciliazione.
- Dato che usa: assegni, movimenti, date, importi, stati.
- Cosa alimenta: banca, riepilogo contabile, verifiche.
- Spiegazione semplice: regista lo stato di un assegno fin dal momento della ricezione al saldo.
- Validazione: SÌ / NO / MODIFICA

## 39. PayPal

- Funzione: gestire pagamenti e ricevute PayPal.
- Dato che usa: pagamenti, ricevute, dati del transazione, documenti collegati.
- Cosa alimenta: riconciliazione, contabilità, report di cassa.
- Spiegazione semplice: mette in ordine i pagamenti ricevuti tramite PayPal.
- Validazione: SÌ / NO / MODIFICA

## 40. Coerenza POS

- Funzione: confrontare i corrispettivi POS con gli accrediti bancari reali.
- Dato che usa: POS, movimenti bancari, data, importo, terminale.
- Cosa alimenta: alert di discrepanza e validazione contabile.
- Spiegazione semplice: dice se l’operazione è stata correttamente registrata o se c’è stato uno scarto.
- Validazione: SÌ / NO / MODIFICA

## 44. Movimenti banca

- Funzione: dettaglio di ogni movimento bancario importato.
- Dato che usa: estratti conto, descrizioni, importi, date, stato.
- Cosa alimenta: riconciliazione, Prima Nota, alert e analisi bancaria.
- Spiegazione semplice: è il registro di tutte le entrate e uscite bancarie.
- Validazione: SÌ / NO / MODIFICA

## 52. Riconciliazione PagoPA

- Funzione: confrontare ricevute e movimenti PagoPA.
- Dato che usa: ricevute, movimenti bancari, identificativi, dati di pagamento.
- Cosa alimenta: contabilità e documenti di pagamento.
- Spiegazione semplice: collega i pagamenti elettronici alle prove di pagamento corrette.
- Validazione: SÌ / NO / MODIFICA

---

# 9) Documenti e Drive

## 41. Import documenti

- Funzione: importare documenti dal sistema, da file, da cartelle, da email autorizzate.
- Dato che usa: file, hash, provenienza, metadata, tipo documento.
- Cosa alimenta: archivio documentale, classificazione, processi successivi.
- Spiegazione semplice: è la porta di ingresso del sistema.
- Validazione: SÌ / NO / MODIFICA

## 42. Archivio documenti

- Funzione: mostrare tutti i documenti importati, raggruppati e ricercabili.
- Dato che usa: documenti, hash, categoria, provenienza, stato.
- Cosa alimenta: ricerca, classificazione, elaborazioni, rielaborazione.
- Spiegazione semplice: è il deposito dove tutte le prove sono custodite e trovate.
- Validazione: SÌ / NO / MODIFICA

## 63. Indice documentale Drive

- Funzione: tenere traccia dei documenti archiviati su Drive.
- Dato che usa: file, cartelle, metadata, hash, origine.
- Cosa alimenta: documenti, import, comparazioni, audit.
- Spiegazione semplice: è l’indice dei file importanti dentro Drive.
- Validazione: SÌ / NO / MODIFICA

## 64. Atti amministrativi

- Funzione: gestire atti e documenti amministrativi.
- Dato che usa: atti, documenti, associazioni, scadenze, processi.
- Cosa alimenta: archivio, controlli e report amministrativi.
- Spiegazione semplice: raccoglie la documentazione amministrativa del sistema.
- Validazione: SÌ / NO / MODIFICA

---

# 10) Strumenti, IVA e amministrazione

## 43. Verifica coerenza

- Funzione: controllare che i dati non siano incoerenti.
- Dato che usa: tutte le informazioni rilevanti del sistema e delle singole operazioni.
- Cosa alimenta: alert, correzioni, report di qualità.
- Spiegazione semplice: è il controllo di qualità del gestionale.
- Validazione: SÌ / NO / MODIFICA

## 45. Commercialista

- Funzione: supportare il lavoro del commercialista con report e dati coerenti.
- Dato che usa: contabilità, fatture, dichiarazioni, bilancio, scadenze.
- Cosa alimenta: report e analisi di supporto.
- Spiegazione semplice: ti aiuta a preparare la parte fiscale e contabile da condividere.
- Validazione: SÌ / NO / MODIFICA

## 46. Pianificazione

- Funzione: organizzare il lavoro nel tempo.
- Dato che usa: scadenze, priorità, task, piani e schedulazioni.
- Cosa alimenta: dashboard, alert e programmazione.
- Spiegazione semplice: è il calendario operativo dell’azienda.
- Validazione: SÌ / NO / MODIFICA

## 47. Visure

- Funzione: eseguire verifiche su documenti, fornitori, conti o soggetti.
- Dato che usa: dati fiscali, rapporti e record del sistema.
- Cosa alimenta: decisioni e controlli su soggetti esterni.
- Spiegazione semplice: aiuta a controllare chi è chi e se i dati sono affidabili.
- Validazione: SÌ / NO / MODIFICA

## 54. Admin sistema

- Funzione: gestione amministrativa del sistema.
- Dato che usa: config, utenti, settings, processi, servizi, scheduler.
- Cosa alimenta: manutenzione e controllo del funzionamento del gestionale.
- Spiegazione semplice: è il pannello del tecnico e dell’amministratore.
- Validazione: SÌ / NO / MODIFICA

## 55. Admin MFA

- Funzione: sicurezza a più fattori e autenticazione avanzata.
- Dato che usa: utenti, credenziali, MFA, configurazioni sicurezza.
- Cosa alimenta: accessi protetti.
- Spiegazione semplice: blocca l’accesso non autorizzato.
- Validazione: SÌ / NO / MODIFICA

## 56. Elaborazioni amministrative

- Funzione: processi batch e attività di manutenzione amministrativa.
- Dato che usa: documenti, dati, schedulazioni, processi.
- Cosa alimenta: correttivi, deduplicazione, consolidamenti.
- Spiegazione semplice: è il reparto manutenzione del sistema.
- Validazione: SÌ / NO / MODIFICA

## 57. Elaborazioni legacy

- Funzione: eseguire vecchi processi e batch legacy.
- Dato che usa: dati storici e archivi legacy.
- Cosa alimenta: compatibilità e migrature.
- Spiegazione semplice: serve per non perdere dati vecchi mentre si migra verso il nuovo modo di lavorare.
- Validazione: SÌ / NO / MODIFICA

## 58. Utenti

- Funzione: Gestire utenti e permessi.
- Dato che usa: profili, ruoli, accessi, credenziali.
- Cosa alimenta: sicurezza e autorizzazioni del sistema.
- Spiegazione semplice: è l’anagrafica delle persone che usano il gestionale.
- Validazione: SÌ / NO / MODIFICA

## 59. Mappa gestionale

- Funzione: mostrare il quadro complessivo delle aree del gestionale.
- Dato che usa: struttura delle pagine e moduli.
- Cosa alimenta: orientamento e navigazione.
- Spiegazione semplice: è la cartina del sistema.
- Validazione: SÌ / NO / MODIFICA

## 60. Gestione IVA

- Funzione: gestire l’IVA, i regimi, i pagamenti e i controlli fiscali.
- Dato che usa: fatture, documenti, importi, IVA, valori fiscali.
- Cosa alimenta: dichiarazioni, report e verifiche.
- Spiegazione semplice: è il motore delle imposte al momento giusto.
- Validazione: SÌ / NO / MODIFICA

---

# 11) Pagine speciali e situazioni finali

## 65. Situazione fiscale

- Funzione: riepilogo dello stato fiscale aziendale.
- Dato che usa: IVA, F24, imposte, scadenze, dichiarazioni, pagamenti.
- Cosa alimenta: controllo fiscale finale e report di discussione.
- Spiegazione semplice: ti dice se la parte fiscale è in ordine.
- Validazione: SÌ / NO / MODIFICA

---

# 12) Regole di automazione da tenere sempre presenti

Nel gestionale, i dati non devono andare in giro a caso. Le regole più importanti sono:

- un documento originale non viene sostituito o perso;
- un dato nasce da una prova e non da una supposizione;
- importo da solo non basta per associare un movimento;
- le associazioni ambigue vanno mostrate e lasciate alla scelta dell’utente;
- quando il sistema è certo, automatizza;
- quando il sistema non è certo, chiede all’utente;
- la logica del monitor Gmail deve essere verificabile e avvisare se il lavoro non arriva;
- ogni notifica importante deve andare anche a canale esterno come email o Telegram;
- se un PDF è senza testo, serve OCR di riserva e si conserva l’originale;
- ogni scansione va registrata in modo immutabile, con revisione e spiegazione dell’associazione.

---

# 13) Schema riassuntivo da usare per validare pagina per pagina

Puoi usare questo blocco, copiandolo e completando per ogni pagina:

- Pagina: numero + nome
- Funzione: …
- Dato principale: …
- Dove arriva: …
- Cosa alimenta: …
- Automatismo: sì / no / parziale
- Status: SÌ / NO / MODIFICA
- Note: …

---

# 14) Checklist finale per la validazione utente

- [ ] Ho verificato che il catalogo delle pagine coincide con [page_catalog.json](../page_catalog.json)
- [ ] Ho controllato che la logica descritta è coerente con le route e i moduli attivi
- [ ] Ho indicato le pagine da correggere o approfondire
- [ ] Ho verificato se i documenti storici in [docs/](../docs) sono da usare come memoria o come riferimento storico
- [ ] Ho deciso quali file Markdown aggiornare dopo le correzioni

Se vuoi, dopo aver risposto SÌ / NO / MODIFICA per ogni pagina, ti preparo una seconda versione del documento con le logiche modificate e gli aggiornamenti definitivi.
