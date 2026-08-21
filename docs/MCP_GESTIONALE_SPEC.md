# GestionaleCloud MCP — specifica di produzione

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

## Scopo e confine architetturale

`gestionale_cloud_mcp` espone agli agenti AI tutte le aree operative del GestionaleCloud senza creare un secondo ERP.

Il server MCP:

1. non apre connessioni Drive/Sheets;
2. non interroga direttamente Drive, Gmail, PayPal o SumUp;
3. usa le API HTTP già registrate dal backend come unico confine applicativo;
4. inoltra il JWT dell'utente al backend, che continua a verificare firma, scadenza, revoca e ruolo;
5. rende disponibili strumenti specifici e, per la copertura completa, le sole operazioni `GET` dichiarate dall'OpenAPI corrente;
6. rifiuta URL arbitrari, redirect, parametri non dichiarati, export e contenuti binari;
7. non abilita scritture finché non sono soddisfatti contemporaneamente configurazione, ruolo admin, MFA e conferma esplicita.

Questo evita letture Drive/Sheets duplicate, regole contabili divergenti e bypass dei middleware già presenti.

## Regole semantiche inderogabili

- Documento, fattura, movimento bancario, assegno, cedolino, F24, quietanza, liquidazione IVA, transazione POS e payout sono entità distinte.
- L'importo da solo non costituisce mai una corrispondenza sufficiente.
- Ogni collegamento mantiene identificativi e provenienza in entrambe le direzioni.
- Il movimento bancario importato è prova finanziaria immutabile; la Prima Nota lo rappresenta ma non lo sostituisce.
- Un F24 può contenere più codici tributo: stato e residuo si determinano per riga, non soltanto sul totale del modello.
- XML RT, Numia, SumUp e PayPal sono fonti indipendenti. XML RT non attribuisce il gestore POS; payout e accrediti non sono nuovi ricavi.
- Cassa configurata sul fornitore porta la fattura in Cassa; Banca resta Provvisoria finché non esiste un riscontro bancario valido.
- Un risultato ambiguo resta da verificare: l'MCP propone, non inventa.

## Tool pubblicati

| Tool | Area | Effetto |
|---|---|---|
| `gestionale_status` | sistema | verifica API, identità, ruolo, MFA e catalogo |
| `gestionale_list_capabilities` | sistema | elenca tool curati, GET OpenAPI e azioni confermate |
| `gestionale_read_api` | tutte | esegue una GET OpenAPI non binaria con validazione rigorosa |
| `gestionale_search_documents` | documenti | ricerca per anno, categoria, stato e testo |
| `gestionale_search_invoices` | fatture | ricerca fatture ricevute e relativi stati |
| `gestionale_get_invoice_context` | fatture | dettaglio, storia e prove di pagamento, senza file binari |
| `gestionale_list_bank_movements` | banca | movimenti estratto conto filtrati e paginati |
| `gestionale_get_prima_nota` | contabilità | Cassa, Banca o Provvisori, senza creare righe |
| `gestionale_get_checks` | assegni | assegni e proposte di associazione |
| `gestionale_get_payment_channel` | PayPal/POS | PayPal, SumUp o coerenza POS reale |
| `gestionale_get_payroll` | paghe | Prima Nota salari per dipendente/mese/anno |
| `gestionale_get_f24_status` | F24 | modelli, righe tributo, quietanze e banca |
| `gestionale_get_vat_period` | IVA | liquidazione mensile/annuale e anomalie |
| `gestionale_get_accounting_report` | contabilità | piano conti, bilancio, audit o discrepanze |
| `gestionale_get_operational_context` | operazioni | scadenze, PagoPA, noleggi, verbali, cespiti, bonifici |
| `gestionale_prepare_action` | workflow | crea una proposta a durata limitata senza eseguirla |
| `gestionale_execute_confirmed_action` | workflow | esegue una proposta solo dopo tutti i controlli |

### Copertura completa senza tool duplicati

`gestionale_read_api` non accetta un percorso o un URL. Accetta esclusivamente un `operationId` presente nell'OpenAPI vivo del backend. Il gateway verifica:

- metodo `GET`;
- percorso interno `/api/...`;
- nomi dei parametri path e query;
- limiti di paginazione;
- assenza di endpoint PDF, download, export, template o XML originale;
- risposta JSON entro la dimensione configurata.

