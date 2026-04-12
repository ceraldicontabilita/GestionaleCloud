# Blueprint HR — Ceraldi ERP
> Aggiornato: Aprile 2026 | Redesign completo completato

---

## STRUTTURA (post-redesign Aprile 2026)

La vecchia `GestioneDipendentiUnificata.jsx` (2.183 righe) è stata eliminata.
Al suo posto: 4 pagine separate in `frontend/src/pages/hr/`.

### Route HR
```
/dipendenti          → HRDipendenti.jsx      (anagrafica + dettaglio dipendente)
/dipendenti/cedolini → HRCedolini.jsx        (buste paga + import Gmail)
/dipendenti/presenze → HRPresenze.jsx        (calendario presenze)
/dipendenti/tfr      → HRTFR.jsx             (gestione TFR e acconti)
```

### SecondaryTabs (navigazione HR)
```
"Dipendenti"  → /dipendenti
"Cedolini"    → /dipendenti/cedolini
"Presenze"    → /dipendenti/presenze
"TFR"         → /dipendenti/tfr
```

---

## API BACKEND (tutte funzionanti)

```
GET  /api/dipendenti                              → lista 34 dipendenti
GET  /api/dipendenti/{id}                         → singolo dipendente
PUT  /api/dipendenti/{id}                         → salva anagrafica
GET  /api/cedolini?anno=2026                      → cedolini per anno
GET  /api/cedolini/dipendente/{id}?anno=          → cedolini per dipendente
POST /api/cedolini/import-gmail?since_days=180    → importa da Gmail (non bloccante)
GET  /api/paghe/buste-paga?anno=                  → buste paga libro unico
GET  /api/paghe/distinte-f24?anno=                → distinte F24
GET  /api/tfr/acconti/{id}                        → acconti TFR dipendente
POST /api/tfr/acconti                             → nuovo acconto TFR
PUT  /api/tfr/acconti/{id}                        → modifica acconto
DELETE /api/tfr/acconti/{id}                      → cancella acconto
GET  /api/attendance/ore-lavorate/{id}?mese=&anno= → ore lavorate
GET  /api/attendance/richieste-pending            → richieste assenza
PUT  /api/attendance/richiesta-assenza/{id}/approva → approva assenza
GET  /api/giustificativi/dipendente/{id}/saldo-ferie → saldo ferie e ROL
GET  /api/archivio-bonifici/transfers?beneficiario= → bonifici stipendio
```

---

## SCHEMA COLLECTION `dipendenti` (CANONICA)

```json
{
  "id": "uuid",
  "nome": "Mario",
  "cognome": "Rossi",
  "codice_fiscale": "RSSMRA80A01F839Y",
  "email": "mario.rossi@example.com",
  "telefono": "333...",
  "mansione": "Pasticciere",
  "livello": "3",
  "tipo_contratto": "tempo_indeterminato",
  "data_assunzione": "2019-01-15",
  "data_cessazione": null,
  "iban": "IT60X0542811101000000123456",
  "banca": "BPM",
  "importo_mensile": 1800.00,
  "importo_netto": 1406.00,
  "in_carico": true
}
```

**Collection corretta**: `dipendenti` (34 record). **NON** `employees` (31 record — copia solo per presenze batch).

---

## SCHEMA CEDOLINO

```json
{
  "id": "uuid",
  "dipendente_id": "uuid (→ dipendenti.id)",
  "dipendente_nome": "Mario Rossi",
  "anno": 2026,
  "mese": 1,
  "lordo": 1800.00,
  "netto": 1406.00,
  "inps_dipendente": 189.00,
  "inps_azienda": 420.00,
  "irpef": 380.00,
  "tfr": 135.00,
  "costo_azienda": 2355.00,
  "ferie_residue": 12,
  "permessi_rol": 8,
  "tipo": "mensile",
  "source": "gmail | cedolino_v2 | document_ai | pdf_upload",
  "file_hash": "md5 (solo source=gmail)",
  "filename": "Busta paga - Mario Rossi - Gennaio 2026.pdf",
  "pagato": true
}
```

---

## FORMATI CEDOLINO SUPPORTATI

