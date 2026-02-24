## Aggiornamento V8 - 2026-02-08
- F24 Unificato: nuova pagina con tab Tributi e Riconciliazione
- IVA Unificata: nuova pagina con tab Calcolo e Liquidazione
- Filtro anno aggiunto a endpoint F24 riconciliazione
- Auth middleware: aggiunti path pubblici per setup e F24
- Aggiornate 17 pagine frontend

## Aggiornamento V7 - 2026-02-08
- Nuova pagina Bilancio di Verifica
- Nuova pagina Partitario Clienti/Fornitori
- Nuova pagina Budget Previsionale
- Nuovo router contabilita_gestionale.py

## Aggiornamento V6 - 2026-02-08
- Autenticazione JWT obbligatoria attivata
- Redirect automatico a /login su 401
- Filtro anno per endpoint F24 pubblici
- Emoji 🚪 aggiunta al pulsante Esci

## Aggiornamento V5 - 2026-02-08
- Patch V5 applicata
- Aggiunta pagina Login completa
- Aggiunto pulsante Logout nella sidebar
- Endpoint /api/auth/setup per setup admin iniziale
- Strategia multi-livello per riconciliazione verbali-driver

# REGOLE CONTABILI ITALIANE - Sistema ERP Azienda in Cloud
# Ultimo aggiornamento: 8 Febbraio 2026 (post Salari V2 + Notifiche F24 V4)

## 1. STRUTTURA DEL DATABASE

### 1.1 Corrispettivi (collezione: `corrispettivi`)
**Cosa sono:** Scontrini e ricevute fiscali emessi per vendite al pubblico.

| Campo | Descrizione |
|-------|-------------|
| `totale` | Importo lordo (IVA inclusa) |
| `totale_imponibile` | Importo netto (base imponibile) |
| `totale_iva` | IVA calcolata |
| `data` | Data emissione scontrino |
| `partita_iva` | P.IVA dell'azienda (04523831214) |

**REGOLA FONDAMENTALE:** I corrispettivi sono l'UNICA fonte di RICAVI.

### 1.2 Fatture Ricevute (collezione: `invoices`)
**Cosa sono:** Fatture PASSIVE ricevute dai fornitori per acquisti.

**CLASSIFICAZIONE AUTOMATICA:**
Il sistema classifica automaticamente le fatture in base al fornitore:
- Enel, Edison, A2A → Energia (B7)
- TIM, Vodafone, Fastweb → Telefonia (B7, ded. 80%, IVA 50%)
- ARVAL, Leasys, ALD → Noleggio Auto (B8, ded. 20%, max €3.615,20)
- Benzinai, Q8, Esso → Carburante Auto (ded. 20%, IVA 40%)
- Corrieri, BRT, DHL → Trasporti (B7)
- Assicurazioni → Assicurazioni (B7, IVA esente)

### 1.3 Cedolini (collezione: `cedolini`)
**Cosa sono:** Buste paga dipendenti.

| Campo | Descrizione |
|-------|-------------|
| `lordo` | Retribuzione lorda |
| `netto` | Retribuzione netta |
| `inps_azienda` | Contributi INPS carico azienda |
| `tfr` | Accantonamento TFR |
| `costo_azienda` | Costo totale per l'azienda |

---

## 2. CONTO ECONOMICO DETTAGLIATO (Art. 2425 c.c.)

### A) VALORE DELLA PRODUZIONE
| Voce | Fonte | Deducibilità | IVA |
|------|-------|--------------|-----|
| A1 - Ricavi vendite | corrispettivi | 100% | Da versare |

### B) COSTI DELLA PRODUZIONE

| Voce | Fonte | Deducibilità | IVA Detraibile |
|------|-------|--------------|----------------|
| B6 - Materie prime/merci | invoices (default) | 100% | 100% |
| B7 - Energia elettrica/gas | invoices (Enel...) | 100% | 100% |
| B7 - Acqua | invoices (ABC...) | 100% | 100% |
| **B7 - Telefonia** | invoices (TIM...) | **80%** | **50%** |
| B7 - Consulenze | invoices (Studio...) | 100% | 100% |
| B7 - Manutenzioni | invoices | 100% (limite 5%) | 100% |
| B7 - Assicurazioni | invoices | 100% | Esente |
| B7 - Trasporti | invoices (BRT...) | 100% | 100% |
| B7 - Pubblicità | invoices | 100% | 100% |
| **B7 - Carburante auto** | invoices | **20%** | **40%** |
| **B8 - Noleggio auto** | invoices (ARVAL...) | **20% su max €3.615** | **40%** |
| B8 - Affitti immobili | invoices | 100% | Spesso esente |
| B8 - Leasing | invoices | Varia | 100% |
| B9a - Salari e stipendi | cedolini (lordo) | 100% | N/A |
| B9b - Oneri sociali | cedolini (inps_azienda) | 100% | N/A |
| B9c - TFR | cedolini (tfr) | 100% | N/A |
| B14 - Oneri diversi | invoices (altro) | 100% | 100% |

### C) PROVENTI E ONERI FINANZIARI

