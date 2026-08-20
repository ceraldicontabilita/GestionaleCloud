# Audit Drive fiscale e codici tributo — 10 agosto 2026

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Esito iniziale

- Le cartelle fiscali erano risolte da ID statici senza verifica della radice.
- Lo scheduler rieseguiva una scansione completa ogni ora.
- Non esistevano token `changes`, storico delle sincronizzazioni o marcatura della rimozione dalla fonte.
- I codici tributo erano descritti da una tabella statica non versionata.

## Correzioni

- La radice fiscale viene verificata con Drive `files.get`.
- `Avvisi bonari` e `Cartelle esattoriali` sono cercate ricorsivamente e accettate solo se univoche.
- Gli ID verificati sono persistiti nel registro interno e non esposti nelle API pubbliche.
- Il primo ciclo esegue una scansione completa; i successivi usano Drive Changes e un page token persistente.
- Un file rimosso dalla fonte riceve `source_deleted_at`: nessun documento fiscale viene cancellato.
- Il registro codici tributo importa la tabella ufficiale AdE, la valida, la versiona tramite SHA-256 e conserva le esecuzioni.
- Un codice è utilizzabile dal motore solo quando lo stato è `verified`.

## Limiti operativi verificabili

La scoperta reale necessita delle credenziali Drive dell'ambiente di produzione. In loro assenza il servizio fallisce in modo esplicito e non inventa cartelle o associazioni.