| Formato | Periodo | Parser File |
|---|---|---|
| CSC Napoli | Fino al 2018 | `busta_paga_multi_template.py` |
| Zucchetti classico | 2018–2022 | `busta_paga_multi_template.py` |
| Zucchetti nuovo | Dal 2022 (separatore `s`) | `busta_paga_multi_template.py` |
| Teamsystem | Variabile | `busta_paga_multi_template.py` |

Tutti i formati estraggono:
- Netto, lordo, IRPEF, INPS dipendente
- Progressivi annui INPS e IRPEF
- Quota TFR del mese
- Ferie residue (giorni) e permessi ROL (ore)
- Giustificativi usati nel mese

---

## CODICI GIUSTIFICATIVI

| Codice | Significato |
|---|---|
| FE | Ferie |
| RL | Riposo per Lavoro (ROL) |
| MA | Malattia |
| SM | Smart Working |
| L1 | Legge 104 (disabilità) |
| CP | Congedo parentale |
| IN | Infortunio |
| AI | Assenza ingiustificata |
| PE | Permesso |

---

## IMPORT CEDOLINI DA GMAIL

- **Endpoint**: `POST /api/cedolini/import-gmail?since_days=180`
- **Esecuzione**: `asyncio.to_thread()` — NON blocca il server
- **Deduplicazione**: `file_hash` (MD5 del file PDF)
- **Parsing filename**: `_parse_filename_periodo()` → `"Busta paga - Nome - Aprile 2026.pdf"` → `{mese: 4, anno: 2026}`
- **Stato**: 271 cedolini Gmail già importati con mese/anno (Apr 2026)
- **Mittenti accettati**: `f.ferrantini@...`, `rosaria.marotta@...` (whitelist in `mittenti_email`)

---

## TFR — LOGICA DI CALCOLO

**Quota mensile:**
```
quota_mese = retribuzione_lorda / 13.5   (Art. 2120 c.c.)
```

**Rivalutazione annua:**
```
rivalutazione = 1.5% fisso + 75% dell'indice ISTAT del periodo
```

**Collection**: `tfr_accantonamenti` — una riga per dipendente × mese × anno
- NON creare duplicati: verificare se esiste già prima di inserire

**API:**
```
GET  /api/tfr/acconti/{dipendente_id}       → storico acconti
POST /api/tfr/acconti                       → registra nuovo acconto
PUT  /api/tfr/acconti/{id}                  → modifica acconto
DELETE /api/tfr/acconti/{id}               → cancella acconto
```

---

## PRESENZE E GIUSTIFICATIVI

**Collections presenze:**
- `presenze` (20.989): storico completo presenze giornaliere
- `presenze_mensili` (1.629): riepiloghi mensili
- `attendance_presenze_calendario`: calendario mensile per la UI

**API:**
```
GET  /api/attendance/ore-lavorate/{id}?mese=3&anno=2026
GET  /api/attendance/richieste-pending
PUT  /api/attendance/richiesta-assenza/{id}/approva
GET  /api/giustificativi/dipendente/{id}/saldo-ferie
```

---

## AGENTE HR GUARDIANO

L'agente `HRGuardiano` monitora in modo autonomo:
- Contratti in scadenza nei prossimi 30/60/90 giorni
- Ferie accumulate > 25 giorni → segnalazione "ferie in scadenza"
- Cedolini di tipo "tredicesima" → promemoria rivalutazione TFR
- Stipendi non erogati nei tempi previsti

Le segnalazioni vanno in `agenti_segnalazioni` con tipo `hr` e priorità (alta/media/bassa).

---

## REGOLE CRITICHE SVILUPPO HR

1. Collection corretta: `dipendenti` (NON `employees`)
2. Design: SOLO CSS inline da `lib/utils.js` — NO Tailwind, NO Shadcn
3. Icone: lucide-react ONLY — NO emoji nel codice sorgente
4. NO tab che duplicano le SecondaryTabs (Cedolini, Presenze, TFR hanno proprie pagine)
5. Selettore anno necessario in Cedolini (anni presenti: 2019–2026)
6. NO early return prima dei React Hooks — usare render condizionale
7. IMAP sempre in `asyncio.to_thread()` — mai chiamare IMAP direttamente in async

---

*Aggiornato: Aprile 2026*
