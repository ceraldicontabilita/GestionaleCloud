# 🧠 Intelligenza Espansa — Ceraldi ERP
## Cosa può diventare questo gestionale avendo accesso a tutti i suoi dati

---

> Questo documento descrive la visione completa di ciò che il sistema può fare
> sfruttando i dati che già possiede, l'AI integrata (OpenClaw/Claude), 
> e gli agenti già esistenti (FiscaleSentinella, HRGuardiano, LearningCervello).
> Non è fantascienza: ogni funzionalità descritta si aggancia a codice già scritto.

---

## IL PRINCIPIO BASE

Il gestionale già sa moltissimo:
- Chi sono i dipendenti, quanto guadagnano, quando sono malati
- Quali ingredienti compri, da chi, a quanto, ogni quanto
- Quanto incassi ogni giorno, mese, anno
- Quali tasse paghi, quando, con quale codice tributo
- Quali auto hai, quante multe prendono, quanto costano
- Come si pagano i fornitori, con quale ritardo, con quale metodo

**Con questi dati + una ricerca in tempo reale su internet + Claude AI, il sistema può trasformarsi da "registro contabile" a "consulente intelligente che conosce la tua azienda".**

---

## 🍕 1. SEZIONE INGREDIENTI INTELLIGENTE — dal dato contabile alla scienza

### Cosa già abbiamo
Dal magazzino: lista ingredienti con quantità, costo, fornitore, frequenza di acquisto.
Dalle fatture: prezzo pagato per kg/litro di ogni ingrediente nel tempo.
Dalle ricette: combinazioni di ingredienti nei prodotti.

### Cosa può diventare

**Cliccando su "Farina 00" nel magazzino:**

**Tab "Acquisti"** (già esiste — dati contabili)
- Storico prezzi pagati per kg, per fornitore, nel tempo
- Fornitore più conveniente, trend di prezzo, previsione prossimo ordine

**Tab "Nutrizione"** (nuovo — ricerca AI)
L'agente interroga un database nutrizionale (USDA FoodData, INRAN) e porta:
- Calorie per 100g, macronutrienti, micronutrienti
- Indice glicemico, contenuto proteico, fibre
- Allergeni presenti (già parzialmente in HACCP)

**Tab "Reazioni chimiche"** (nuovo — AI research)
L'agente chiede a Claude: *"Cosa succede chimicamente quando la farina 00 viene mescolata con lievito di birra a 220°C?"*
Risposta strutturata:
- Reazione di Maillard (imbrunimento)
- Gelatinizzazione dell'amido
- Sviluppo glutine
- Effetto su prodotto finale (croccantezza, colore, shelf-life)

**Tab "Reazioni con altri tuoi ingredienti"** (nuovo — AI + dati tuoi)
Il sistema prende i tuoi ingredienti reali dalle ricette e genera:
- "Se usi questa farina con la tua ricetta di suppli: attenzione al contenuto di sale — la combinazione con il tuo prosciutto (1.8g/100g sodio) porta il prodotto finale sopra i 2.5g/100g raccomandati"
- "La farina 00 + tuo lievito madre a 4h di lievitazione → indice glicemico cala del 30%"

**Tab "Sostenibilità"** (nuovo — AI research)
- Carbon footprint per kg di questo ingrediente
- Stagionalità: quando conviene comprarlo (prezzo + qualità)
- Confronto fornitori locali vs lontani

**Tab "Normativa"** (nuovo — AI research)
- Etichettatura obbligatoria per allergeni
- Limiti di utilizzo (additivi, conservanti se applicabile)
- Aggiornamenti normativi recenti

### Come si implementa
Un nuovo agente `IngredienteResearcher` che:
1. Prende il nome dell'ingrediente dal magazzino
2. Chiama Claude via API con: nome ingrediente + contesto (prodotti dove viene usato, quantità, fornitori)
3. Restituisce scheda strutturata in JSON
4. Salva in `ingredienti_schede` — non ricerca ogni volta, aggiorna ogni 30 giorni
5. La scheda è visibile come tab aggiuntivo nella pagina Magazzino

