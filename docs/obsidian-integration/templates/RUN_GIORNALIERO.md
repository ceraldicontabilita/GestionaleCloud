---
projection_version: 1
entity_type: automation_run
entity_id: "{{run_id}}"
run_date: "{{run_date}}"
status: "{{status}}"
started_at: "{{started_at}}"
finished_at: "{{finished_at}}"
source_system: GestionaleCloud
tags: [gestionalecloud, automazione, controllo-giornaliero]
---

# Controllo giornaliero {{run_date}}

| Indicatore | Valore |
| --- | ---: |
| Sorgenti controllate | {{sources_checked}} |
| Messaggi analizzati | {{messages_scanned}} |
| Documenti nuovi | {{documents_created}} |
| Note aggiornate | {{notes_updated}} |
| Associazioni ambigue | {{ambiguous_matches}} |
| Errori | {{errors}} |

## Nuovi elementi

{{new_items}}

## Da verificare

{{review_items}}

## Errori

{{error_details}}

