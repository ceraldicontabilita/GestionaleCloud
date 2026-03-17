# Prima Nota Cassa — Logica Operativa Completa

**Versione:** 2.0 | **Data:** 17 Marzo 2026  
**Applicazione:** Ceraldi Group ERP

---

## 1. Fonte dei Dati: Corrispettivi Telematici (XML)

Ogni giorno il Registratore Telematico (RT) trasmette all'Agenzia delle Entrate un file XML con i corrispettivi giornalieri.

### Struttura XML (file `XXXXXXXX_XXXXXXXX.xml`)

```xml
<n1:DatiCorrispettivi xmlns:n1="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/corrispettivi/v1.0">
  <Intestazione>
    <PeriodoImposta>2026</PeriodoImposta>
    <DataOraRilevazione>2026-01-08</DataOraRilevazione>  ← DATA
  </Intestazione>
  <DatiRT>
    <Riepilogo>
      <AliquotaIVA>10.00</AliquotaIVA>
      <Ammontare>1910.73</Ammontare>       ← BASE IMPONIBILE
      <Imposta>191.07</Imposta>            ← IVA (10%)
      <ImportoParziale>1910.73</ImportoParziale>
    </Riepilogo>
    <Riepilogo>
      <AliquotaIVA>22.00</AliquotaIVA>
      <Ammontare>0.00</Ammontare>
    </Riepilogo>
    <Totali>
      <PagatoContanti>1125.20</PagatoContanti>    ← CONTANTI RIMASTI IN CASSA
      <PagatoElettronico>976.60</PagatoElettronico> ← VA IN BANCA (POS/Carte)
    </Totali>
  </DatiRT>
</n1:DatiCorrispettivi>
```

### Calcolo Totale Giornata
```
Totale giornata = PagatoContanti + PagatoElettronico
                = 1125.20 + 976.60 = 2101.80 (IVA inclusa)

Base imponibile = somma di tutti Ammontare = 1910.73
IVA             = somma di tutte Imposta   = 191.07
Check:          = 1910.73 + 191.07 = 2101.80 ✓
```

---

## 2. Logica Prima Nota Cassa (Definitiva)

### Regola Fondamentale

| Voce | Campo XML | Campo DB | Tipo Movimento |
|------|-----------|----------|----------------|
| **DARE** | `PagatoContanti + PagatoElettronico` | `corrispettivi.totale` | Entrata |
| **AVERE** | `PagatoElettronico` | `corrispettivi.pagato_elettronico` | Uscita |

### Perché IVA Inclusa in DARE?

**I ricavi sono CON IVA.** Il totale del corrispettivo (DARE) rappresenta:
- Il denaro FISICAMENTE ricevuto dal cliente
- Include l'IVA che poi dovrà essere versata all'Erario

### Schema di Registrazione (per ogni corrispettivo)

```
DARE  (entrata):  totale = contanti + POS        = €2.101,80
AVERE (uscita):   pagato_elettronico (POS→Banca)  = €  976,60
                  ─────────────────────────────────────────────
SALDO CASSA:      contanti rimasti in cassa        = €1.125,20
```

### Verifica del Saldo
```
Saldo cassa = DARE - AVERE
            = totale - pagato_elettronico
            = pagato_contanti  ✓
```

**Il saldo della Prima Nota Cassa deve SEMPRE coincidere con il totale dei `PagatoContanti` dei corrispettivi.**

---

## 3. Database

### Collezioni Coinvolte

| Collezione | Descrizione |
|------------|-------------|
| `corrispettivi` | Dati originali dei corrispettivi telematici |
| `prima_nota_cassa` | Movimenti di Prima Nota generati dai corrispettivi |

### Schema `prima_nota_cassa` (movimenti generati)

#### Riga DARE (Entrata)
```json
{
  "tipo": "entrata",
  "importo": 2101.80,
  "categoria": "Corrispettivi",
  "descrizione": "Corrispettivo 2026-01-08 - RT XXXXXXXX",
  "data": "2026-01-08",
  "source": "rebuild_corrispettivi",
  "dettaglio": {
    "totale_lordo": 2101.80,
    "pagato_contanti": 1125.20,
    "pagato_elettronico": 976.60,
    "totale_imponibile": 1910.73,
    "totale_iva": 191.07
  }
}
```

