# Agenti AI — Ceraldi ERP
> Visione e implementazione dell'intelligenza integrata | Aggiornato: Aprile 2026

---

## PRINCIPIO BASE

Il gestionale sa già moltissimo:
- Chi sono i dipendenti, quanto guadagnano, quando sono malati
- Quali ingredienti compri, da chi, a quanto, ogni quanto
- Quanto incassi ogni giorno, mese, anno
- Quali tasse paghi, quando, con quale codice tributo
- Come si pagano i fornitori, con quale ritardo

Con questi dati + Claude AI, il sistema si trasforma da "registro contabile" a "consulente che conosce la tua azienda".

---

## AGENTI ATTIVI (già nel codice)

### FiscaleSentinella (`app/agents/fiscale_sentinella.py`)

**Cosa monitora:**
- Email da Agenzia Entrate e Agenzia Riscossione → classifica: avviso bonario, cartella, rottamazione
- Avvisi bonari (art. 36-bis, 36-ter, 54-bis): confronta con F24 già pagati per vedere se è già saldato
- F24 in scadenza nei prossimi 5 giorni → alert rosso
- Cartelle esattoriali: scadenza 60 giorni, importo, natura del tributo

**Output**: segnalazioni in `agenti_segnalazioni` con tipo `fiscale`, priorità alta/media/bassa

**Trigger**: ogni email di tipo `cartella_esattoriale` o `inps`

### HRGuardiano (`app/agents/hr_guardiano.py`)

**Cosa monitora:**
- Contratti in scadenza nei prossimi 30/60/90 giorni
- Ferie accumulate > 25 giorni → segnalazione "ferie in scadenza"
- Cedolini tredicesima → promemoria rivalutazione TFR
- Stipendi non erogati nei tempi previsti

**Output**: segnalazioni in `agenti_segnalazioni` con tipo `hr`

**Trigger**: import cedolino, scheduler settimanale

### LearningCervello (`app/agents/learning_brain.py`)

**Cosa impara:**
- Pattern descrizioni righe fattura → centro di costo (Rosticceria, Pasticceria, Veicoli, Amministrazione)
- Deducibilità per categoria fornitore (già impostati: TIM→80%, ARVAL→20%, ecc.)
- Metodo pagamento preferito per fornitore

**Output**: `learning_rules` in MongoDB, campo `centro_costo_id` aggiornato sulle fatture

**Trigger**: ogni import fattura (handler learning nel bus eventi)

### Orchestratore (`app/agents/orchestrator.py`)

Coordina gli altri agenti, gestisce le priorità delle segnalazioni, evita duplicati.

### Notifier (`app/agents/notifier.py`)

Invia notifiche via WebSocket alla UI quando ci sono eventi importanti (nuova fattura, scadenza imminente, alert agente).

---

## AGENTI PIANIFICATI (codice parziale o da implementare)

### Anticipatore Liquidità

**Cosa fa:** analizza 3 anni di dati (corrispettivi, fatture, cedolini, F24) e prevede:
- Incassi prossimi 30 giorni (con stagionalità e trend)
- Uscite obbligatorie: canoni noleggio, rate mutui, F24 del 16, stipendi
- Margine di sicurezza: se < soglia → alert "rischio liquidità"

**Algoritmo:**
1. Stagionalità: stesso periodo anni precedenti
2. Trend corrente: ultime 4 settimane
3. Uscite note: importi fissi + scadenze già note
4. Output: previsione ±8%, alert 5 giorni prima del problema

**Status**: pianificato, non ancora implementato

### IngredienteResearcher

**Cosa fa:** arricchisce le schede degli ingredienti con dati da fonti esterne.

**Per ogni ingrediente (ogni 30 giorni):**
- **Tab Nutrizione**: valori nutrizionali da USDA FoodData/INRAN (calorie, macro, allergeni)
- **Tab Chimica**: cosa succede chimicamente in cottura (reazione Maillard, gelatinizzazione amido, ecc.)
- **Tab Confronto prezzi**: prezzo mercato da ISMEA, borse merci
- **Tab Normativa**: allergeni obbligatori, limiti additivi

