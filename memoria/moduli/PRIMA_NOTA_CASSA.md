# Prima Nota Cassa — stato reale vs specifica

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi Mongo/collection restano compatibilità o contesto storico.

Fonte specifica: `Prima Nota Cassa — Flussi automatici.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Corrispettivi → cassa SOLO quota contanti (mai POS) | ✅ nel percorso principale, ⚠️ VIOLATO in un percorso legacy | Corretto in `app/routers/invoices/corrispettivi_helpers.py::_create_prima_nota_movements` (righe 144-214: cassa riceve solo `contanti`, la quota POS va su `prima_nota_banca` separatamente) — usato da `upload-xml`/`upload-xml-bulk` |
| Trasferimenti banca↔cassa come movimenti interni (non costi/ricavi) | ✅ | `app/services/handlers/trasferimento_handlers.py` — `categoria: "trasferimento_interno"`, esclusi dalla categorizzazione normale entrata/uscita |
| Fatture pagate in contanti → cassa | ✅ (percorso principale) | stessa pipeline di `auto_registra_prima_nota()` in `fatture_upload.py` (vedi `FATTURE_RICEVUTE.md`) |

## Gap confermati (in ordine di priorità)

1. ~~**Bug critico: un endpoint legacy VIOLA la regola "mai la quota POS in cassa"**~~ —
   **RISOLTO**. `POST /sincronizza-prima-nota` in `corrispettivi.py` scriveva l'importo
   `totale` completo (incluso l'incasso POS) in `prima_nota_cassa`. Corretto: ora scrive
   solo `dettaglio["contanti"]`, coerente con `corrispettivi_helpers.py`.
2. **Codice morto/parallelo per lo stesso calcolo**:
   `app/services/corrispettivi_service.py::CorrispettiviService._create_prima_nota_entry`
   (righe 370-422) implementa una terza variante (netta corretta ma diversa architettura:
   registra `entrata=totale` poi un'`uscita` compensativa per la quota POS) — esportata in
   `app/services/__init__.py` ma **mai istanziata da nessuna parte** (`CorrispettiviService()`
   ha zero chiamanti reali). Tre implementazioni indipendenti dello stesso calcolo, di cui
   solo una è sia corretta sia viva.
3. ~ PARZIALE (lug 2026) — Solo 5 alert `CAS_*` definiti su 6 richiesti dalla spec.
   `CAS_DIFFERENZA_SALDO` è referenziato fuori da `alert_engine.py` solo per essere
   *risolto* (`trasferimento_handlers.py:76`), mai creato — non toccato in questo passaggio.
   ✔ RISOLTO ora `CAS_DUPLICATO`: generato in `prima_nota_module/sync.py::
   create_movimento_generico()` (endpoint di inserimento manuale movimento cassa/banca)
   quando esiste già un movimento cassa con stessa data+tipo+descrizione+importo. Additivo:
   non blocca l'inserimento (l'utente potrebbe intenzionalmente registrare due movimenti
   identici), solo lo segnala — verificato con mongomock: alert corretto sul duplicato
   esatto, nessun falso positivo su movimento banca (fuori scope di questo alert), il
   secondo movimento viene comunque salvato. Restano morti `CAS_SENZA_CAUSALE`,
   `CAS_FAT_CONTANTI_NON_REGOLATA`, `CAS_CORRISPETTIVI_INCOERENTI` — richiedono
   rispettivamente: una definizione più precisa di "causale mancante" (il modello oggi ha
   solo `descrizione` obbligatoria e `categoria` con default "Altro", nessun vero campo
   causale distinto), un confronto fatture-a-pagamento-contanti vs cassa non ancora
   costruito, e un tracciamento della quota contanti dei corrispettivi che non risulta
   ancora esistere in questo repo.
4. **`CAS_FAT_CONTANTI_NON_REGOLATA` mai generato**: quindi anche se una fattura fosse
   configurata a pagamento contanti ma non risultasse mai regolata in cassa, non esiste
   oggi alcuna segnalazione automatica di questa condizione.

## Bug/incoerenze note (da correggere)

- **Priorità 1**: `corrispettivi.py::sincronizza-prima-nota` va disattivato o corretto per
  usare la stessa logica di split contanti/POS di `corrispettivi_helpers.py` — è l'unico bug
  di questo documento con impatto contabile diretto e concreto (cassa gonfiata dell'incasso
  POS se questo endpoint viene chiamato).
- Consolidare le 3 implementazioni del calcolo contanti/POS in una sola funzione condivisa,
  eliminando `CorrispettiviService._create_prima_nota_entry` se confermato davvero senza
  chiamanti.
