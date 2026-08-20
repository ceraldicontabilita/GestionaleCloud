# Modello delle note

## Convenzioni

- Date ISO `YYYY-MM-DD`; timestamp ISO con timezone.
- Identificatori numerici lunghi e codici sono sempre stringhe.
- Importi sono numeri decimali; valuta separata.
- Collegamenti generati da ID stabili.
- Provenienza e confidenza non vengono omesse.
- Stato operativo mostrato come proiezione non modificabile.

## Proprietà comuni

```yaml
---
projection_version: 1
entity_type: documento
entity_id: DOC-000001
title: Avviso PartenoPay 302000600008408304
status: DA_VERIFICARE
source_system: GestionaleCloud
source_updated_at: 2026-08-20T10:30:00+02:00
exported_at: 2026-08-20T10:31:00+02:00
gestionale_url: https://gestionale.example/documenti/DOC-000001
document_hash: abcdef...
sensitivity: riservato
tags:
  - gestionalecloud
  - documento
---
```

## Nomi e percorsi

```text
Aziende/{azienda_id}.md
Soggetti/Fornitori/{fornitore_id}.md
Soggetti/Clienti/{cliente_id}.md
Personale/{dipendente_id}.md
Veicoli/{veicolo_id}.md
Documenti/{anno}/{documento_id}.md
Contabilita/Fatture/{anno}/{fattura_id}.md
Contabilita/Pagamenti/{anno}/{pagamento_id}.md
Fiscalita/F24/{anno}/{f24_id}.md
Fiscalita/Dichiarazioni/{anno}/{dichiarazione_id}.md
Pratiche/{tipo}/{pratica_id}.md
Automazioni/Run/{anno}/{run_id}.md
Procedure/{procedura_id}.md
Decisioni/{anno}/{decisione_id}.md
```

Il nome leggibile vive nel titolo della nota. Il percorso usa l’ID per evitare collisioni e rinomine.

## Relazioni

Esempio di proprietà:

```yaml
azienda_id: AZ-001
fornitore_id: FOR-0042
documento_ids:
  - DOC-1001
  - DOC-1002
pagamento_ids:
  - PAG-8821
```

Esempio nel corpo:

```markdown
## Collegamenti

- Azienda: [[Aziende/AZ-001|Ceraldi Group SRL]]
- Fornitore: [[Soggetti/Fornitori/FOR-0042|Fornitore esempio]]
- Documento: [[Documenti/2026/DOC-1001]]
- Pagamento: [[Contabilita/Pagamenti/2026/PAG-8821]]
```

## Timeline

Ogni evento mantiene origine e autore:

```markdown
## Timeline

- 2026-08-18 09:12 — Documento ricevuto via Gmail (`message_id=...`).
- 2026-08-18 09:14 — Parsing completato con confidenza 0,98.
- 2026-08-19 16:20 — Associazione confermata da utente `...`.
```

## Separazione delle prove

Una nota non deve ridurre tutto a `pagato: true`. Deve distinguere:

```yaml
pagamento_dichiarato: true
quietanza_documentale_presente: true
ricevuta_paypal_presente: false
bonifico_documentale_presente: false
movimento_bancario_verificato: false
```

