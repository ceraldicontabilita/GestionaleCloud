# Handoff: Restyling app Lotti (Ceraldi Group — Tracciabilità HACCP)

## Obiettivo
Applicare al frontend reale (`frontend/src/` di questo repo) la nuova veste grafica del design system **Ceraldi Lotti**, SENZA cambiare logiche, route, API o flussi esistenti. L'app live è `https://lotti-frontend.onrender.com` (deploy automatico Render a ogni push su `main`).

**Regola n.1 di questo handoff: la grafica cambia, il comportamento no.** Ogni pagina esistente resta al suo posto con i suoi dati e le sue chiamate; si sostituiscono solo stili, colori, tipografia e componenti visivi. Le uniche AGGIUNTE funzionali richieste sono elencate in "Nuove funzioni".

## Cosa sono i file allegati
I file in questo pacchetto sono **riferimenti di design in HTML/JSX** (prototipo navigabile, dati fittizi): NON vanno copiati in produzione così come sono. Vanno usati come specifica visiva pixel-perfect per ricreare gli stessi stili nell'ambiente esistente (React 18 + classi `g-*` in `frontend/src/index.css` + Tailwind).

## Fedeltà
**Hi-fi**: colori, tipografia, spaziature, raggi e ombre sono definitivi. Replicarli esattamente.

## Fondamenta visive (token)
Fonte: `tokens/colors.css`, `tokens/typography.css`, `tokens/geometry.css` (allegati). Valori chiave:
- **Palette**: primario salvia `#5b7a6b` (dark `#3f5a4e`, gradiente brand `135deg #5b7a6b → #6f9180`), sfondo crema `#faf7f0`, card `#fffefb`, bordi `#e6e0d4` (subtle `#f0ebe0`).
- **Mai blu/indaco/viola**: ogni colore freddo esistente va rimappato su salvia/sabbia. Semantici caldi: danger terracotta `#d35f4e`, warning ocra `#c4894a`, success verde bosco `#3d8168`, info sabbia `#8a6f47` (ognuno con varianti soft/border/text nei token).
- **Tipografia**: Fraunces 500–700 per h1–h3 e valori stat; Plus Jakarta Sans 400–800 per tutto il resto. Body 15px/1.5. Label uppercase 10–11px peso 700–800, tracking .04–.06em.
- **Raggi**: 12 base (bottoni/input), 16 card, 20 modal, 999 pill. **Ombre tinte salvia** (es. card `0 2px 10px rgba(63,90,78,.06)`), mai grigie.
- **Tap target ≥ 44px**; press `transform: scale(.97)`.
- **Icone**: Lucide (`lucide-react`, già nel codebase). Niente emoji nelle UI nuove.
- L'header app resta scuro salvia (`#3f5a4e`); i bottoni sull'header usano `rgba(255,255,255,.12)` con testo bianco.

## Schermate di riferimento (cartella `ui_kit/`)
Aprire `ui_kit/index.html` per il prototipo navigabile. Mapping con il codice reale:
| Riferimento | File reale da restilizzare |
|---|---|
| `DashboardScreen.jsx` | `components/haccp/DashboardView.jsx` |
| `RicetteScreen.jsx` | `components/haccp/RicetteDashboardView.jsx` + `SchedaProdottoView.jsx` (eliminare i viola/emoji, usare categorie con icone Lucide e card come da riferimento) |
| `LottiScreen.jsx` | `components/haccp/LottiList.jsx` |
| `OrdiniScreen.jsx` | `public/ordini-app.html` (rimappare il tema viola `#5D29C7` su salvia; la logica carrello/giacenze esistente resta) |
| `FornitoriScreen.jsx` | `components/haccp/FornitoriList.jsx` |
| `HaccpScreen.jsx` | viste HACCP (`RegistroHACCPView`, `SanificazioneView`, `ControlloOlioView`, `DisinfestazioneView`, `TemperatureCotturaView`, `RicezioneMerceView`, `AnomalieView`, `TemperaturePositiveView`, `TemperatureNegativeView`) |
| `AppShell.jsx` | `App.js` (header + nav) |

## Nuove funzioni (uniche aggiunte di comportamento)
1. **Impostazioni stampanti di rete** (vedi `AppShell.jsx` di riferimento, modale "Impostazioni · Stampanti di rete"):
   - Elenco stampanti configurabili: nome, indirizzo IP, tipo (`etichette80` = etichette 80 mm, `pdf` = PDF A4). Default richiesti dal titolare:
     - Stampante Pasticceria · `192.168.001.025` · etichette 80 mm
     - Stampante Rosticceria / Cucina · `192.168.001.026` · etichette 80 mm
     - Stampante Ufficio · `192.168.001.030` · PDF A4
   - **Instradamento**: etichette lotti Pasticceria → stampante Pasticceria; etichette lotti Rosticceria → stampante Rosticceria/Cucina; registri HACCP e report → PDF; schede tecniche → PDF. Ogni voce modificabile.
   - Nel backend reale la configurazione va persistita su database (nel prototipo è `localStorage`, chiave `lotti_stampanti_cfg_v1`); la stampa etichette va inviata all'IP della stampante del reparto del lotto.
2. **Persistenza eliminazioni ordini**: la ✕ su righe e ordini sospesi deve cancellare sul database (nel prototipo: `localStorage`). Al ricaricamento l'ordine eliminato NON deve ricomparire.
3. **Note inline nel registro disinfestazione**: campo note editabile per ogni postazione, salvato.
4. **Fatture cliccabili nella scheda fornitore**: ogni fattura apre il PDF della fattura XML (endpoint già esistente nel backend per il dettaglio fattura); il filtro anno deve filtrare davvero i dati per anno.
5. **Operatori**: gli elenchi operatore mostrano gli operatori reali dal backend (oggi: Vincenzo Ceraldi, Pocci Salvatore) — niente nomi hardcoded.

## Interazioni e stati
- Hover primario: `opacity .9`; righe tabella: sfondo crema; press: `scale(.97)`.
- Animazioni micro .1–.2s ease-out; modal `scale(.95)→1` cubic-bezier(.34,1.2,.64,1); overlay `rgba(15,23,42,.55)` + blur 6px.
- Stati vuoti sempre dichiarati con testo (mai sezioni mute).
- Toast di conferma stampa: pill scura salvia in basso al centro, testo "«X» → Nome stampante (IP) · tipo".

## File nel pacchetto
- `ui_kit/` — prototipo navigabile completo (index.html + 7 JSX + data.js fittizio)
- `tokens/` — colors.css, typography.css, geometry.css, fonts.css, base.css (classi componente `g-*` di riferimento)
- `styles.css` — entry point CSS

## Come usarlo con Claude Code
Nel repo `ceraldicontabilita/Lotti`, scompattare questa cartella nella root (es. `design_handoff/`) e chiedere a Claude Code:
> "Applica il restyling descritto in `design_handoff/README.md` al frontend in `frontend/src/`, senza modificare logiche, route o API. Implementa anche le 5 nuove funzioni elencate."
Al push su `main`, Render rideploya automaticamente e su `lotti-frontend.onrender.com` comparirà la nuova grafica.
