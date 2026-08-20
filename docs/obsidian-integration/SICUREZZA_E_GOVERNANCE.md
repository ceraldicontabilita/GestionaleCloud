# Sicurezza e governance

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Classificazione

| Classe | Esempi | Destinazione |
| --- | --- | --- |
| Pubblico | procedure già pubbliche | vault condivisibile |
| Interno | manuali e decisioni non sensibili | vault procedure |
| Riservato | contabilità, fornitori, pratiche | vault privato |
| Molto riservato | banca, personale, PEC, credenziali | solo metadati e link protetti |

## Regole

1. Nessuna password, token OAuth, cookie, chiave API o segreto nel Markdown.
2. PDF molto riservati restano nel repository documentale e sono aperti tramite URL autenticato.
3. Il vault privato non viene pubblicato.
4. La sincronizzazione remota usa cifratura end-to-end quando prevista.
5. La cifratura di Sync non sostituisce cifratura disco, backup e controllo degli account.
6. I plugin comunitari sono disabilitati per impostazione predefinita nel vault privato.
7. Ogni plugin proposto richiede revisione di codice, permessi, manutenzione e rete.
8. Gli agenti ricevono accesso al solo vault necessario, non all’intero computer.
9. Gli URL del Gestionale rispettano autorizzazioni e scadenza della sessione.
10. Log e note non riportano contenuti completi di documenti sensibili se non indispensabile.

## Autorità dei dati

Obsidian non può:

- registrare o correggere scritture contabili;
- confermare deducibilità IVA;
- dichiarare un pagamento verificato;
- riconciliare un movimento bancario;
- assegnare definitivamente un driver ambiguo;
- eliminare o spostare documenti originali;
- modificare lo stato giuridico o lavorativo di una persona.

Può:

- mostrare lo stato letto dal Gestionale;
- raccogliere annotazioni personali;
- creare bozze di attività o richieste di revisione;
- aprire la pagina corretta nel Gestionale;
- spiegare relazioni e provenienza.

## Backup e ripristino

- Backup periodico indipendente dal Sync.
- Manifest SHA-256 dei pacchetti di esportazione.
- Test di rigenerazione completa su ambiente isolato.
- Ripristino documentato del vault e delle annotazioni personali.
- Verifica periodica di collegamenti irrisolti e note orfane.

## Conservazione

La durata delle note segue le regole della sorgente. L’eliminazione nel Gestionale non comporta cancellazione silenziosa: la proiezione viene marcata archiviata o rimossa con evento di audit secondo la policy applicabile.
