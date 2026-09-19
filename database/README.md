# Logica che vive nel database, non nel codice

Su Supabase ci sono **trigger PL/pgSQL che scrivono dati contabili** e che fino
al 19/09/2026 non comparivano da nessuna parte in questo repository. Si potevano
leggere tutti i file del progetto senza sapere che esistevano: nessun import,
nessun test, nessuna riga di `CLAUDE.md`.

Questa cartella non li esegue. Serve a **renderli visibili**: chi legge il
codice deve poter sapere che una riga di Prima Nota puo' nascere anche senza che
Python l'abbia scritta.

## Come si leggono quelli veri, adesso

```sql
select tgname, pg_get_triggerdef(t.oid)
from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'gestionale' and not t.tgisinternal;
```

## Le guardie — si tengono

`trg_guardia_delete` e `trg_guardia_truncate`, su `documents`, `blobs`,
`protocollo_drive`, `protocollo_impronte`, `protocollo_drive_giri`. Bloccano
cancellazioni e troncamenti non autorizzati. Sono la rete di sicurezza del §6
(«niente cancellazioni con filtro»): **non si toccano**.

`documents_touch_updated_at` e `documents_collection_versions` tengono
`updated_at` e le versioni per collezione, su cui poggia la cache incrementale
del runtime. Anche queste restano.

## `trg_bank_ec_after_write` — si tiene, ma va saputo

Dopo ogni scrittura su `estratto_conto_movimenti`:

- rigenera la riga corrispondente in **`bank_reconciliation_hub`** (2.017
  righe). Nessun file di questo repository nomina quella collezione: e' una
  proiezione dello stato di riconciliazione che oggi **non ha nessun lettore**;
- quando il movimento e' riconciliato, scrive la relazione in
  **`entity_relations`** (468 righe), che invece il codice legge davvero
  (`app/services/entity_relations_audit.py`).

Per questo resta: toglierlo spegnerebbe il flusso delle relazioni.

## `trg_bank_ec_before_write` — rimosso il 19/09/2026

Era un **secondo motore di riconciliazione**, scritto in SQL, che prima di ogni
inserimento sull'estratto conto:

1. riscriveva `categoria` quando sembrava un codice MCC;
2. riconosceva le spese bancarie (`COMMISSION|CANONE|BOLLO|...`), le marcava
   riconciliate e **inseriva una riga in `prima_nota_banca`** con
   `source: 'estratto_conto_hub'`;
3. agganciava i finanziamenti soci alle attese `rapido_apporto_soci`.

I punti 2 e 3 sono **esattamente** i due casi di
`app/services/proiezione_bancaria.classifica_movimento_ec`, che gira da solo
all'import dell'estratto conto
(`reconciliation_orchestrator.on_estratto_conto_importato_riprocessa`) ed e'
quello canonico: versionato, testato, con `rule_id` e `rule_version` che
lasciano una traccia verificabile. Il trigger girava **prima** e vinceva, quindi
per quei movimenti le regole controllabili non parlavano mai — e due
implementazioni delle stesse regole, una in Python e una in SQL, possono
divergere senza che nessuno se ne accorga.

Verificato prima di rimuoverlo:

- le due sorgenti **non si sovrapponevano**: nessun movimento dell'estratto
  conto risultava proiettato due volte in Prima Nota (i saldi non erano
  gonfiati);
- `proiezione_bancaria` cerca le righe esistenti per `estratto_conto_id` /
  `movimento_estratto_conto_id`, che il trigger scriveva entrambi: quindi **non
  ricreera' le 82 righe** gia' presenti;
- quelle 82 righe (`source: 'estratto_conto_hub'`, 129,50 EUR, dal 16/01 al
  24/08/2026) sono spese bancarie corrette e **restano dove sono**: una
  registrazione sbagliata si storna, e queste non sono nemmeno sbagliate.

Per ricrearlo, se dovesse servire, la definizione integrale e' in
`database/trg_bank_ec_before_write.sql`.
