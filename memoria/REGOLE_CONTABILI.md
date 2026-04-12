# Regole Contabili Italiane — Ceraldi ERP
> P.IVA: 04523831214 | Regime: Ordinario | Aggiornato: Aprile 2026

---

## 1. FONTI DEI DATI

| Tipo | Collection | Cosa Rappresenta |
|---|---|---|
| Ricavi | `corrispettivi` | Scontrini/ricevute — **UNICA** fonte ricavi |
| Acquisti | `invoices` | Fatture passive ricevute dai fornitori |
| Stipendi | `cedolini` | Buste paga dipendenti |
| Banca | `estratto_conto_movimenti` | Movimenti bancari |
| Cassa | `prima_nota_cassa` | Contanti fisici |

---

## 2. CONTO ECONOMICO (Art. 2425 c.c.)

### A — Valore della Produzione

| Voce | Fonte | Deducibilità |
|---|---|---|
| A1 — Ricavi vendite | `corrispettivi.totale_giornata` | 100% |

### B — Costi della Produzione

| Voce CE | Categoria | Fornitore Tipico | Deducibilità IRES | IVA Detraibile |
|---|---|---|---|---|
| B6 | Materie prime/merci | (generico) | 100% | 100% |
| B7 | Energia elettrica | Enel, Edison, A2A | 100% | 100% |
| B7 | **Telefonia** | TIM, Vodafone | **80%** | **50%** |
| B7 | Consulenze | Studio..., professionisti | 100% | 100% |
| B7 | Trasporti | BRT, DHL, GLS | 100% | 100% |
| B7 | **Carburante** | Q8, Esso, IP, ENI | **20%** | **40%** |
| B8 | **Noleggio auto** | ARVAL, Leasys, ALD | **20% max €3.615/anno** | **40%** |
| B8 | Affitti immobili | Proprietari | 100% | Spesso esente |
| B9a | Salari netti | — | 100% | N/A |
| B9b | Oneri sociali (INPS) | — | 100% | N/A |
| B9c | TFR | — | 100% | N/A |

---

## 3. REGOLE FISCALI SPECIFICHE

### 3.1 Auto Aziendali (Art. 164 TUIR)

| Costo | Deducibilità | IVA |
|---|---|---|
| Noleggio | 20% su max €3.615,20/anno | 40% |
| Carburante | 20% | 40% |
| Manutenzione | 20% | 40% |
| Assicurazione | 20% | Esente |

**Se auto assegnata a dipendente come benefit**: deducibilità sale al **70%**

### 3.2 Telefonia (Art. 102 TUIR)
- Deducibilità costo: **80%**
- IVA detraibile: **50%**

### 3.3 Interessi Passivi (Art. 96 TUIR)
- Limite: **30% del ROL** (Risultato Operativo Lordo)
- Eccedenza riportabile agli anni successivi

### 3.4 TFR (Art. 2120 c.c.)
- Quota mensile: `retribuzione_lorda / 13.5`
- Rivalutazione annua: `1.5% fisso + 75% dell'indice ISTAT`
- Accantonamento: in `tfr_accantonamenti` per dipendente + mese + anno

---

## 4. CALENDARIO FISCALE

| Mese | Giorno | Adempimento |
|---|---|---|
| Ogni mese | 16 | F24 (IRPEF ritenute, INPS, Addizionali) |
| Marzo | 16 | Saldo IVA anno precedente |
| Giugno | 30 | Dichiarazione redditi (IRES/IRAP) |
| Novembre | 30 | Acconto imposte |

---

## 5. LIQUIDAZIONE IVA

```
IVA a debito  = SUM(corrispettivi.totale_iva) per periodo
IVA a credito = SUM(invoices.iva_detraibile) per periodo
Liquidazione  = IVA a debito − IVA a credito
```
- Se positiva → versamento tramite F24 (codice tributo 6001)
- Se negativa → credito da riportare al periodo successivo
- Frequenza: **trimestrale** (settore specifico Ceraldi)

---

## 6. CODICI F24 PRINCIPALI

| Codice | Tributo | Scadenza tipica |
|---|---|---|
| 1001 | IRPEF ritenute dipendenti | 16 del mese successivo |
| 1030 | Addizionale comunale IRPEF | 16 del mese |
| 3802 | Addizionale regionale IRPEF | 16 del mese |
| 6001 | IVA mensile/trimestrale | 16 del mese |
| 6099 | Saldo IVA annuale | 16 marzo |
| 1301 | INPS dipendenti | 16 del mese |
| 1303 | INPS quota azienda | 16 del mese |

---

## 7. METODI DI PAGAMENTO FE (Fatturazione Elettronica)

| Codice | Metodo | Prima Nota |
|---|---|---|
| MP01 | Contanti | `prima_nota_cassa` |
| MP02 | Assegno | `prima_nota_banca` |
| MP05 | Bonifico bancario | `prima_nota_banca` |
| MP08 | Carta di credito | `prima_nota_banca` |
| MP19 | SEPA Credit Transfer | `prima_nota_banca` |

---

## 8. TIPI DOCUMENTO FE

| Codice | Tipo | Direzione Contabile |
|---|---|---|
| TD01 | Fattura ordinaria | Acquisto → uscita cassa/banca |
| TD04 | Nota di credito | Rimborso → entrata |
| TD08 | Nota di debito | Addebito → uscita |
| TD16 | Autofattura (integrazione reverse charge) | Neutro |
| TD24 | Fattura differita | Vendita → entrata |
| TD25 | Fattura differita (varie) | Vendita → entrata |

---

## 9. STRUTTURA CEDOLINO

| Campo | Descrizione | Voce CE |
|---|---|---|
| `lordo` | Retribuzione lorda | B9a |
| `netto` | Retribuzione netta pagata | — |
| `inps_dipendente` | Quota INPS a carico del dipendente | — |
| `inps_azienda` | Contributi INPS a carico azienda | B9b |
| `irpef` | IRPEF trattenuta | — |
| `tfr` | Accantonamento TFR del mese | B9c |
| `costo_azienda` | Totale costo = lordo + inps_azienda + tfr | B9 totale |

---

## 10. MAGAZZINO — CATEGORIE BAR/PASTICCERIA

| Codice | Categoria | Centro Costo |
|---|---|---|
| BEV-CAF | Caffè e derivati | 1.1_CAFFE_BEVANDE_CALDE |
| BEV-VRS | Vini rossi | 1.2_BEVANDE_FREDDE_ALCOLICI |
| MP-FAR | Farine e amidi | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-ZUC | Zuccheri | 1.3_MATERIE_PRIME_PASTICCERIA |
| MP-LAT | Latticini | 1.3_MATERIE_PRIME_PASTICCERIA |
| GEL-BAS | Basi per gelato | 1.5_GELATI_GRANITE |
| IMB-CAR | Imballaggi carta | 13.1_IMBALLAGGI |

---

## 11. REGOLA FONDAMENTALE

> **I corrispettivi sono l'UNICA fonte di RICAVI.**
> Le fatture ricevute (`invoices`) sono COSTI (ciclo passivo).
> NON sommarli insieme per calcolare il volume d'affari.
>
> `Volume d'Affari = SUM(corrispettivi.totale_giornata) per anno`

---

*Aggiornato: Aprile 2026*
