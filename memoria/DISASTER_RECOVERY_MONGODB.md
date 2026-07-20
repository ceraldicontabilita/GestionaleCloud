# Disaster recovery MongoDB Atlas

## Stato e confini

Il database canonico è MongoDB Atlas, database `Gestionale`. Le collection di
backup create da singole funzioni applicative proteggono alcune cancellazioni,
ma **non sostituiscono** un backup Atlas dell'intero database.

Questa procedura non dichiara attivo ciò che non è stato verificato nella
dashboard Atlas. Frequenza, retention, RPO e RTO sono parametri operativi da
approvare; non vengono modificati dal repository.

## Regola vincolante

- Il ripristino di prova avviene sempre su un cluster o database temporaneo,
  mai sopra `Gestionale`.
- Gli utenti usati per il collaudo hanno sola lettura sul rispettivo database.
- Le URI restano nel password manager o nelle variabili d'ambiente locali:
  mai in chat, file, log, commit o comandi condivisi.
- Il database live non viene scritto, rinominato, cancellato o sostituito.
- Un ripristino sulla produzione richiede approvazione umana separata, finestra
  di manutenzione e piano di rollback.

## Verifica periodica in Atlas

1. Aprire Atlas → progetto del cluster canonico → **Backup**.
2. Confermare visivamente che i backup siano abilitati e che esista almeno un
   punto di ripristino recente. Annotare solo data/ora e stato, mai credenziali.
3. Controllare retention e copertura rispetto a RPO/RTO approvati.
4. Avviare il restore del punto scelto verso una destinazione temporanea e
   distinta. Non usare l'opzione che sovrascrive il cluster live.
5. Creare due utenti temporanei `read` con ambito sul solo database sorgente e
   sul solo database ripristinato; revocarli al termine del collaudo.

## Confronto automatico sola-lettura

Impostare localmente, senza stamparne i valori:

```text
DR_SOURCE_MONGO_URL
DR_RESTORE_MONGO_URL
DR_SOURCE_DB_NAME=Gestionale
DR_RESTORE_DB_NAME=<database temporaneo>
```

Eseguire:

```bash
python scripts/verifica_ripristino_mongodb.py --output rapporto-dr.json
```

Il rapporto contiene soltanto nomi delle collection, conteggi, differenze di
indici e hash SHA-256 di un campione deterministico. Non contiene documenti,
URI o password. Esito `ok: true` significa che inventario, conteggi, indici e
campione confrontato coincidono; non sostituisce i controlli funzionali.

## Controlli funzionali sulla copia

Con un backend temporaneo collegato esclusivamente alla copia ripristinata:

1. `GET /api/health` deve riportare `database: connected`.
2. Login con account di collaudo, mai con credenziali di produzione condivise.
3. Verificare in sola lettura fatture, prima nota, scadenze, F24 e allegati.
4. Verificare che indici univoci e TTL attesi siano presenti.
5. Non avviare scheduler, import email/Drive, riconciliazioni o agenti sulla
   copia: potrebbero produrre effetti esterni o duplicare dati.

## Evidenze e chiusura

Registrare data del punto di ripristino, durata restore, esito dello script,
controlli funzionali e scostamenti. Non allegare dati aziendali o segreti.
Dopo l'accettazione, eliminare la destinazione temporanea e revocare gli utenti
di collaudo. La cancellazione della copia richiede una conferma esplicita nella
dashboard Atlas.

## Fallimento e rollback

- Se il restore Atlas fallisce, il database live resta invariato: aprire un
  incidente e ripetere su una nuova destinazione temporanea.
- Se il confronto rileva differenze, non promuovere la copia e non modificare
  la produzione; conservare il solo rapporto privo di dati sensibili.
- Se un controllo funzionale fallisce, fermare il backend temporaneo e
  investigare configurazione, indici e compatibilità applicativa.
