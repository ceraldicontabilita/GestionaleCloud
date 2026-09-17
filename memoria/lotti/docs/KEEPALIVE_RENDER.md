# Risolvere il cold start di Render (risveglio lento ~50s)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Il problema
Il piano gratuito di Render **spegne il backend dopo ~15 minuti di inattività**.
Alla prima richiesta successiva il servizio si riavvia e impiega ~50 secondi a rispondere.
Per chi usa l'app al banco (tablet, mattina presto) è un'attesa inaccettabile.

## La soluzione gratuita: UptimeRobot
Un servizio esterno chiama un endpoint leggero del backend ogni pochi minuti,
tenendolo sempre sveglio. È gratuito e non richiede modifiche al codice.

L'endpoint da usare è già pronto e non fa query al database (risposta istantanea):

    https://lotti-backend-2wwb.onrender.com/api/health

Restituisce `{"status":"ok","db":"Gestionale"}`.

### Passi (una volta sola, ~3 minuti)
1. Vai su https://uptimerobot.com e crea un account gratuito.
2. Clicca **+ New Monitor**.
3. Imposta:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Lotti backend keep-alive
   - **URL**: `https://lotti-backend-2wwb.onrender.com/api/health`
   - **Monitoring Interval**: 5 minuti (il minimo gratuito)
4. Salva. Fatto.

Da quel momento il backend resta sveglio e risponde subito.

### Nota sui costi
Il piano gratuito di Render ha ore-mese limitate. Un ping ogni 5 minuti 24/7
consuma più ore. Se le ore non bastano, due alternative:
- Limitare il monitoraggio UptimeRobot alle ore di apertura (es. 5:00–21:00)
  tramite la finestra di manutenzione, così di notte il servizio dorme.
- Passare al piano Render a pagamento (Starter), che elimina del tutto lo
  spegnimento senza bisogno di ping.

Il ping gratuito risolve già il problema nelle ore di lavoro.
