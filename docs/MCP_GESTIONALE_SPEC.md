# Specifica MCP per Gestionale Cloud

## Obiettivo

Esporre agli agenti AI funzioni stabili del gestionale senza duplicare parser, query o regole contabili. Il server proposto si chiama `gestionale_cloud_mcp` e riusa esclusivamente servizi e API esistenti.

Questa fase definisce il contratto. L'attivazione remota richiede prima autenticazione OAuth, ruoli applicativi, audit log e test di autorizzazione; per questo non viene aggiunto un secondo backend MCP non protetto durante l'audit contabile.

## Principi

- Trasporto remoto Streamable HTTP; `stdio` solo per sviluppo locale.
- Input Pydantic con campi extra vietati e limiti espliciti.
- Output strutturato, paginato e privo di PDF/base64 salvo richiesta autorizzata.
- Annotazioni `readOnlyHint`, `destructiveHint`, `idempotentHint` e `openWorldHint` su ogni tool.
- JWT/OAuth con controllo di ruolo a ogni chiamata; le annotazioni non sostituiscono l'autorizzazione.
- Conferma umana per modifiche fiscali, riconciliazioni e operazioni documentali.
- Nessun tool di cancellazione definitiva nella prima versione.

## Tool di prima versione

| Tool | Riusa | Modalità | Risultato |
|---|---|---|---|
| `gestionale_search_documents` | `documents_inbox` e ricerca documenti | sola lettura | documenti filtrati, hash, stato e provenienza |
| `gestionale_get_invoice` | API fatture | sola lettura | fattura, fornitore, scadenza e collegamenti |
| `gestionale_get_vat_period` | motori IVA e liquidazioni | sola lettura | vendite, acquisti classificati, credito/debito e anomalie |
| `gestionale_list_bank_movements` | API estratto conto | sola lettura | movimenti paginati con stato riconciliazione |
| `gestionale_explain_reconciliation` | motore riconciliazione | sola lettura | evidenze, punteggio e motivi di esclusione |
| `gestionale_get_f24_status` | `f24_unificato` e `quietanze_f24` | sola lettura | modello, pagamento, quietanza e prova bancaria |
| `gestionale_get_payslip_context` | cedolini e prima nota salari | sola lettura | cedolino, dipendente, bonifico e stato match |
| `gestionale_run_audit` | `esegui_collaudo` | scrittura idempotente di report | report aggregato e alert aggiornati |
| `gestionale_propose_match` | motore matching | proposta | candidato non applicato con evidenze |
| `gestionale_confirm_match` | API riconciliazione esistente | mutazione confermata | relazione bidirezionale e audit log |

## Esempio di input paginato

```json
{
  "category": "f24",
  "status": "da_verificare",
  "limit": 25,
  "cursor": null,
  "response_format": "json"
}
```

La risposta include `items`, `count`, `has_more` e `next_cursor`. I dati personali non necessari vengono omessi.

## Autorizzazioni

| Ambito | Ruoli minimi |
|---|---|
| documenti e ricerca | operatore, contabile, amministratore |
| IVA e liquidazioni | contabile, amministratore |
| banca e riconciliazioni | tesoreria, contabile, amministratore |
| cedolini | paghe, amministratore |
| conferme e mutazioni | ruolo di dominio + conferma esplicita |

Ogni invocazione registra utente, tool, parametri minimizzati, esito, durata e identificativi delle entità coinvolte. Credenziali, PDF e payload base64 non entrano nei log.

## Criteri di accettazione

1. Nessuna query Mongo duplicata se esiste già un service applicativo.
2. Test di autorizzazione positivi e negativi per ogni tool.
3. Paginazione obbligatoria per gli elenchi.
4. Output schema validato.
5. Errori applicativi utili ma senza stack trace o segreti.
6. Dieci valutazioni read-only su casi storici e stabili prima del deploy.
7. Nessun dato reale incluso nei fixture o nel repository.

## Riferimenti tecnici

- [MCP specification: tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP specification: authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [SDK Python ufficiale](https://github.com/modelcontextprotocol/python-sdk)