---

## 👥 2. HR INTELLIGENTE — dai cedolini alla consulenza sul lavoro

### Cosa già abbiamo
Dipendenti, cedolini, presenze, giustificativi, TFR, contratti.
L'agente HRGuardiano già monitora dimissioni e scadenze contratti.

### Cosa può diventare

**Sezione "Vantaggi Fiscali Dipendenti"** (nuovo)

L'agente ogni settimana interroga:
- Normativa vigente sui fringe benefit (soglia 2024: €1.000 o €2.000 con figli)
- Welfare aziendale deducibile (buoni pasto, rimborsi trasporto, assicurazioni)
- Agevolazioni per nuove assunzioni (contratti di apprendistato, Garanzia Giovani, Sud)
- Crediti d'imposta per formazione 4.0

Poi incrocia con i tuoi dati reali:
- "Pocci ha 2 figli → puoi dargli fringe benefit fino a €2.000 esentasse"
- "Hai 3 dipendenti under 30 → potresti accedere all'esonero contributivo del 100% per 36 mesi se li converti a tempo indeterminato"
- "Il costo del buono pasto da €8 è deducibile al 100% per te, non tassato per il dipendente → risparmio effettivo per Pocci: €3.200/anno"

**Sezione "News HR"** (nuovo — ricerca web)

L'agente ogni lunedì mattina:
1. Cerca su INPS.it, MinisteroLavoro.gov, IPSOA, Il Sole 24 Ore Lavoro
2. Filtra le notizie rilevanti per il tuo profilo (settore alimentare, Napoli, dimensione azienda)
3. Le traduce in impatto pratico sul tuo gestionale
4. Le mostra come alert in Agenti AI

Esempio di output:
> **📰 Novità INPS — 15 aprile 2026**
> Il tasso di rivalutazione TFR per il 1° trimestre 2026 è 0,8%.
> **Impatto su di te:** il TFR dei tuoi 12 dipendenti va rivalutato.
> Stima importo rivalutazione: €340 complessivi.
> **Azione:** Vai in TFR → Rivalutazione trimestrale → Conferma.

**Sezione "Costo reale per dipendente"** (nuovo — calcolo da cedolini)

Per ogni dipendente, scheda con:
- Costo annuo totale (netto + INPS azienda + INAIL + TFR + eventuali fringe)
- Confronto con produttività (corrispettivi per reparto / numero dipendenti reparto)
- "Pocci costa €28.400/anno → genera €142.000 di corrispettivi in Rosticceria → ROI 5x"

---

## 🔮 3. AGENTE "ANTICIPATORE" — il gestionale che vede il futuro

### Cosa già abbiamo
3 anni di dati: corrispettivi giornalieri, fatture, cedolini, F24, stagionalità.

### Cosa può diventare

**Previsione incassi prossimi 30 giorni**
Il sistema analizza:
- Stesso periodo degli anni precedenti (stagionalità)
- Trend corrente (ultime 4 settimane)
- Giorni festivi, eventi locali (Pasqua, estate, Natale)
- Fattori anomali già rilevati (es. lavori in strada)

Output: "Questa settimana prevedo €18.400 di corrispettivi (±8%). Mese: €72.000."

**Previsione uscite obbligatorie**
Già noti per contratto o abitudine:
- F24 del 16: importo stimato da cedolini del mese
- Canoni noleggio auto: importo fisso, data fissa
- Rate mutui: importo fisso, data fissa
- Fornitori con pagamento a 30gg: fatture in scadenza

Output: "Uscite previste prossimi 15 giorni: €34.200. Saldo banca attuale: €41.800. Margine: €7.600. ⚠️ Attenzione."

**Alert "Rischio liquidità"**
Se il margine scende sotto una soglia configurabile → alert urgente 5 giorni prima.

---

## 📊 4. LEARNING MACHINE 2.0 — da categorizzatore a consulente

