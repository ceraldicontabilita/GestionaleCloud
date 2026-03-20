# CERALDI GROUP ERP — Flusso Completo per Sezione
> Documento di revisione — Aggiornato 20 Marzo 2026
> Formato: Da dove arrivano i dati → Cosa fa → Cosa popola → Cosa aspetta per chiudersi

---

## 📒 PRIMA NOTA CASSA

**Da dove arrivano i dati:**
I dati entrano da due canali principali:
1. Il **file XML corrispettivi** emesso dal registratore di cassa (obbligatorio per legge, trasmesso all'AdE) che viene importato dalla pagina Import Documenti — il sistema lo legge e carica automaticamente gli incassi giornalieri suddivisi per tipologia (contanti, carta, ticket).
2. **Inserimenti manuali** per spese piccole in contanti (spese di piccola cassa: consumo ufficio, piccole forniture, mance ecc.).

**Cosa fa:**
Registra ogni movimento di denaro fisico: entrate (incassi del bar/ristorante) e uscite (fornitori pagati cash, spese varie). Ogni riga ha data, causale, importo e segno contabile.
- DARE = Ricavi Lordi totali (PagatoContanti + PagatoElettronico) — IVA inclusa
- AVERE = Pagato Elettronico (POS/carta) → denaro che fisicamente uscirà verso la banca
- SALDO CASSA = DARE - AVERE = solo contante fisico rimasto in cassa

**Cosa popola a sua volta:**
- → **Bilancio** (sezione Ricavi, voce corrispettivi)
- → **Conto Economico** (ricavi operativi, base del Volume d'Affari)
- → **Coerenza POS/Corrispettivi**: isola i pagamenti con carta/POS dall'importo totale per confrontarli con la banca

**Cosa aspetta per chiudersi:**
1. **Chiusura Fisarmonica del POS** (inserita manualmente la sera): confronta se il totale del file XML corrispettivi coincide con la chiusura reale del POS → se c'è una differenza, significa che qualcuno ha premuto il tasto sbagliato o c'è un errore da recuperare il giorno dopo.
2. **Estratto Conto Bancario** (via riconciliazione): l'importo dei pagamenti elettronici (POS carta) registrati in prima nota cassa deve corrispondere all'accredito che arriva sul conto bancario solitamente il giorno lavorativo successivo. Se non coincide, la riconciliazione segnala l'anomalia.

**Obiettivo finale:** evitare sanzioni per corrispettivi non dichiarati e garantire che **POS fisico = XML = accredito banca**.

---

## 🏦 PRIMA NOTA BANCA

**Da dove arrivano i dati:**
I dati arrivano da tre fonti:
1. **Estratto Conto bancario** (PDF/CSV importato dalla pagina Import Documenti oppure scaricato automaticamente da Gmail) — il sistema lo legge riga per riga, riconosce ogni movimento.
2. **Riconciliazione automatica** che abbina i movimenti bancari alle fatture già registrate nel Ciclo Passivo.
3. **Inserimento manuale** per operazioni non abbinabili automaticamente (es. commissioni bancarie, interessi, operazioni atipiche).

**Cosa fa:**
Tiene il libro mastro di tutti i movimenti sul conto corrente bancario: incassi da clienti, pagamenti a fornitori, bonifici stipendi, rate mutui, F24, commissioni banca. Ogni riga è classificata con causale contabile. Calcola il saldo progressivo giornaliero.
> Le commissioni bancarie fisse (es. €1 per operazione) sono movimenti validi e vengono incluse — non scartate.

**Cosa popola a sua volta:**
- → **Bilancio** (sezione Attivo: saldo cassa in banca — Disponibilità Liquide)
- → **Riconciliazione Fornitori**: quando entra un pagamento a fornitore, aggiorna lo stato della fattura corrispondente da "Da pagare" a "Pagata"
- → **Saldo Banca nel ContabilitaHub** (KPI principale della dashboard contabilità)
- → **Verifica Coerenza POS**: gli accrediti POS confermano o smentiscono quanto registrato in prima nota cassa

**Cosa aspetta per chiudersi:**
1. **Fatture Ricevute**: per ogni uscita bancaria, cerca la fattura corrispondente e la "chiude" (segna pagamento). Se non trova corrispondenza, il movimento rimane "non riconciliato" in attesa di abbinamento manuale.
2. **Prima Nota Cassa (accrediti POS)**: aspetta che l'accredito POS in banca coincida con il totale pagamenti carta di prima nota cassa.
3. **F24 pagati**: ogni uscita fiscale in banca deve trovare un F24 registrato nel modulo Fisco — se non c'è, viene segnalato come uscita non classificata.

---

## 💼 PRIMA NOTA SALARI

**Da dove arrivano i dati:**
- **PDF Cedolini** elaborati mensilmente dal consulente del lavoro (caricati da Import Documenti). Contengono: retribuzione lorda, netta, contributi INPS a carico azienda, IRPEF trattenuta, TFR maturato.
- Dati presenze dal modulo HR (se il cedolino è calcolato internamente).

**Cosa fa:**
Registra il COSTO TOTALE DEL PERSONALE come uscita contabile mensile (non solo lo stipendio netto, ma anche i contributi a carico azienda). Separa: (1) netto da pagare al dipendente tramite bonifico, (2) contributi INPS/INAIL da versare con F24, (3) quota TFR da accantonare.

**Cosa popola a sua volta:**
- → **Bilancio** (voce Costo del Lavoro)
- → **F24 Contributi** (versamenti INPS/INAIL/IRPEF da fare entro il 16 del mese successivo)
- → **Prima Nota Banca** (bonifici stipendi attesi in uscita)

**Cosa aspetta per chiudersi:**
1. **Estratto Conto Bancario**: conferma che ogni bonifico stipendio sia uscito e l'importo corrisponda al netto del cedolino.
2. **Ricevute F24 Contributi**: il versamento entro il 16 del mese successivo deve essere riconciliato sull'estratto conto.

---

## 🧾 CORRISPETTIVI RT

**Da dove arrivano i dati:**
File XML dal Registratore Telematico — caricamento manuale da Import Documenti (generato automaticamente dal RT ogni giorno e trasmesso all'AdE).

**Cosa fa:**
Legge ogni giornata lavorativa con gli importi suddivisi per aliquota IVA. Estrae PagatoContanti e PagatoElettronico (POS). Mostra dettaglio giornaliero e mensile con confronto annuale. Calcola l'IVA a debito trimestrale.

**Cosa popola a sua volta:**
- → **Prima Nota Cassa** (DARE Ricavi + AVERE POS)
- → **Fisco / IVA** (IVA a Debito trimestrale)
- → **Bilancio** (Volume d'Affari — Ricavi operativi)

**Cosa aspetta per chiudersi:**
1. Chiusura manuale POS sera — verifica quadratura POS fisico vs XML.
2. Accredito POS su estratto conto — verifica che l'importo POS XML arrivi davvero in banca.

---

## 📥 FATTURE RICEVUTE (Ciclo Passivo)

**Da dove arrivano i dati:**
File XML Fattura Elettronica SDI — caricamento manuale da Import Documenti oppure download automatico da email (quando l'integrazione Gmail è attiva).

**Cosa fa:**
Legge l'XML SDI ed estrae: fornitore (P.IVA + ragione sociale), data, imponibile, IVA, totale, scadenza pagamento. Abbina automaticamente al fornitore in anagrafica o ne crea uno nuovo. Categorizza la spesa in base allo storico.

**Cosa popola a sua volta:**
- → **Fornitori** (storico fatture per fornitore)
- → **Scadenze** (nuova scadenza di pagamento)
- → **Prima Nota Banca** (uscita attesa se SEPA/Bonifico)
- → **Cespiti** (se bene strumentale ammortizzabile)
- → **Fisco / IVA** (IVA a Credito detraibile)

**Cosa aspetta per chiudersi:**
La fattura rimane "Da pagare" finché l'uscita bancaria corrispondente non viene riconciliata → diventa "Pagata" e viene rimossa dallo Scadenzario.

---

## 🏭 FORNITORI

**Da dove arrivano i dati:**
Estratti automaticamente dalle fatture XML al primo caricamento + inserimento/modifica manuale operatore (metodo pagamento, categoria, note).

**Cosa fa:**
Raccoglie tutto lo storico acquisti in una scheda unica per fornitore. Mostra fatture totali, scadenze aperte, metodo di pagamento preferito.

**Cosa popola a sua volta:**
- → **Ciclo Passivo** (precompila categoria e metodo pagamento sulle nuove fatture)
- → **Prima Nota Banca** (automatismo pagamento SEPA per i fornitori con metodo SEPA/Bonifico)

---

## 🔗 RICONCILIAZIONE

**Da dove arrivano i dati:**
Movimenti Prima Nota Banca (dopo import CSV) + documenti da abbinare: fatture, POS attesi, F24, stipendi.

**Cosa fa:**
Confronta ogni movimento bancario con i documenti aperti cercando corrispondenze per importo, data e causale. Abbina automaticamente quando certo, propone opzioni quando ambiguo. Gestisce assegni e bonifici SEPA.

**Cosa popola a sua volta:**
- → **Fatture Fornitori** → stato "Pagata"
- → **Prima Nota Cassa** → conferma POS ricevuto dalla banca
- → **F24** → stato "Versato"

**Cosa aspetta per chiudersi:**
Il mese si considera "chiuso contabilmente" solo quando tutti i movimenti bancari sono stati riconciliati.

---

## 🏛️ FISCO & IVA

**Da dove arrivano i dati:**
- IVA a Debito dai Corrispettivi (automatico)
- IVA a Credito dalle Fatture Ricevute (automatico)
- Contributi IRPEF/INPS da Cedolini (automatico)

**Cosa fa:**
Calcola liquidazione IVA trimestrale (IVA Debito - IVA Credito). Genera modelli F24 con codici tributo corretti. Mantiene il calendario scadenze fiscali.

**Cosa popola a sua volta:**
- → **Scadenze** (adempimenti tributari)
- → **Prima Nota Banca** (uscita F24 attesa)

**Cosa aspetta per chiudersi:**
Pagamento F24 riconciliato sull'estratto conto entro la data di scadenza.

---

## ⚖️ BILANCIO & ANALISI

**Da dove arrivano i dati:**
Prima Nota Cassa (ricavi), Prima Nota Banca (liquidità), Fatture Fornitori (costi), Prima Nota Salari (costo personale), Cespiti (ammortamenti).

**Cosa fa:**
Calcola Conto Economico (Ricavi - Costi = Utile/Perdita) e Stato Patrimoniale (Attivo vs Passivo + Patrimonio Netto). Mostra Budget Previsionale vs Reale.

**Cosa popola a sua volta:**
- → **Commercialista** (dati per dichiarazione dei redditi)
- → **Chiusura Esercizio** (saldi portati all'anno successivo)

**Cosa aspetta per chiudersi:**
Chiusura di tutti i mesi contabili + approvazione commercialista.

---

## 🏗️ CESPITI & AMMORTAMENTI

**Da dove arrivano i dati:**
Fatture acquisto beni strumentali — identificate automaticamente dalla funzione "Scansiona Fatture" nel Ciclo Passivo.

**Cosa fa:**
Registra ogni bene con costo, data acquisto, aliquota ammortamento. Calcola quote annuali automaticamente.

**Cosa popola a sua volta:**
- → **Bilancio** (Immobilizzazioni in Attivo + Quote Ammortamento in Costi)

---

## 👥 DIPENDENTI & HR

**Da dove arrivano i dati:**
Anagrafica manuale + timbrature/presenze (manuale o import da badge).

**Cosa fa:**
Gestisce stato dipendenti (in carico/non), presenze, ferie, permessi. Flag "In carico" indica attività corrente.

**Cosa popola a sua volta:**
- → **Cedolini** (dati presenze per calcolo busta paga)
- → **Prima Nota Salari** (lista dipendenti attivi del mese)

---

## 💰 CEDOLINI & PAGHE

**Da dove arrivano i dati:**
PDF Cedolini dal consulente del lavoro (Import Documenti) + dati presenze da HR.

**Cosa fa:**
Archivia cedolini per tutti i dipendenti (anche ex-dipendenti). Mostra lorda, netta, contributi, TFR. Calcola TFR accumulato.

**Cosa popola a sua volta:**
- → **Prima Nota Salari** (costo totale mensile)
- → **F24 Contributi** (IRPEF + contributi da versare)

---

## 📅 SCADENZARIO

**Da dove arrivano i dati:**
Fatture non pagate (automatico), modelli F24 (automatico), scadenze contrattuali (manuale).

**Cosa fa:**
Mostra tutte le scadenze in ordine cronologico con importo e tipo. Evidenzia in rosso le scadenze critiche.

**Cosa aspetta per chiudersi:**
Ogni scadenza si chiude solo quando il pagamento viene riconciliato sull'estratto conto → garantisce che "chiuso" = "davvero pagato".

---

## 📤 IMPORT DOCUMENTI

**Gateway di ingresso** per tutti i dati: XML fatture → Ciclo Passivo, XML corrispettivi → Prima Nota Cassa, CSV banca → Prima Nota Banca, PDF cedolini → Paghe. Con anteprima dati prima della conferma per evitare importazioni errate.

---

## 🔧 STRUMENTI & COMMERCIALISTA

**Pacchetto Commercialista**: aggrega tutti i dati del periodo in un file Excel/ZIP per il consulente fiscale. Valido solo dopo la chiusura di tutti i mesi contabili.

---

## Stack Tecnologico

### Backend
| Tecnologia | Descrizione |
|---|---|
| FastAPI | Web framework Python asincrono |
| Pydantic | Validazione dati e modelli |
| Motor | Driver MongoDB asincrono |
| MongoDB Atlas | Database NoSQL cloud |
| Python IMAP | Integrazione email Gmail per fatture |
| xml.etree | Parser fatture XML SDI e RT |
| Uvicorn | ASGI server produzione |

### Frontend
| Tecnologia | Descrizione |
|---|---|
| React 19 | UI library |
| React Router v7 | Routing SPA |
| Vite | Build tool ultra-veloce |
| Shadcn/UI | Componenti UI |
| Tailwind CSS | Styling utility-first |
| Recharts | Grafici e KPI |
| Mermaid.js | Diagrammi di flusso interattivi |
| Axios | HTTP client |
| Lucide React | Icone |

### Database — Collezioni MongoDB principali
| Collezione | Contenuto |
|---|---|
| estratto_conto_movimenti | Movimenti CSV Banco BPM (7.800+ record) |
| prima_nota_cassa | Registro cassa da XML corrispettivi |
| corrispettivi | Incassi giornalieri RT (1.051 record) |
| invoices | Fatture fornitori ricevute (74 record) |
| dipendenti | Anagrafica personale (34 dipendenti) |
| cedolini | Buste paga archivio (841 record) |
| cespiti | Beni strumentali con ammortamento (21 cespiti) |
| mittenti | Lista mittenti email autorizzati |

---
*Documento generato automaticamente dal Gestionale Ceraldi ERP — Revisiona, correggi e rimanda per aggiornare la pagina /mappa-gestionale*
