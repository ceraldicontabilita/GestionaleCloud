# AUDIT REGISTRI & STAMPE — Tranche 6 (24/07/2026)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

> Regola tassativa del brief: un anno = 365 righe MAI 364; i giorni senza
> dati compaiono come "Dato non disponibile", MAI celle vuote o righe
> saltate; le stampe vanno GENERATE davvero e confrontate col DB.
> Fatto: tutte le stampe elencate sotto come "verificato con test" sono state
> generate su mongomock (DB "Gestionale_Test") con dati finti e i conteggi
> DB↔output confrontati in `backend/tests/test_audit_tranche6.py` (sezione 5).

## RISULTATO IN SINTESI

| Stampa/registro | Endpoint | Esito |
|---|---|---|
| Report HACCP mensile (temperature+sanificazione+anomalie+lotti) | `GET /api/report-haccp/mensile` | **2 DIFETTI CORRETTI** (righe saltate, celle vuote) — generato e confrontato con test |
| Registro lotti mensile HTML | `GET /api/registro-lotti/{anno}/{mese}` | Verificato OK con test (conteggi DB=stampa) |
| Registro lotti mensile CSV | `GET /api/registro-lotti/{anno}/{mese}/csv` | Verificato OK con test |
| Registro lotti annuale | `GET /api/registro-lotti/{anno}` | Verificato OK con test (12 mesi sempre presenti + totale) |
| Registro lotti ASL per periodo | `GET /api/registro-lotti-asl` | **DIFETTO CORRETTO** (troncava a 2000 lotti) — test con 2300 lotti |
| Export sanificazione mensile | `GET /api/sanificazione/export-pdf/{anno}/{mese}` | Verificato con test (tutte le righe attrezzature) + 1 finding documentato |
| Export disinfestazione annuale | `GET /api/disinfestazione/export-pdf/{anno}` | Verificato su codice: 12 mesi fissi, "Non effettuato" esplicito (disinfestazione.py:466-486) |
| Registro tracciabilità fatture-ricette | `GET /api/registro-tracciabilita` (+/csv,/json) | Verificato su codice + 1 finding (HTML mostra max 500 righe) |
| Stampa lotto POS 80mm / scheda richiamo / report lotto | stampa.py:616, lotti_produzione.py:2121 | Non oggetto di questa tranche (per-documento, non registri a giorni) |

Tutte le stampe sono HTML print-ready (`window.print()` → PDF): nessuna
generazione PDF server-side, quindi "generare la stampa" = generare l'HTML,
ed è ciò che i test fanno e confrontano.

---

## 1. REPORT HACCP MENSILE — `backend/routers/report_haccp.py`

### 1.1 — DIFETTO CORRETTO: apparecchi senza dati nel mese SPARIVANO
**Prima**: `load_temperature` aggiungeva la riga solo `if giorni:` (vecchia
report_haccp.py:142-143) → un frigorifero con ZERO rilevazioni nel mese non
compariva proprio nel registro: il buco più grave (un mese intero) era anche
quello invisibile. **Scenario**: il Frigo 2 resta scollegato per un mese →
il report mensile stampato per l'ASL semplicemente non lo elenca, nessuno
se ne accorge. Gravità: ALTA.
**Fix**: la riga viene emessa SEMPRE (report_haccp.py:157-162); i giorni
senza lettura sono resi come celle `N/D` con `title="Dato non disponibile"`
e legenda "N/D = Dato non disponibile" sotto la tabella
(report_haccp.py:238-243, 262-272).
**Test**: `test_report_haccp_mensile_giorni_mancanti_e_righe_mai_saltate` —
2 schede a DB (una con 2 letture su 31 giorni, una con 0): entrambe le righe
presenti in stampa, 60 celle N/D contate ((31-2)+31), "2 rilevazioni" nel
riepilogo = 2 record a DB.

### 1.2 — DIFETTO CORRETTO: giorni mancanti come celle "." (vuote)
**Prima**: cella `<td class="empty">.</td>` (vecchia report_haccp.py:227,244)
— il brief vieta le celle vuote/mute. **Fix**: "N/D" + tooltip + legenda
(vedi 1.1). Il numero di colonne del mese è già corretto anche per febbraio
e bisestili (`calendar.monthrange`, report_haccp.py:225): verificato con
`test_report_haccp_mensile_febbraio_28_colonne` (28 giorni nel 2026 →
27 N/D con 1 lettura presente). Un anno stampato mese per mese = 365 righe
di giorni, mai 364.

### 1.3 — DIFETTO CORRETTO: conformità ricalcolata con le soglie correnti
Il report valutava `in_range` con i `temp_min/temp_max` CORRENTI della
scheda: cambiare le soglie ridipingeva il passato (stesso difetto grave di
get_allarmi, vedi AUDIT_SCHEDULER_TEMPERATURE.md §2.1). **Fix**: le soglie
congelate nel record vincono (`limiti_record`, report_haccp.py:97-113, usate
in load_temperature:141-152 e table_temperature:247-259). **Test**: nel test
1.1 la lettura 8.0 °C con soglie-del-momento 0-10 resta CONFORME (nessuna
cella "ko") anche se la scheda oggi ha max 4.

### 1.4 — DIFETTO CORRETTO: troncamento silenzioso a 1000/2000 record
`anomalie` a `to_list(1000)` e `lotti` a `to_list(2000)` (vecchie
report_haccp.py:345,354): superate quelle soglie il report mensile perdeva
righe senza dirlo. Portati a 20000/50000 (report_haccp.py:369, 378).

