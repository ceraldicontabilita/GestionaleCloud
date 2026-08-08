"""Curated, stable operation catalogue layered over the live OpenAPI schema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadOperation:
    operation_id: str
    domain: str
    path: str
    description: str


@dataclass(frozen=True, slots=True)
class ActionOperation:
    action_id: str
    domain: str
    method: str
    path: str
    description: str


READ_OPERATIONS: tuple[ReadOperation, ...] = (
    ReadOperation("documents_list", "documenti", "/api/documenti/lista", "Cerca documenti con stato, categoria, anno e provenienza."),
    ReadOperation("documents_stats", "documenti", "/api/documenti/statistiche", "Statistiche e anomalie dell'archivio documentale."),
    ReadOperation("documents_drive_catalog", "documenti", "/api/documenti/drive/catalog", "Catalogo delle cartelle Drive configurate."),
    ReadOperation("documents_sync_status", "documenti", "/api/documenti/ultimo-sync", "Stato dell'ultima sincronizzazione documentale."),
    ReadOperation("invoices_received", "fatture", "/api/fatture-ricevute/archivio", "Archivio fatture ricevute con filtri e stato pagamento."),
    ReadOperation("invoice_detail", "fatture", "/api/fatture-ricevute/fattura/{fattura_id}", "Dettaglio completo di una fattura ricevuta."),
    ReadOperation("invoice_history", "fatture", "/api/fatture-ricevute/fattura/{fattura_id}/storia", "Storia, fonti e collegamenti di una fattura."),
    ReadOperation("invoice_payment_documents", "fatture", "/api/fatture-ricevute/fattura/{fattura_id}/documenti-pagamento", "Documenti di pagamento collegati alla fattura."),
    ReadOperation("suppliers_list", "fornitori", "/api/suppliers", "Anagrafica fornitori, metodo di pagamento e stato qualità."),
    ReadOperation("supplier_detail", "fornitori", "/api/suppliers/{supplier_id}", "Dettaglio anagrafico del fornitore."),
    ReadOperation("supplier_invoices", "fornitori", "/api/suppliers/{supplier_id}/fatture", "Fatture collegate a un fornitore."),
    ReadOperation("bank_statement_movements", "banca", "/api/estratto-conto-movimenti/movimenti", "Movimenti immutabili importati dall'estratto conto."),
    ReadOperation("bank_statement_summary", "banca", "/api/estratto-conto-movimenti/riepilogo", "Riepilogo dei movimenti dell'estratto conto."),
    ReadOperation("bank_transfers", "bonifici", "/api/archivio-bonifici/transfers", "Bonifici e documenti di pagamento archiviati."),
    ReadOperation("bank_transfers_reconciliation", "bonifici", "/api/archivio-bonifici/stato-riconciliazione", "Stato di riconciliazione dei bonifici."),
    ReadOperation("prima_nota_cash", "prima_nota", "/api/prima-nota/cassa", "Prima Nota Cassa paginata."),
    ReadOperation("prima_nota_bank", "prima_nota", "/api/prima-nota/banca", "Prima Nota Banca paginata."),
    ReadOperation("prima_nota_pending", "prima_nota", "/api/prima-nota/provvisori", "Fatture da decidere e pagamenti in attesa banca."),
    ReadOperation("prima_nota_stats", "prima_nota", "/api/prima-nota/stats", "Saldi e contatori di Prima Nota."),
    ReadOperation("prima_nota_unlinked_bank", "prima_nota", "/api/prima-nota/movimenti-ec-non-in-prima-nota", "Movimenti bancari non ancora rappresentati in Prima Nota."),
    ReadOperation("checks_list", "assegni", "/api/assegni", "Assegni con stato, fornitore, fatture e riscontro bancario."),
    ReadOperation("checks_candidates", "assegni", "/api/assegni/proposte-associazione", "Proposte non applicate di associazione assegno-fattura."),
    ReadOperation("checks_integrity", "assegni", "/api/assegni/verifica-associazioni", "Verifica delle associazioni assegni senza match per solo importo."),
    ReadOperation("paypal_transactions", "paypal", "/api/paypal-statements/transactions", "Transazioni PayPal e collegamenti a fatture/banca."),
    ReadOperation("paypal_dashboard", "paypal", "/api/paypal-statements/dashboard", "Quadratura PayPal, statement e movimenti banca."),
    ReadOperation("sumup_status", "pos", "/api/sumup/stato", "Stato API e sincronizzazione SumUp."),
    ReadOperation("sumup_summary", "pos", "/api/sumup/riepilogo", "Venduto SumUp lordo, payout e commissioni per periodo."),
    ReadOperation("pos_coherence", "pos", "/api/pos-corrispettivi/verifica-coerenza", "Coerenza tra POS reali, corrispettivi fiscali e accrediti."),
    ReadOperation("payroll_ledger", "paghe", "/api/prima-nota-salari/salari", "Dare/avere salari per dipendente, mese e anno."),
    ReadOperation("f24_list", "f24", "/api/f24", "Modelli F24 con righe tributo e stato."),
    ReadOperation("f24_detail", "f24", "/api/f24/{f24_id}", "Dettaglio F24 preservando le singole righe tributo."),
    ReadOperation("f24_reconciliation", "f24", "/api/f24-riconciliazione/dashboard", "Stato modelli, quietanze e prove di pagamento."),
    ReadOperation("withholding_taxes", "f24", "/api/ritenute", "Ritenute, scadenze e collegamenti F24."),
    ReadOperation("vat_period", "iva", "/api/iva/liquidazioni/{periodo}", "Liquidazione IVA mensile e relative fonti."),
    ReadOperation("vat_year", "iva", "/api/iva/riepilogo-annuale/{anno}", "Riepilogo IVA annuale mensile, senza logica trimestrale."),
    ReadOperation("vat_anomalies", "iva", "/api/iva/anomalie", "Anomalie di attribuzione e quadratura IVA."),
    ReadOperation("deadlines", "scadenze", "/api/scadenze/tutte", "Scadenze fiscali, F24, fatture e INPS."),
    ReadOperation("chart_of_accounts", "contabilita", "/api/piano-conti/", "Piano dei conti senza duplicazioni di codice conto."),
    ReadOperation("financial_statement", "contabilita", "/api/bilancio/riepilogo", "Riepilogo di bilancio per anno."),
    ReadOperation("coherence_audit", "audit", "/api/verifica-coerenza/completa/{anno}", "Audit di coerenza contabile per anno."),
    ReadOperation("coherence_discrepancies", "audit", "/api/verifica-coerenza/discrepanze/{anno}", "Discrepanze con fonte e severità."),
    ReadOperation("pagopa_receipts", "pagopa", "/api/pagopa/ricevute", "Ricevute PagoPA e associazioni a verbali/movimenti."),
    ReadOperation("rentals_vehicles", "noleggio", "/api/noleggio/veicoli", "Veicoli a noleggio e relativi costi."),
    ReadOperation("fines_list", "verbali", "/api/verbali-riconciliazione/lista", "Verbali con PagoPA, driver, fatture e banca."),
    ReadOperation("assets_summary", "cespiti", "/api/cespiti/riepilogo", "Cespiti e ammortamenti riepilogativi."),
)


ACTION_OPERATIONS: tuple[ActionOperation, ...] = (
    ActionOperation("prima_nota_confirm_pending", "prima_nota", "POST", "/api/prima-nota/provvisori/conferma", "Conferma il metodo di pagamento di una fattura provvisoria."),
    ActionOperation("prima_nota_wait_bank", "prima_nota", "POST", "/api/prima-nota/provvisori/attendi-banca", "Sposta una fattura in attesa di prova bancaria."),
    ActionOperation("prima_nota_mark_uncertain", "prima_nota", "POST", "/api/prima-nota/provvisori/segnala-dubbio", "Segnala un metodo di pagamento dubbio senza inventare un match."),
    ActionOperation("check_confirm_proposal", "assegni", "POST", "/api/assegni/conferma-proposta/{proposta_id}", "Conferma una proposta assegno-fattura già calcolata."),
    ActionOperation("paypal_link_transaction", "paypal", "POST", "/api/paypal-statements/transazione/{transaction_id}/associa", "Collega una transazione PayPal a entità esistenti."),
    ActionOperation("payroll_reconcile", "paghe", "PUT", "/api/prima-nota-salari/salari/{record_id}/riconcilia", "Conferma il collegamento cedolino-bonifico."),
    ActionOperation("f24_reconcile", "f24", "POST", "/api/f24/riconcilia", "Conferma il pagamento F24 preservando le righe tributo."),
    ActionOperation("pagopa_link_receipt", "pagopa", "POST", "/api/pagopa/ricevute/associa-manuale", "Collega una ricevuta PagoPA al verbale corretto."),
    ActionOperation("invoice_reconcile_bank", "fatture", "POST", "/api/fatture-ricevute/riconcilia-con-estratto-conto", "Conferma una fattura contro una prova bancaria univoca."),
)


READ_BY_ID = {item.operation_id: item for item in READ_OPERATIONS}
ACTION_BY_ID = {item.action_id: item for item in ACTION_OPERATIONS}
