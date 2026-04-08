# DIARIO.md — Ceraldi ERP gestionale2

## Chat 4 — Fix bug, 2 tab mancanti, push backend

### Fix applicati
- App.jsx: route mancanti tributi, alert-fiscali, fornitori, f24-privati
- TopNav.jsx: import duplicati, Building2 mancante
- tributi.py: import PRIVATI_CF/CF_AZIENDA mancante
- main.py: prefix doppio su tributi e f24_privati

---

## Chat 5 — 3 pagine HACCP nel gestionale2

### Pagine create e pushate
Le 3 pagine leggono le API di `ceraldiapp.it` (repo tracciabilita).
Prima di costruire: letti tutti e 4 i router backend (temperature_positive, temperature_negative, sanificazione, disinfestazione).

**frontend/src/pages/TemperatureHACCP.jsx**
- Tab interno: Frigoriferi (+) e Congelatori (−)
- Chiama GET `/temperature-positive/scheda/{anno}/{n}` e `/temperature-negative/scheda/{anno}/{n}` per tutti i 12 apparecchi
- Griglia: giorni come righe, apparecchi come colonne
- Legge stati speciali: is_chiuso 🚫, is_manutenzione 🔧, is_non_usato ⏸
- Badge "fuori range" se temp > max o < min
- CSS inline con design system utils.js

**frontend/src/pages/SanificazioneHACCP.jsx**
- Tab "Attrezzature": griglia mensile toggle X, pulsanti "marca tutto giorno N" → POST `/giorno-completo`, salva bulk → PUT `/scheda/{anno}/{mese}`
- Tab "Apparecchi Refrigeranti": read-only, griglia frigo+congelatori con ✓/✗ per sanificazioni ogni 7-10 giorni

**frontend/src/pages/DisinfestazioneHACCP.jsx**
- Intervento mensile: card + pulsante "Registra/Modifica" → POST `/registra-intervento/{anno}/{mese}`
- Cards frigoriferi/congelatori cliccabili → modal → POST `/registra-monitoraggio/{anno}/{mese}`
- Riepilogo annuale: griglia 12 mesi, click mese per navigare
- Ditta: ANTHIRAT CONTROL S.R.L., giorno fisso 15

### Modifiche a file esistenti
- App.jsx: aggiunte 3 route `/haccp/temperature`, `/haccp/sanificazione`, `/haccp/disinfestazione`
- TopNav.jsx: aggiunti 3 link 🌡️ Temp, ✨ Sanif., 🐀 Disinfest. con icone Thermometer, Sparkles, Bug

### Commit pushati (Chat 5)
- 63030da — feat: aggiunte 3 route HACCP in App.jsx
- 9ee8358 — feat: aggiunti 3 link HACCP in TopNav
- 66ec17d — feat: TemperatureHACCP.jsx
- 1d12ece — feat: SanificazioneHACCP.jsx
- 7648ce3 — feat: DisinfestazioneHACCP.jsx
