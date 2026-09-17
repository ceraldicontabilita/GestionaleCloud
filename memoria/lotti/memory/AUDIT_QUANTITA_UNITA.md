# AUDIT QUANTITÀ E UNITÀ DI MISURA (24/07/2026)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Convenzioni per collection (VERIFICATE): lotti_fornitori.quantita_disponibile
= unità GREZZE di fattura (kg/CT/PZ, unità vera in unita_misura);
magazzino_bar_prodotti.stock = SEMPRE pezzi; vendite_banco = pezzi;
dizionario.quantita_disponibile_kg/prezzo_kg = equivalente kg (l 1:1).

## GIÀ CORRETTO (verificato)
- Motore import unico xml_helpers.calcola_prezzo_quantita_kg (+test):
  g/ml÷1000, cl÷100, l 1:1, moltiplicatore cartone X24 sui prezzi.
- Cartoni→pezzi SIMMETRICO in magazzino_unificato (lettura e scarico stesso
  helper pezzi_per_collo dal nome riga).
- FIFO ricette: conversione kg↔g↔l↔ml↔pz con peso_pezzo (fix storico uova);
  ripristino simmetrico; mai negativi.
- Regola Enzo "bevande a cartone/unità MAI a kg": fonte unica
  utils.CATEGORIE_BEVANDE_A_UNITA, applicata al confronto fornitori.
- _riordini_post_produzione NON scrive kg falsi sui non-convertibili.

## PROBLEMI (da sistemare — ordine di priorità)
1. ALTA (condizionale) lotti_produzione.py:1056-1059 — unità NON convertibili
   (lotto in CT, o PZ senza peso_pezzo_g) → confronto numero-contro-numero:
   ricetta "500 g" può scalare 500 CT/PZ. Mitigato dai pesi censiti; il
   motore resta indifeso. FIX PROPOSTO: se non convertibile, non scalare e
   segnalare (ora c'è ingredienti_insufficienti come veicolo).
2. MEDIA magazzino_unificato.py:500-535 — cascata FIFO multi-lotto usa il
   fattore-collo del SOLO lotto cliccato anche sui fratelli a fattore/unità
   diversi.
3. MEDIA food_cost.py:1823-1834 e :3238 — food-cost ricetta usa prezzo_kg
   anche per le bevande (regola bevande-a-unità non applicata lì).
4. MEDIA food_cost.py:3172-3199 converti_in_kg — non gestisce cl (errore
   ×10) né cf; stesso buco in :1593-1600.
5. MEDIA food_cost.py — default inventati: 50 g/pezzo e peso_confezione=1.0
   ("1 confezione = 1 kg") quando manca il peso reale (mitigati dalla coda
   "prodotto_senza_peso"). MAI aggiungere altre conversioni automatiche
   senza peso reale.
6. BASSA — secondo motore prezzo_kg nel sync dizionario senza moltiplicatore
   X24 (tamponato dal cap 5000); euristica quantita<=1 in lotti_fornitori;
   densità liquidi 1:1 (accettata, documentata).

## CORREZIONI APPLICATE

- §1 FATTO (tranche 4, 24/07/2026): unità non convertibili → il lotto NON
  viene scalato ed esce in `conversioni_non_disponibili` (toast sul tablet).
- §2 FATTO (25/07/2026, magazzino_unificato.py): la cascata FIFO usa ora il
  fattore-collo di OGNI lotto (`_fatt_di`), non più quello del solo lotto
  cliccato; tutto il calcolo avviene nell'unità mostrata all'operatore. I
  lotti non confrontabili (sfuso a kg quando la lista mostra pezzi, o unità
  diversa) restano FUORI dalla cascata invece di essere mal convertiti.
  Test: test_e2e_flussi.py::test_cascata_multilotto_usa_il_fattore_di_ogni_lotto
  e ::test_cascata_non_tocca_lotti_non_confrontabili.
- §3 FATTO (25/07/2026, food_cost.py): regola bevande applicata anche al food
  cost delle ricette — nuovo `_e_bevanda_a_unita` (categoria dal dizionario,
  altrimenti dedotta col classificatore del listino). Per una bevanda il costo
  esce dal prezzo a bottiglia/cartone; se quel prezzo manca il costo NON viene
  inventato: riga con `costo_non_calcolabile` e segnalazione tra gli
  ingredienti da sistemare.
- §4 FATTO (25/07/2026, food_cost.py): `cl` (÷100) e `dl` (÷10) in entrambi i
  motori di conversione; le unità a confezione (nuovo `UNITA_A_CONFEZIONE`:
  cartone, cassa, bottiglia, collo…) non vengono più divise per 1000 come se
  fossero grammi — tornano 0 e chi chiama deve dichiararlo non calcolabile.
  Test: tests/test_quantita_unita.py (9 test puri).

## RIMASTO APERTO
- §5 default 50 g/pezzo quando manca `peso_pezzo_g` (per gli ingredienti a
  pezzo diversi da uova/tuorli/albumi): resta, ma ora non riguarda più le
  confezioni. Regola confermata: MAI aggiungere altre conversioni automatiche
  senza il peso reale.
- §6 BASSA: secondo motore prezzo_kg nel sync dizionario senza moltiplicatore
  X24 (tamponato dal cap 5000); densità liquidi 1:1 (accettata).

Stato: fix 1-4 CHIUSI con test; restano §5 (default 50 g) e §6 (bassa).