#### Riga AVERE (Uscita POS)
```json
{
  "tipo": "uscita",
  "importo": 976.60,
  "categoria": "Incasso POS/Elettronico",
  "descrizione": "Incasso POS 2026-01-08 → Banca (RT XXXXXXXX)",
  "data": "2026-01-08",
  "source": "rebuild_corrispettivi",
  "dettaglio": {
    "saldo_cassa_atteso": 1125.20,
    "totale_lordo_corrispettivo": 2101.80
  }
}
```

---

## 4. API Endpoint

### Ricostruire Prima Nota Cassa

```
POST /api/prima-nota/cassa/rebuild-da-corrispettivi?anno=2025
```

**Funzionamento:**
1. Cancella TUTTI i movimenti dell'anno specificato dalla `prima_nota_cassa`
2. Legge tutti i corrispettivi dell'anno dalla collezione `corrispettivi`
3. Per ogni corrispettivo inserisce:
   - 1 riga DARE: importo = `totale` (con IVA)
   - 1 riga AVERE: importo = `pagato_elettronico` (se > 0)

**Risposta esempio:**
```json
{
  "message": "Prima Nota Cassa ricostruita correttamente",
  "anno": 2025,
  "corrispettivi_processati": 346,
  "righe_inserite": 686,
  "totale_dare": 922090.27,
  "totale_avere": 563033.68,
  "saldo_cassa": 359056.59
}
```

**Senza anno** (ricostruisce TUTTI gli anni):
```
POST /api/prima-nota/cassa/rebuild-da-corrispettivi
```

---

## 5. Dati Riepilogo per Anno

### Anno 2024
| Voce | Importo |
|------|---------|
| DARE (Ricavi lordi con IVA) | € 825.152,16 |
| AVERE (POS → Banca) | € 457.893,56 |
| **SALDO CASSA** | **€ 367.258,60** |

### Anno 2025
| Voce | Importo |
|------|---------|
| DARE (Ricavi lordi con IVA) | € 922.090,27 |
| AVERE (POS → Banca) | € 563.033,68 |
| **SALDO CASSA** | **€ 359.056,59** |

### Anno 2026 (fino al 16/03)
| Voce | Importo |
|------|---------|
| DARE (Ricavi lordi con IVA) | € 36.564,51 |
| AVERE (POS → Banca) | € 22.203,34 |
| **SALDO CASSA** | **€ 14.361,17** |

---

## 6. Ciclo Operativo

```
1. Il cliente paga al bancone
      ↓
2. Il Registratore Telematico registra il pagamento
      ↓
3. Ogni giorno il RT trasmette il file XML all'AdE
      ↓
4. Il file XML viene caricato nell'ERP (sezione Corrispettivi)
      ↓
5. L'ERP calcola:
   - DARE = totale (contanti + POS)  → Prima Nota Cassa ENTRATA
   - AVERE = POS                     → Prima Nota Cassa USCITA
      ↓
6. Saldo Cassa = DARE - AVERE = Contanti fisici in cassa
      ↓
7. I pagamenti POS arrivano in Banca (estratto conto)
   e vengono registrati nella Prima Nota BANCA (sezione separata)
```

---

## 7. Prima Nota Banca (sezione separata)

La Prima Nota Banca usa l'**Estratto Conto CSV** del Banco BPM.

| Voce | Logica |
|------|--------|
| DARE | Tutti gli accrediti sul conto (POS, bonifici, depositi) |
| AVERE | Tutti i pagamenti (fornitori, commissioni, utenze) |

**I ricavi reali** (corrispettivi) sono nella sezione CASSA, non in BANCA.  
Gli accrediti bancari includono anche movimenti interni (finanziamenti, giro conto).

**Forza aggiornamento estratto conto:**
```
POST /api/estratto-conto-movimenti/force-reimport  [multipart CSV]
```
Cancella gli anni del CSV e reinserisce tutto senza deduplicazione (corretto per commissioni €1 ripetute).

---

## 8. Errori Comuni e Soluzioni

| Problema | Causa | Soluzione |
|----------|-------|-----------|
| Saldo cassa negativo | Vecchi record da excel_import | Ricostruire con `/rebuild-da-corrispettivi` |
| DARE ≠ pagato_contanti + pagato_elettronico | Campo `totale` inconsistente | Verificare i corrispettivi XML originali |
| Commissioni €1 duplicate nell'estratto conto | Deduplicazione troppo aggressiva | Usare `force-reimport` per l'estratto conto |

---

*Documento generato automaticamente dal sistema ERP Ceraldi Group*