**Output**: `ingredienti_schede` — JSON con timestamp aggiornamento

**Status**: pianificato, integrazione Claude API in corso

### FornitorePriceWatcher

**Cosa fa:** monitora i prezzi degli ingredienti nelle fatture.

**Trigger:** ogni import fattura con righe alimentari.

**Logica:**
1. Identifica ingrediente dalla descrizione riga (dizionario match)
2. Confronta prezzo pagato con prezzo medio degli ultimi 6 mesi
3. Se aumentato >5% → segnalazione "variazione prezzo ingrediente"
4. Se pagando >15% sopra il mercato → segnalazione con prezzo riferimento ISMEA
5. Aggiorna tutte le ricette che usano quell'ingrediente con il nuovo costo

**Status**: logica parzialmente in `handlers/ricette.py`, non completamente connessa

---

## INTELLIGENZA HR ESPANSA (pianificata)

### Suggerimenti fiscali per dipendenti
L'agente ogni settimana verifica:
- Normativa fringe benefit corrente (soglia €1.000 o €2.000 con figli)
- Welfare aziendale deducibile (buoni pasto, rimborsi trasporto)
- Agevolazioni nuove assunzioni (Garanzia Giovani, Sud, apprendistato)
- Crediti d'imposta formazione 4.0

Poi incrocia con i dati reali dei dipendenti e genera suggerimenti concreti.

### Calcolo costo reale per dipendente
Per ogni dipendente, calcola:
- Costo annuo totale: netto + INPS azienda + INAIL + TFR + fringe benefit
- ROI per reparto: corrispettivi reparto / numero dipendenti reparto

---

## LEARNING MACHINE 2.0 (pianificata)

Estensione di LearningCervello con analisi proattiva:

**`_analizza_trend_fornitori()`**
- Confronta prezzi stessa categoria ultimi 6 mesi
- Se fornitore X aumenta il 12% → suggerisci alternativi

**`_analizza_centri_costo()`**
- Varianza mese su mese per reparto
- Se Rosticceria costa 18% in più → analisi automatica delle voci aumentate

**`_anticipa_scadenze_fiscali()`**
- Confronta stesso mese anni precedenti
- A settembre → reminder IVA 3° trimestre con importo stimato

**`_analizza_ferie_accumulate()`**
- Dipendenti con ferie > soglia entro fine anno
- Alert: "X ha 22 giorni di ferie in scadenza il 31/12"

**Output**: tipo `suggerimento` in `agenti_segnalazioni`

---

## COLLECTION AGENTI

| Collection | Contenuto |
|---|---|
| `agenti_segnalazioni` | Segnalazioni di tutti gli agenti (tipo, priorità, messaggio, data) |
| `agenti_apprendimenti` | Pattern appresi da LearningCervello |
| `learning_rules` | Regole classificazione centri di costo |
| `ingredienti_schede` | Schede nutrizione/chimica (da IngredienteResearcher) |
| `eventi_sistema` | Bus eventi |
| `eventi_log` | Log esecuzione handler |

---

## RICERCA WEB INTEGRATA

L'agente usa Claude API con tool `web_search` per cercare su internet in tempo reale.

**Applicazioni concrete già previste:**
- Normativa HR settimanale (INPS.it, MinisteroLavoro.gov, IPSOA)
- Prezzi ingredienti da ISMEA e borse merci
- Aggiornamenti aliquote e scadenze fiscali
- News rilevanti per settore alimentare a Napoli

**Frequenza**: ricerche HR ogni lunedì mattina, ingredienti ogni 30 giorni per ingrediente, fiscale su trigger (nuova cartella/avviso).

---

*Aggiornato: Aprile 2026*