### 1.5 — Finding documentato (non corretto): palette fuori design
Il report usa blu/indaco/violet (`#273b7a`, `.violet #6d28d9`,
report_haccp.py:398-405) e il registro lotti `#1565c0` — colori vietati da
REGOLE_ENZO ("MAI blu/indigo/viola") anche negli hex inline. Gravità: BASSA
(estetica, documento comunque leggibile). **Stato: da correggere** con la
skill `bonifica-design` in un giro dedicato (fuori scopo di questo audit
dati; non toccato per non mischiare le tranche).

## 2. REGISTRO LOTTI (mensile/annuale/CSV) — `routers/lotti_produzione.py`

- Mensile (1667-1767): filtro su anno/mese REALI con `parse_data_flessibile`
  (gestisce il formato misto dd/mm/yyyy + ISO), lettura fino a 50000 lotti;
  mese vuoto → riga esplicita "Nessun lotto registrato per questo mese"
  (1726-1727), non una tabella muta.
- Annuale (1799-1835): SEMPRE 12 righe mese (range(1,13), 1816) + totale.
- **Test** `test_registro_lotti_mensile_html_e_csv_conteggi`: 3 lotti di
  luglio (formati data misti) + 1 di giugno → stampa mensile contiene i 3
  numeri lotto e NON quello di giugno, totale stampato = 3 = conteggio DB;
  CSV = intestazione + 3 righe; annuale = 12 mesi tutti presenti, totale 4.
  Stato: verificato ok.

## 3. REGISTRO LOTTI ASL — `routers/utils.py:514-628`

**DIFETTO CORRETTO**: leggeva solo gli ultimi 2000 lotti per `created_at`
(vecchia utils.py:523) — con più di 2000 lotti in archivio i più VECCHI
sparivano dal registro del periodo richiesto, in silenzio (e il documento
stesso dice "conservare per almeno 5 anni", utils.py:627). Scenario: dopo
~2000 produzioni, l'ASL chiede il registro di 6 mesi fa → mancano lotti.
Gravità: MEDIA-ALTA. **Fix**: limite allineato a 50000 come il registro
mensile (utils.py:523-526). **Test**
`test_registro_lotti_asl_non_tronca_a_2000`: 2300 lotti a DB nel periodo →
la stampa ne dichiara 2300.

## 4. SANIFICAZIONE — `routers/sanificazione.py:698-781`

- Export mensile: griglia con TUTTE le attrezzature della lista fissa
  (757-764) e tutti i giorni del mese (752-754, febbraio/bisestile corretto
  712-717). **Test** `test_export_sanificazione_tutte_le_righe`: 8 righe
  attrezzature sempre presenti; 2 X a DB → 2 celle `check` in stampa.
- **Finding documentato (da correggere, fuori scopo qui)**: nella griglia il
  giorno senza "X" è una cella VUOTA (761-763) e lo schema
  `{attrezzatura: {giorno: "X"}}` non distingue "non sanificato" da "dato
  non registrato" — per allinearlo alla regola "Dato non disponibile"
  servirebbe un valore esplicito nello schema (es. "N/D" scritto dal job per
  i giorni passati senza registrazione): cambio di schema+job da concordare.
  Mitigazione attuale: il job delle 07:00 compila ogni giorno la scheda del
  giorno (haccp_auto.py:442-469), quindi i buchi nascono solo nei giorni in
  cui il backend è rimasto giù (vedi AUDIT_SCHEDULER_TEMPERATURE.md §2.3).
- Righe dinamiche extra: l'export itera la lista FISSA
  `ATTREZZATURE_SANIFICAZIONE` (757): un'attrezzatura aggiunta a mano nelle
  `registrazioni` con altro nome non comparirebbe nell'export. Gravità:
  BASSA (la UI usa la stessa lista). Stato: documentato.

## 5. REGISTRO TRACCIABILITÀ FATTURE-RICETTE — `routers/utils.py:631-753`

- HTML: mostra le prime 500 righe (`registro[:500]`, utils.py:673) mentre le
  statistiche in testa dichiarano il totale VERO dei collegamenti (707): il
  lettore vede "1200 collegamenti" ma 500 righe, senza avviso. CSV e JSON
  invece sono completi (718-753). Gravità: BASSA (il CSV è la via d'export).
  **Stato: da correggere** (basta una riga "mostrate 500 di N — usa il CSV
  per l'elenco completo"); non corretto ora per non gonfiare la tranche —
  candidato al prossimo giro insieme al finding 1.5.
- Emoji nei template stampa (📋 sanificazione.py:741, 🐀 disinfestazione.py:443,
  🖨️/🏢/📅): contro la regola "mai emoji nelle UI". Gravità: BASSA,
  documentato per il giro di bonifica design.

## 6. NON VERIFICABILE IN SANDBOX (dichiarato)

- La resa VISIVA/PDF finale (`window.print()` dal browser) non è
  verificabile qui: il Chromium headless della sandbox non fa rete (limite
  noto in CLAUDE.md). Verificati: HTML generato, conteggi, struttura righe/
  colonne. Serve il solito giro visivo di Enzo da telefono per il layout.
- `GET /api/listino/genera-pdf` e stampanti fisiche ESC/POS
  (routers/stampanti.py): richiedono servizi/hardware esterni — fuori scopo
  e non testabili in sandbox.
