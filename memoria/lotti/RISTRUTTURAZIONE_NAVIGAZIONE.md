# Ristrutturazione navigazione

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Modifiche applicate

- Ridotte le voci principali da sei a cinque: Oggi, Produzione, Tracciabilità, Magazzino e Acquisti.
- Spostati Gelati e Fornitori nel menu secondario senza eliminare le relative pagine.
- Raggruppato il menu Altro per Produzione e scorte, Acquisti e vendita, Analisi, Amministrazione e Supporto.
- Estratta la configurazione di navigazione da `App.js` in `frontend/src/config/navigation.js`.
- Aggiornati titolo, descrizione, colore tema e messaggio `noscript`.
- Rimossa la `.gitconfig` generata dall'ambiente precedente.
- Rimossi i riferimenti testuali e i file di configurazione del vecchio ambiente di sviluppo.
- Sostituito il README generico di Create React App con documentazione specifica.

## Compatibilità

Gli hash esistenti e le viste non sono stati eliminati. I collegamenti diretti continuano a usare gli stessi identificativi (`#lotti`, `#gelati`, `#fornitori`, ecc.).

## Verifiche

- Backend compilato con `python -m compileall backend`.
- Ricerca globale dei riferimenti al vecchio ambiente: nessun risultato residuo.
- La build frontend non è stata completata nel contenitore perché l'installazione delle dipendenze dal lockfile ha superato il limite operativo; eseguire `npm ci` e `CI=false npm run build` prima del push.