| Voce | Deducibilità | Note |
|------|--------------|------|
| C17 - Interessi passivi mutui | Limite ROL 30% | Art. 96 TUIR |
| C17 - Commissioni bancarie | 100% | IVA esente |

---

## 3. REGOLE FISCALI SPECIFICHE

### 3.1 AUTO AZIENDALI (Art. 164 TUIR)

| Costo | Deducibilità | IVA Detraibile |
|-------|--------------|----------------|
| Noleggio | 20% su max €3.615,20/anno | 40% |
| Carburante | 20% | 40% |
| Manutenzione | 20% | 40% |
| Assicurazione | 20% | Esente |

**Se auto assegnata a dipendente**: Deducibilità sale al **70%**

### 3.2 TELEFONIA (Art. 102 TUIR)
- **Deducibilità**: 80%
- **IVA Detraibile**: 50%

### 3.3 SPESE DI RAPPRESENTANZA
- **Deducibilità**: Limiti su ricavi
  - Fino a €10M: 1,5% dei ricavi
  - €10M-€50M: 0,6%
  - Oltre €50M: 0,4%
- **IVA**: Indetraibile

### 3.4 INTERESSI PASSIVI (Art. 96 TUIR)
- **Limite ROL**: 30% del Risultato Operativo Lordo
- Eccedenza riportabile agli anni successivi

---

## 4. GESTIONE MAGAZZINO BAR/PASTICCERIA

### 4.1 Categorie Merceologiche
Il sistema gestisce 26 categorie specifiche per bar/pasticceria:

| Codice | Categoria | Centro Costo |
|--------|-----------|--------------|
| BEV-CAF | Caffè e derivati | 1.1_CAFFE_BEVANDE_CALDE |
| BEV-VRS | Vini rossi | 1.2_BEVANDE_FREDDE_ALCOLICI |
| BEV-VBI | Vini bianchi | 1.2_BEVANDE_FREDDE_ALCOLICI |
| BEV-SPU | Spumanti e Prosecco | 1.2_BEVANDE_FREDDE_ALCOLICI |
| BEV-BIR | Birre | 1.2_BEVANDE_FREDDE_ALCOLICI |
| BEV-LIQ | Liquori e distillati | 1.2_BEVANDE_FREDDE_ALCOLICI |
| MP-FAR | Farine e amidi | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-ZUC | Zuccheri e dolcificanti | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-UOV | Uova e ovoprodotti | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-LAT | Latticini | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-CAC | Cacao e cioccolato | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-FRS | Frutta secca | 1.3_MATERIE_PRIME_PASTICCERIA |
| SL-BAS | Basi e paste | 1.4_PRODOTTI_SEMIFINITI |
| SL-CRE | Creme e farciture | 1.4_PRODOTTI_SEMIFINITI |
| GEL-BAS | Basi per gelato | 1.5_GELATI_GRANITE |
| IMB-CAR | Imballaggi carta | 13.1_IMBALLAGGI |
| IMB-PLA | Imballaggi plastica | 13.1_IMBALLAGGI |

### 4.2 Flusso Carico Magazzino
1. **Import Fattura XML** → Sistema legge linee fattura
2. **Classificazione** → Pattern matching su descrizione e fornitore
3. **Estrazione Quantità** → Parsing unità di misura (KG, LT, PZ, CF)
4. **Aggiornamento Stock** → Prezzo medio ponderato
5. **Registrazione Movimento** → Tracciabilità completa

### 4.3 Flusso Scarico Produzione (Distinta Base)
1. **Selezione Ricetta** → Es: "Sfogliatella napoletana"
2. **Porzioni da Produrre** → Es: 100 pezzi
3. **Calcolo Ingredienti** → Proporzionale (fattore = porzioni / base_ricetta)
4. **Verifica Disponibilità** → Check giacenze
5. **Scarico e Lotto** → Genera LOTTO-YYYYMMDDHHMMSS

### 4.4 Collezioni Database
- `warehouse_stocks` - Giacenze con prezzo medio ponderato
- `movimenti_magazzino` - Log carico/scarico
- `lotti_produzione` - Registro lotti con ingredienti usati
- `ricette` - Distinte base con ingredienti e procedimento

---

## 5. ENDPOINT API

| Endpoint | Descrizione |
|----------|-------------|
| `/api/bilancio/conto-economico` | CE semplificato |
| `/api/bilancio/conto-economico-dettagliato` | CE con tutte le voci |
| `/api/bilancio/stato-patrimoniale` | Stato Patrimoniale |
| `/api/liquidazione-iva/calcola/{anno}/{mese}` | Liquidazione IVA |
| `/api/learning-machine/riclassifica-fatture` | Classifica automatica CDC |
| `/api/learning-machine/riepilogo-centri-costo/{anno}` | Riepilogo fiscale |
| `/api/magazzino/carico-da-fattura/{id}` | Carico da XML |
| `/api/magazzino/scarico-produzione` | Scarico per lotto |
| `/api/magazzino/giacenze` | Situazione stock |

---

*Documento aggiornato: 22 Gennaio 2026 (Sessione 12)*
*Sistema: NON multi-utente*
*P.IVA Azienda: 04523831214*