### Cosa già esiste
LearningCervello registra pattern in `agenti_apprendimenti`, suggerisce automaticamente.

### Cosa può diventare

**Suggerimenti proattivi basati sui tuoi dati:**

*Esempio 1 — Fornitore*
Il sistema nota che Fornitore X ha aumentato i prezzi del 12% negli ultimi 6 mesi.
Suggerimento: "Guarda questi 3 fornitori alternativi per farina 00 nella tua area geografica — prezzi stimati da fonti pubbliche."

*Esempio 2 — Centro di costo*
La Rosticceria sta costando il 18% in più rispetto al trimestre scorso.
Analisi automatica: l'aumento è concentrato su 2 voci — packaging (+23%) e olio di semi (+31%).
Suggerimento: "Valuta cambio fornitore packaging o riduzione grammature."

*Esempio 3 — Fiscale*
Il sistema nota che ogni anno a ottobre arrivi in ritardo sul versamento IVA del 3° trimestre.
Suggerimento a settembre: "Ricordati: IVA 3° trimestre da versare entro 16 novembre. Stima importo: €4.200 (basato sullo stesso periodo 2025)."

*Esempio 4 — HR*
Il sistema nota che Thimira ha 22 giorni di ferie non godute accumulate.
Suggerimento: "Thimira ha ferie prossime alla scadenza (31/12). Pianifica le assenze entro fine anno per evitare il pagamento sostitutivo."

**Come si implementa**
LearningCervello viene esteso con:
- `_analizza_trend_fornitori()` — confronta prezzi stessa categoria ultimi 6 mesi
- `_analizza_centri_costo()` — varianza mese su mese per reparto
- `_anticipa_scadenze_fiscali()` — confronta stesso mese anni precedenti
- `_analizza_ferie_accumulate()` — dipendenti con ferie > soglia
- Ogni analisi produce segnalazioni in `agenti_segnalazioni` con tipo "suggerimento"

---

## 🌐 5. RICERCA WEB INTEGRATA — il gestionale che legge il mondo

### Come funziona tecnicamente
L'agente usa Claude via API (già configurato in OpenClaw) con il tool `web_search`.
Può cercare su internet in tempo reale, filtrare le fonti affidabili, strutturare la risposta.

### Applicazioni concrete

**"Cosa c'è di nuovo per la mia azienda questa settimana?"**
Ogni lunedì mattina, l'agente cerca:
- Normative INPS/INAIL/Agenzia Entrate degli ultimi 7 giorni
- Novità su fringe benefit, welfare, sgravi contributivi
- Aggiornamenti scadenze fiscali (circolari MEF)
- News settore alimentare Napoli/Campania (HACCP, ispezioni, normative igieniche)
- Prezzi materie prime commodities (farina, olio, carne — impatto sui tuoi costi)

Tutto viene sintetizzato in 5 bullet point nella Dashboard.

**"Questo fornitore è affidabile?"**
Prima di pagare un fornitore nuovo, l'agente cerca:
- Visura camerale (già integrata via OpenAPI Imprese)
- Notizie negative recenti (fallimenti, frodi, contenziosi)
- Rating media da fonti pubbliche

**"Qual è il prezzo di mercato di questo ingrediente?"**
L'agente cerca sui listini pubblici (ISMEA, mercati ortofrutticoli, borse merci) il prezzo corrente di quell'ingrediente e lo confronta con quello che stai pagando tu.

---

## 🏗️ 6. ARCHITETTURA — come si costruisce tutto questo

### Nuovo agente: `RicercatoreWeb`
```python
class RicercatoreWeb:
    """
    Agente che usa Claude API con web_search per ricerche contestuali.
    Gira ogni lunedì alle 8:00.
    """
    async def run(self, db):
        await asyncio.gather(
            self._aggiorna_news_hr(db),
            self._aggiorna_news_fiscale(db),
            self._aggiorna_prezzi_ingredienti(db),
            self._controlla_fornitori_nuovi(db),
        )
    
    async def _aggiorna_news_hr(self, db):
        # Chiama Claude con web_search
        # Salva risultati in agenti_news_hr
        # Crea segnalazione se ci sono novità rilevanti
        pass
```

