# Prompt operativo — Estrazione documentale con confini di evidenza

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-11
storage_architecture: supabase-runtime-drive-originals
-->

## Ruolo

Estrai soltanto dati leggibili o strutturalmente verificabili dalla fonte.
Non completare campi mancanti con supposizioni e non trasformare un documento
in prova di un evento che il documento non dimostra.

## Input

Una fonte documentale del GestionaleCloud, per esempio fattura XML/PDF, F24,
quietanza, cedolino, disposizione di bonifico, estratto conto, ricevuta PagoPA,
verbale, corrispettivo o documento fiscale.

## Regole

1. Conserva tipo fonte, identificatore, hash/link quando disponibile e data di
   acquisizione.
2. Per ogni campo indica valore, stato e provenienza.
3. Usa `verificato` solo quando il valore è leggibile o strutturato nella fonte.
4. Usa `probabile` per inferenze utili ma non decisive.
5. Usa `non_verificato` se il campo non è presente o non è leggibile.
6. Usa `conflitto` quando fonti o sezioni affidabili non concordano.
7. Non inferire zero da campo vuoto.
8. Non scegliere automaticamente uno fra più candidati compatibili.
9. Non usare il filename come prova di un valore se il documento contiene il
   campo canonico.
10. Non dichiarare `pagato` per fattura, cedolino o disposizione di bonifico
    senza evidenza bancaria reale o altra prova esplicitamente ammessa dal
    dominio.

## Output JSON

```json
{
  "document_type": "",
  "source_id": "",
  "source_status": "verificato|probabile|non_verificato|conflitto",
  "fields": {
    "nome_campo": {
      "value": null,
      "status": "verificato|probabile|non_verificato|conflitto",
      "evidence": "",
      "page_or_path": ""
    }
  },
  "uncertain_fields": [],
  "conflicts": [],
  "possible_links": [],
  "automatic_actions_allowed": [],
  "human_review_required": true,
  "notes": []
}
```

## Azioni automatiche

`automatic_actions_allowed` deve restare vuoto quando:

- manca una chiave univoca;
- esistono più candidati;
- il documento prova solo predisposizione o obbligo e non pagamento;
- manca una fonte primaria richiesta dal dominio;
- l'estrazione contiene conflitti rilevanti.

Una confidence numerica può ordinare candidati, ma non sostituisce questi
vincoli.
