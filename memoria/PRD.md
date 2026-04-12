# PRD — Ceraldi ERP
> Product Requirements Document | Aggiornato: Aprile 2026

---

## Identità del Progetto

**Nome**: Ceraldi ERP (codice repo: `gestionale2`)
**Azienda**: Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli
**P.IVA**: 04523831214
**Scopo**: Sistema ERP full-stack per contabilità, HR, magazzino e compliance fiscale italiana.
**Architettura**: React 18 + FastAPI + MongoDB Atlas
**Utenti**: non multi-utente — uso interno da parte dello staff amministrativo
**Database**: MongoDB Atlas (DB: `Gestionale`)

---

## Regole Fondamentali (Non Negoziabili)

1. **Design system**: SOLO CSS inline con le costanti di `lib/utils.js`. Vietato Tailwind e Shadcn per le pagine gestionali.
2. **Lingua**: rispondere SEMPRE in italiano nei commenti e nella UI.
3. **Database**: MongoDB Atlas (`Gestionale`) via `MONGO_URL` dal `.env`.
4. **Backend entry**: NON eliminare `backend/server.py` — è il punto di avvio di Supervisor.
5. **Collection**: usare sempre le costanti di `app/database/collections.py`.
6. **IMAP**: sempre in `asyncio.to_thread()` — non bloccare l'event loop.
7. **`_id` MongoDB**: escludere sempre con `{"_id": 0}` nelle query o via Pydantic.

---

## Fix Applicati (Aprile 2026 - Sessione Corrente)

### ✅ Cedolini Page (HRCedolini.jsx)
- **Problema**: Tutti i cedolini mostravano "Libro unico.pdf" come nome dipendente, LORDO sempre 0.00€
- **Causa**: Il frontend cercava `dipendente_nome` ma il DB usa `nome_dipendente`
- **Fix**: Riscritto completamente HRCedolini.jsx con:
  - Corretta mappatura campi: `nome_dipendente` → nome visualizzato
  - Due viste: "Per Mese" (raggruppamento collassabile) e "Per Dipendente" (card)
  - Ricerca per nome/codice fiscale/mansione
  - KPI corretti (26 cedolini, 14 dipendenti, netto totale)
  - Download PDF per ogni cedolino

### ✅ Noleggio Auto (NoleggioAuto.jsx)
- **Problema**: Selettore anno duplicato (uno nel header + badge "Anno: 2026")
- **Fix**: Rimosso badge ridondante, rimosso wrapper PageLayout duplicato

### ✅ Strumenti / Verifica Coerenza (VerificaCoerenza.jsx)
- **Problema**: Spinner "Caricamento" rimane visibile e card vuote appaiono insieme
- **Causa**: Tabs e card non erano wrappati in `!loading`
- **Fix**: Aggiunto `!loading` a tabs e contenuto tab, spinner animato durante caricamento
