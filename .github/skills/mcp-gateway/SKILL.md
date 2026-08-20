# Skill: mcp-gateway

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Valida il gateway MCP del GestionaleCloud come interfaccia semantica tra agenti AI e il backend ERP, senza creare un secondo ERP.

## Obiettivo
Verificare che:
- il gateway esponga solo strumenti coerenti con il backend
- i tool siano read-only di default
- ogni scrittura richieda conferma esplicita, MFA, ruolo admin e autorizzazione
- i dati non vengano sovrascritti o interpretati da importo solo
- la sicurezza e il contratto siano coerenti con le specifiche del repo

## Fonti da usare
- docs/MCP_GESTIONALE_SPEC.md
- docs/MCP_GESTIONALE_RUNBOOK.md
- gestionale_mcp/
- app/ e app/routers/ per validare i confini delle API

## Requisiti applicativi
- Nessuna query diretta a MongoDB
- Nessun bypass del backend ERP
- Nessuna inferenza di pagamento solo da importo
- Nessun output binario, PDF, XML originale o credenziale
- Nessuna mutazione senza proposta e conferma

## Output atteso
- area controllata
- contratti e tool verificati
- sicurezza e autorizzazioni
- rischi effettivi
- evidenze live

## Esempi di prompt
- "valida MCP"
- "controlla il contratto tool e API"
- "cos'è vietato nel gateway MCP"
- "verifica il read-only policy"
- "analizza la sicurezza del server MCP"
