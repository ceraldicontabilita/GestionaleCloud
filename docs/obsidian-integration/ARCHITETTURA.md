# Architettura

<!-- gestionalecloud-doc
status: planned
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!WARNING]
> Specifica o piano approvato, ma non ancora completamente operativo. Verificare il runbook corrente e il codice distribuito prima dell'uso.

> [!WARNING]
> Specifica pianificata: exporter, registro, scheduler e sincronizzazione privata
> descritti qui non sono ancora componenti operativi.

## Principio fondamentale

La sincronizzazione iniziale è **monodirezionale**:

```text
GestionaleCloud + Drive/Sheets
            |
            | eventi e snapshot normalizzati
            v
Obsidian Knowledge Export
            |
            | Markdown, JSON Canvas, indici
            v
Vault Obsidian
```

Il vault deve poter essere cancellato e rigenerato senza perdere dati operativi. Le sole annotazioni personali sono conservate in blocchi esplicitamente delimitati.

## Componenti proposti

### `ObsidianKnowledgeExporter`

Servizio applicativo che:

- legge entità già autorizzate dal Gestionale;
- traduce i record in note Markdown con proprietà YAML;
- crea collegamenti usando identificatori canonici, non nomi fragili;
- scrive tramite file temporaneo e rename atomico;
- calcola SHA-256 dei contenuti generati;
- non riscrive file invariati;
- conserva la sezione `ANNOTAZIONI_PERSONALI`;
- registra esito, errori e durata di ogni esportazione.

### `KnowledgeProjectionRegistry`

Registro con almeno:

- `entity_type`;
- `entity_id`;
- `vault_id`;
- `note_path`;
- `source_updated_at`;
- `exported_at`;
- `content_hash`;
- `projection_version`;
- `status`;
- `last_error`.

### Scheduler

- esportazione incrementale dopo eventi rilevanti;
- riconciliazione completa giornaliera;
- rigenerazione manuale per tipo di entità o singolo record;
- heartbeat e avviso se la sincronizzazione non viene completata.

### Trasporto

Ordine di preferenza:

1. Obsidian CLI con Headless Sync su ambiente server dedicato;
2. cartella locale sincronizzata e controllata;
3. pacchetto ZIP rigenerabile per installazione iniziale o disaster recovery.

Il trasporto non deve dare al vault accesso diretto alle credenziali Gmail, Drive, banca o Gestionale.

## Tre vault separati

### `GestionaleCloud-Privato`

Contabilità, fiscalità, banche, personale, PEC, verbali, pratiche e documenti sensibili.

### `GestionaleCloud-Procedure`

Manuali, runbook, checklist, decisioni tecniche, formazione e documentazione del Gestionale.

### `GestionaleCloud-Condivisibile`

Conoscenza approvata per collaboratori o pubblicazione. Nessun dato personale, bancario o fiscale.

## Apertura incrociata

Ogni nota contiene `gestionale_url`. Il Gestionale espone “Apri in Obsidian” con URI codificata:

```text
obsidian://open?vault=GestionaleCloud-Privato&file=Veicoli%2FGW980ED
```

L’URI serve ad aprire o cercare, non a cambiare uno stato operativo.

## Gestione dei documenti

- Il documento originale resta nel sistema documentale canonico.
- La nota contiene identificatore, hash, tipo, data, provenienza e URL autenticato.
- Una copia nel vault è consentita solo per documenti esplicitamente classificati come idonei.
- PDF cifrati, PEC, estratti conto, documenti del personale e credenziali non vengono duplicati per impostazione predefinita.

## Annotazioni personali

Le note generate possono contenere:

```markdown
<!-- ANNOTAZIONI_PERSONALI:START -->
Testo libero preservato durante le rigenerazioni.
<!-- ANNOTAZIONI_PERSONALI:END -->
```

Tutto il resto è rigenerabile e non deve essere modificato manualmente.

## Osservabilità

Ogni run registra:

- entità lette, create, aggiornate, invariate e fallite;
- note mancanti o collegamenti irrisolti;
- durata e versione della proiezione;
- ultimo heartbeat riuscito;
- errori recuperabili e definitivi;
- differenze fra sorgente e vault.