### Nuovo agente: `IngredienteResearcher`
```python
class IngredienteResearcher:
    """
    Per ogni ingrediente in magazzino, crea scheda completa.
    Gira ogni 30 giorni per ingrediente.
    """
    async def ricerca_ingrediente(self, db, nome_ingrediente, contesto_ricette):
        # Chiama Claude con:
        # - nome ingrediente
        # - ricette dove viene usato (dal DB)
        # - altri ingredienti combinati (dal DB)
        # Restituisce scheda strutturata
        # Salva in ingredienti_schede
        pass
```

### Nuovo agente: `Anticipatore`
```python
class Anticipatore:
    """
    Previsioni finanziarie basate su dati storici.
    Gira ogni giorno alle 6:00.
    """
    async def run(self, db):
        await asyncio.gather(
            self._prevedi_incassi_30gg(db),
            self._prevedi_uscite_obbligatorie(db),
            self._controlla_rischio_liquidita(db),
        )
```

### Orchestratore aggiornato
```python
SCHEDULE = {
    "FiscaleSentinella":   600,    # ogni 10 min
    "HRGuardiano":         1800,   # ogni 30 min
    "LearningCervello":    3600,   # ogni ora
    "Anticipatore":        86400,  # ogni giorno (6:00)
    "RicercatoreWeb":      604800, # ogni settimana (lunedì 8:00)
    "IngredienteResearcher": 2592000, # ogni 30 giorni per ingrediente
}
```

---

## 📋 PRIORITÀ DI IMPLEMENTAZIONE

| Agente/Funzione | Impatto | Dipendenze | Priorità |
|---|---|---|---|
| **LearningCervello 2.0** — trend fornitori + suggerimenti | 🔴 Alta | Solo dati interni | P1 |
| **Anticipatore** — previsioni liquidità 30gg | 🔴 Alta | Solo dati interni | P1 |
| **RicercatoreWeb** — news HR + fiscale settimanali | 🟠 Media | Claude API (già attivo) | P2 |
| **HR — Costo reale dipendente** | 🟠 Media | Cedolini + corrispettivi | P2 |
| **HR — Fringe benefit personalizzati** | 🟠 Media | Dipendenti + normativa | P2 |
| **IngredienteResearcher** — scheda molecolare | 🟡 Media | Claude API + magazzino | P3 |
| **Ingredienti — reazioni chimiche** | 🟡 Interessante | Claude API + ricette | P3 |
| **Prezzi di mercato ingredienti** | 🟡 Media | Claude API + web_search | P3 |
| **Fornitore affidabilità real-time** | 🟡 Media | Visure già integrate | P3 |

---

## 🎯 COSA RENDE TUTTO QUESTO UNICO

La differenza tra un gestionale normale e questo sistema è che **il contesto è già dentro**.

Quando il `RicercatoreWeb` cerca "novità fringe benefit 2026", non porta una risposta generica.
Porta: *"La nuova soglia è €2.000. Hai 3 dipendenti con figli (Pocci, Moscato, Carotenuto).
Il massimo vantaggio fiscale per te è €18.000/anno non tassati per loro, e deducibili al 100% per te."*

Quando l'`IngredienteResearcher` studia la farina, non produce una pagina Wikipedia.
Produce: *"Nella tua ricetta di suppli con questo tipo di farina, la combinazione con
il tuo lievito (acquistato da Fornitore X a €3.20/kg) a 4h di lievitazione produce
un indice glicemico 28% più basso rispetto alla lievitazione standard da 1h.
Questo potrebbe essere un punto di differenziazione comunicabile ai clienti."*

Il sistema **sa chi sei, cosa fai, cosa compri, chi lavora per te** —
e usa questa conoscenza per rendere ogni informazione esterna immediatamente utile.

