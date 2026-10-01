# Colazioni B&B: accesso cliente e recensioni

Il flusso vive dentro `/convenzioni/`, nella scheda della colazione creata
dall'albergatore. Non richiede un'app:

1. l'albergatore invia il link al cliente con WhatsApp oppure copia il link
   dedicato su una targhetta NFC; sono disponibili anche QR e Wi-Fi;
2. la pagina registra struttura partner, fonte, timestamp e versione
   dell'informativa;
3. geolocalizzazione e WhatsApp sono due consensi separati, inizialmente non
   selezionati e revocabili;
4. il numero WhatsApp viene validato e cifrato dal backend prima di essere
   salvato; la posizione viene rimossa alla revoca;
5. dopo il consumo, il job `convenzioni_recensioni` invia il template Meta con
   i link Google e Tripadvisor, senza incentivi.

## Configurazione

La funzione rimane fail-closed con `WHATSAPP_REVIEW_PROVIDER=disabled`.
Per attivarla su Render servono, come segreti e senza inserirne i valori nel
repository:

- `WHATSAPP_REVIEW_PROVIDER=meta`
- `WHATSAPP_REVIEW_PHONE_NUMBER_ID`
- `WHATSAPP_REVIEW_ACCESS_TOKEN`
- `WHATSAPP_REVIEW_DATA_KEY` (32 byte, codificati come 64 caratteri hex)
- un template Meta approvato chiamato, per default,
  `ceraldi_review_invite`, lingua `it`, con tre parametri body: struttura,
  link Google e link Tripadvisor.

Gli URL recensione, il ritardo e la versione dell'informativa si gestiscono
in `bb_config` (`review_google_url`, `review_tripadvisor_url`,
`review_invite_delay_minutes`, `privacy_notice_version`,
`privacy_notice_url`).

## Rilascio

Applicare la migrazione `20261001143000_convenzioni_consensi_recensioni.sql`
prima di attivare il provider. Il codice può essere distribuito anche con il
provider disattivato: QR/NFC/Wi-Fi, consensi, revoche e pulsanti recensione
restano disponibili; non viene reclamato né perso alcun invito in coda.
