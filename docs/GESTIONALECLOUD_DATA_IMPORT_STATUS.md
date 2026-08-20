# GestionaleCloud - stato importazione dati

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data verifica: 2026-08-10. `NON_VERIFICATO_CORRENTE` significa che la produzione e il DB rispondono, ma la sessione amministrativa necessaria per leggere conteggi e record non era disponibile durante l'audit.

| DATASET | PRESENTE_NEI_FILE | IMPORTATO_DB | RICONCILIATO | PROVE | AZIONE |
|---|---|---|---|---|---|
| `CERALDI_GROUP_FISCALE_CODEX_COMPLETO_2020_2026_V2.zip` | SI: 450 file, 436 PDF, 2 XLSX, manifest/indici | PARZIALE / NON_VERIFICATO_CORRENTE | PARZIALE | zero hash dei 436 PDF nella inventory Drive 04/08; DB 05/08: 48 F24/130 quietanze | Dry-run per SHA-256 e confronto DB/Drive corrente. |
| `CERALDI_GROUP_ARCHIVIO_FISCALE_CODEX_2020_2026.zip` | SI: 453 file, 436 PDF, 2 XLSX | PARZIALE / NON_VERIFICATO_CORRENTE | PARZIALE | 446 hash condivisi col V2; 7 esclusivi dello storico | Conservare come fonte storica; non sostituire il V2 alla cieca. |
| Dichiarazioni 770/IVA/IRAP/Redditi/LIPE 2020-2026 | SI: indice di 61 documenti dichiarativi, piu' componenti | NON_PROVATO | NON_PROVATO | indici e SHA presenti nei due ZIP | Import versionato con protocollo, periodo, pagina e documento origine. |
| Operazioni F24 portale 2020-2026 | SI: 302 operazioni | PARZIALE | PARZIALE | manifest dichiara copertura 302/302; DB storico aveva 48 F24 | Confronto per protocollo/hash/riga; non per importo solo. |
| PDF F24/quietanze | SI: 320 PDF (301 quietanze AE, 19 formati stampabili) | PARZIALE | PARZIALE | DB storico aveva 130 quietanze; banca non provata integralmente | Import idempotente e collegamento banca separato. |
| `Archivio_Fiscale_COMPLETO_con_F24_2026_e_Crediti.xlsx` | SI: 10 fogli; 1.296 righe F24, 321 indice PDF, 502 situazione tributi | NO, file di staging | PARZIALE NEL FILE | hash identico alla copia nel V2; nessuna formula | Usare per confronto, mai come prova autonoma di import/pagamento. |
| `Situazione_Fiscale_PULITA_con_2026_e_Crediti.xlsx` | SI: 4 fogli, 502 righe situazione | NO, file di staging | PARZIALE NEL FILE | hash identico alla copia nel V2 | Validare contro PDF, DB e banca. |
| `Riconciliazione_Tributi_Commercialista_vs_Pagamenti_Reali_CORRETTA.xlsx` | SI: 386 righe, 264 documentate, 123 da verificare | NON_PROVATO | PARZIALE NEL FILE | conserva regole e prove dichiarate; 0 formule | Reimportare solo come proposta/evidence mapping. |
| `Tributi_Fiscali_Ceraldi_Group_COMPLETO_2020_2026.xlsx` | SI: 13 fogli, 433 tributi attesi, 76 LIPE, 104 documenti | NON_PROVATO | PARZIALE NEL FILE | 48 formule di riepilogo; dati statici nel dettaglio | Trasformare in obblighi/crediti versionati con provenance. |
| `Situazione_Fiscale_Sintetica_2020_2026.xlsx` | SI: 386 righe + 103 ravvedimenti | NO, file di staging | PARZIALE NEL FILE | identico alla copia nell'archivio precedente | Solo controllo, non seed definitivo. |
| `Archivio_Fiscale_Codex_MASTER_2020_2026.xlsx` | SI: 386 master + indice inverso | NO, file di staging | PARZIALE NEL FILE | identico alla copia nell'archivio precedente | Riutilizzare regole/provenance, non valori non confermati. |
| `Tributi_Fiscali_Ceraldi_Group.xlsx` | SI: 24 righe, 14 formule | NO, versione ridotta | PARZIALE NEL FILE | dataset meno completo | `SUPERATO_DA_VERSIONE_PIU_RECENTE`; non importare separatamente. |
| 25 PDF cartelle/quietanze diretti | SI | DOCUMENTI DRIVE: SI STORICO; DOMINIO DB: NON_PROVATO | PARZIALE | 25/25 SHA-256 uguali a file `CARTELLE ESATTORIALI` nella inventory Drive 04/08; controllo PDF riuscito, uno quasi privo di testo | Evitare duplicati; OCR per il documento immagine; creare claim/eventi/relazioni. |
| Avvisi bonari Drive | cartella logica richiesta | NON_VERIFICATO_CORRENTE | NO | inventory 04/08 mostrava root separata con 0 PDF | Discovery live sotto root fiscale e import tramite `Documenti`. |
| Cartelle esattoriali Drive | SI storico: 35 PDF nella root separata | DOCUMENTI PRESENTI; MODELLO DOMINIO ASSENTE | PARZIALE | 25 fixture coincidono esattamente | Riscoprire sotto la root fiscale e importare struttura, non duplicare file. |
| Registro codici tributo AdE | codice e job presenti | NON_VERIFICATO_CORRENTE | n/d | endpoint live esiste ma richiede auth | Eseguire sync ufficiale e leggere versione/count. |
| Snapshot AdeR 10/08/2026 | SI: archivio annidato, SHA-256 `e5738d898d89fc4abab177566fb927026a5a71ee36c7b4ed2a9309a6f7475c0b` | NO | NO | 47 PDF; parser audit 43/43 analitiche; tre render visuali | Registrare prima l'archivio in `Documenti`, poi dry-run/import MFA idempotente. |
| 43 documenti AdeR (36 `Saldati`, 7 `Da saldare`) | SI, PDF analitici reali | NO | NO | importi e stati dei sette casi campione verificati | Importare snapshot immutabili; il bucket portale non prova il pagamento. |
| Piani AR071812706 / AR071904285 | SI, due PDF di accoglimento | NO | NO | 18 rate e 6 rate; riferimenti posizione stampati a 17 cifre | Risolvere contro le analitiche a 20 cifre solo con corrispondenza univoca. |
| Rottamazione-quater 07190202302172623000 | SI, comunicazione e documento collegato | NO | NO | importo definizione 126,68; la ricevuta bancaria non e' provata dal PDF di definizione | Stato fail-closed finche' una distinta evidenza bancaria/documentale non conferma il pagamento. |

## Verdetto

I file sono una base documentale ricca e coerentemente indicizzata, ma l'importazione integrale e la riconciliazione DB non sono dimostrate. Lo stato operativo resta `PARZIALE` fino a lettura DB corrente, import dry-run, conteggi post-import, relazioni bidirezionali e prova bancaria.
