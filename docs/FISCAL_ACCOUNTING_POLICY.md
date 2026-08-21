# Policy contabile fiscale documentale

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> Vista specialistica subordinata a `PROMPT_MASTER.md`, unica specifica
> normativa del GestionaleCloud.


Questa policy non registra scritture definitive. Dal PDF costruisce una
`journal_proposal` con fonte, versione parser, righe in centesimi, sezione di
bilancio candidata e stato di deducibilita'. La registrazione richiede
approvazione del commercialista e la relazione bidirezionale fra documento,
obbligazione, prova di pagamento e banca.

## Regole applicate ai campioni audit

| Documento/codice | Natura | Bilancio candidato | Deducibilita' automatica |
|---|---|---|---|
| F24 modello | predisposizione | nessuna scrittura | bloccata: non prova pagamento |
| 1040 | chiusura debito ritenute | Passivo D12 | non e' un costo nuovo |
| 7085 | tassa libri sociali | CE B14 / Passivo D12 | da verificare competenza e contabilizzazione pregressa |
| 3918 IMU | tributo locale/ravvedimento | CE B14 / Passivo D12 | da verificare immobile, uso e dettaglio ravvedimento |
| 3813 IRAP | acconto | credito/debito IRAP | da verificare liquidazione e periodo |
| 1993 | interesse ravvedimento | C17 o sottoconto dedicato | da verificare |
| 8907 | sanzione IRAP | B14 separato | indeducibile salvo diversa valutazione professionale |
| 1701/1704 | credito fiscale | Attivo CII | non e' IVA ne' costo; origine/residuo obbligatori |
| 1075 | codice non validato | nessuna | bloccato fino a validazione annuale |
| Nota rettifica INPS | obbligazione | Passivo D12 e costi separati | da verificare esercizio/OIC 29 |
| Avviso PagoPA/verbale | richiesta di pagamento | nessuna finche' non definita responsabilita' | nessun pagamento provato |

Le etichette “deducibile/indeducibile” non sostituiscono il giudizio sul caso
concreto: periodo d'imposta, natura del costo, uso del bene, registrazioni
precedenti, base IRES/IRAP e documentazione possono cambiare il trattamento.
Il sistema quindi espone `DEDUCIBILE`, `INDEDUCIBILE`, `LIMITATA` o
`DA_VERIFICARE` come esito versionato, senza trasformarlo in scrittura.

## Fonti di riferimento

- [Agenzia Entrate: codice 1040](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=1040&Ord=0492&Q1=Tutte&Q2=&Q3=IRPEF&Q4=Tutte)
- [Agenzia Entrate: codice 7085](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=7085&Ord=2487&Q1=&Q2=&Q3=&Q4=Tutte)
- [Agenzia Entrate: codice 1075](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=1075&Ord=0526)
- [OIC 25 - Imposte sul reddito](https://www.fondazioneoic.eu/wp-content/uploads/2011/02/2024-03-OIC-25-Imposte-sul-reddito.pdf)