Questa soluzione copre le centinaia di letture esistenti senza generare centinaia di funzioni quasi identiche.

## Modello di autorizzazione

### Trasporto `stdio`

È destinato allo sviluppo locale e ai client desktop. Il processo legge `GESTIONALE_MCP_API_TOKEN` e lo inoltra alle API. Il token non viene scritto nei log.

### Trasporto Streamable HTTP

Il gateway richiede:

- metadata dell'authorization server e del resource server;
- protezione DNS rebinding con allowlist di host e origin;
- JWT valido del GestionaleCloud;
- scope MCP `gestionale:read` per ogni tool;
- ruolo `admin`, MFA attiva e verificata per le mutazioni.

La verifica del bearer token viene delegata a `/api/auth/verify`, quindi include il controllo di revoca già implementato dal gestionale.

### Mutazioni

Le modifiche sono disabilitate per impostazione predefinita. Per abilitarle serve `GESTIONALE_MCP_ALLOW_WRITES=true`.

Il flusso è sempre a due passaggi:

1. `gestionale_prepare_action` valida l'azione contro una lista chiusa e crea una proposta con hash SHA-256 e scadenza;
2. `gestionale_execute_confirmed_action` accetta soltanto la frase esatta `CONFERMO <proposal_id>`, poi ricontrolla admin e MFA.

Non sono presenti strumenti di cancellazione definitiva. Le azioni ammesse riguardano soltanto conferme o collegamenti già supportati dalle API: Provvisori, assegni, PayPal, cedolini, F24, PagoPA e fatture-banca.

## Protezione dei dati

- Log: nome tool, operation ID, nomi dei parametri, esito, durata e trace ID; mai valori, credenziali o documenti.
- Output: token, password, segreti, chiavi API, base64, contenuto PDF e XML originale sono oscurati.
- Dimensione: massimo 2 MB per risposta per impostazione predefinita.
- Liste: massimo 500 elementi per impostazione predefinita.
- Errori: nessuno stack trace o URL sensibile restituito all'agente.
- Test: soltanto risposte HTTP sintetiche; nessun fixture contiene dati aziendali reali.

## Contratto delle azioni consentite

| Action ID | Endpoint esistente | Vincolo |
|---|---|---|
| `prima_nota_confirm_pending` | `POST /api/prima-nota/provvisori/conferma` | conferma metodo |
| `prima_nota_wait_bank` | `POST /api/prima-nota/provvisori/attendi-banca` | non crea pagamento |
| `prima_nota_mark_uncertain` | `POST /api/prima-nota/provvisori/segnala-dubbio` | segnala anomalia |
| `check_confirm_proposal` | `POST /api/assegni/conferma-proposta/{proposta_id}` | proposta preesistente |
| `paypal_link_transaction` | `POST /api/paypal-statements/transazione/{transaction_id}/associa` | entità preesistenti |
| `payroll_reconcile` | `PUT /api/prima-nota-salari/salari/{record_id}/riconcilia` | cedolino/bonifico |
| `f24_reconcile` | `POST /api/f24/riconcilia` | righe tributo preservate |
| `pagopa_link_receipt` | `POST /api/pagopa/ricevute/associa-manuale` | ricevuta/verbale |
| `invoice_reconcile_bank` | `POST /api/fatture-ricevute/riconcilia-con-estratto-conto` | prova bancaria |

## Accettazione tecnica

1. Ogni endpoint curato deve esistere nell'OpenAPI corrente con il metodo atteso.
2. Le operazioni generiche non possono chiamare POST, PUT, PATCH o DELETE.
3. Path traversal, URL assoluti, header injection e parametri sconosciuti devono fallire.
4. Redirect, file, output non JSON e risposte oltre limite devono fallire.
5. Le proposte devono essere allowlistate, scadere e poter essere consumate una sola volta.
6. Scritture disabilitate, ruolo non admin o MFA non verificata devono fallire chiuso.
7. Tutti i tool devono avere annotazioni MCP corrette.
8. La suite di valutazione read-only deve contenere almeno dieci casi stabili e sintetici.

## Riferimenti

- [MCP Python SDK 2.0](https://github.com/modelcontextprotocol/python-sdk)
- [Documentazione SDK Python](https://py.sdk.modelcontextprotocol.io/)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
