# Area Drive "Estratti conto" — cartelle e fonti (07/08/2026)

Scelta dell'utente, definitiva: **una sola cartella di ingresso**, non una
per fonte. Testuale: *"ho messo in elaborare tutti i documenti degli estratti
conto pdf ed excel, csv per non perdere la testa tra pos bnl, pos bpm,
estratti ordinari avrei avuto molte cartelle"*.

## Struttura da sincronizzare

```
Estratti conto/            <- radice, ID nel registro Drive (area estratti_conto)
├── Da elaborare/          <- UNICO inbox: qui arriva tutto
├── Elaborate/             <- destinazione dopo l'import riuscito
└── Errori/                <- destinazione se l'import fallisce o la fonte e' ignota
```

Gli ID non stanno in questo file: vivono in `DRIVE_FOLDER_REGISTRY_JSON`
(area `estratti_conto`), oppure in `GOOGLE_DRIVE_ESTRATTI_FOLDER_ID(S)`.
Il registro non li espone via API — vedi `drive_folder_registry.py`.

Le vecchie strutture per fonte (`POS BPM/`, `POS BNL/`, `Carta Nexi/`, `BPM/`,
`BNL/`, ciascuna col proprio ciclo) **continuano a funzionare**: se il
percorso dichiara la fonte, comanda il percorso. Chi non le ha piu' non
perde niente.

## Cosa contiene davvero l'inbox

Sei fonti diverse, tutte mescolate:

| Fonte | Come si presenta | Dove finisce |
|---|---|---|
| **POS terminali (Numia)** | `Export_Mensile_<mese>_<anno>.csv`, `Export_Transazioni_<mese>_<anno>.xlsx` | chiusure POS reali |
| **Commissioni POS** | `Commissioni_<mese>_<anno>.xlsx` | costi commissioni |
| **PayPal** | `<codice>-MSR-<da>-<a>.PDF`, `<codice>-CSR-...PDF` | estratti PayPal |
| **Carta di credito Nexi** | `Estratto_Conto*.pdf`, `nexi <mese> <anno>.pdf`, `Movimenti carta_*.pdf` | movimenti carta |
| **Banca BPM / BNL** | `ElencoEntrateUsciteAndamento_*.csv`, `ESTRATTO <anno>.csv`, `Movimenti_BNL_BPM_unificati.xlsx`, `*BNL*cc 3192.pdf`, `Estratto conto corrente_*.pdf` | estratto conto banca |
| **Mutuo** | `Estratto mutuo_*.pdf` | documenti mutuo |

## Come si riconosce la fonte

`app/services/classificazione_estratti.py`, in quest'ordine:

1. **il percorso**, se ancora dice la fonte (retrocompatibilita');
2. **il nome del file**, ma solo con segni che una fonte usa e le altre no
   (`Export_Mensile_`, `-MSR-`, `Estratto mutuo`, `nexi`, `ElencoEntrateUscite`);
3. **il contenuto**, per i PDF e i CSV che si chiamano tutti allo stesso modo.

`estratto conto` da solo **non e' un segno**: lo scrivono tutti. Il report
PayPal si intitola letteralmente *"Estratto conto bancario per marzo 2025"* e
quello della carta *"il suo estratto conto Nexi"*. Per questo il contenuto si
controlla nell'ordine Nexi → PayPal → mutuo → banca.

**Un documento non riconosciuto non viene indovinato**: va in `Errori` con il
motivo scritto. Attribuire la fonte a caso significherebbe, per esempio,
registrare le spese Amazon della carta di credito come uscite dal conto
corrente — soldi mai usciti dalla banca.

## Il bug che questa struttura aveva creato (corretto il 07/08/2026)

Finche' la fonte si deduceva dalla cartella, l'inbox unico rendeva
l'importatore cieco:

- non entrava nemmeno dentro `Da elaborare`, perche' ci entrava solo quando
  il percorso aveva gia' dichiarato una fonte;
- gli export dei terminali non venivano riconosciuti: **ecco perche' diversi
  mesi risultavano senza POS reale**;
- i report PayPal non venivano riconosciuti;
- e una regola di ripiego dava per bancario qualunque file col nome che
  conteneva "estratto": l'estratto della carta di credito Nexi sarebbe
  entrato in estratto conto banca.

Test di guardia: `tests/test_classificazione_estratti.py`, scritti sui nomi
reali di questa cartella.

## Nota sugli accrediti NUMIA (da approfondire)

L'export BPM (`ESTRATTO <anno>.csv`) contiene gli accrediti POS con il giorno
di vendita nella causale:

```
INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 16/07/26 PDV 3757283/00012
INC.POS CARTE CREDIT - NUMIA-AMEX DEL 16/07/26 PDV 3757283/00012
```

Sommando per `DEL <data>` si ricostruisce il lordo Numia del giorno di
vendita, perche' Numia accredita il lordo. E' una fonte **derivata**: vale
meno dell'export del terminale e va registrata come tale, mai al posto suo
quando l'export c'e'.
