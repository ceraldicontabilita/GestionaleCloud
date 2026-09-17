---
name: bonifica-design
description: Verifica e ripristina la coerenza del design in tutte le pagine (colori, centratura, mobile). Usare quando una pagina "non è come la dashboard", sborda dallo schermo o ha colori fuori palette. Riusabile su tutte le app del gruppo Ceraldi.
---

# Bonifica design (metodo Ceraldi)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Palette ufficiale (design_handoff/)
Salvia #5b7a6b (dark #3f5a4e, gradiente 135° #5b7a6b→#6f9180), crema #faf7f0, card
#fffefb, bordi #e6e0d4. Semantici caldi: danger #d35f4e, warning #c4894a, success
#3d8168, info sabbia #8a6f47. VIETATI: blu, indaco, viola (e ogni resto di
#5D29C7/#1E1B4B/#7c3aed/violet-*/indigo-*/sky-*). Icone Lucide, niente emoji nelle UI nuove.

## Scansione colori
`grep -rEn "5D29C7|1E1B4B|7c3aed|8b5cf6|6366f1|4f46e5|violet-|indigo-|bg-blue-|bg-sky-"`
su src/ (jsx/js/css) e sui PDF generati dal backend (reportlab HexColor). Rimappa con
la tabella salvia/sabbia/ambra; verifica il bundle buildato = zero occorrenze.
Mai usare stringhe accentate come marcatori nel bundle minificato (vengono escapate).

## Layout mobile (regole)
- Ogni pagina: contenitore centrato `maxWidth` (900-1100) + `margin: 0 auto`.
- MAI tabelle larghe su mobile: righe → card impilate (titolo+badge sopra, campi e
  azioni sotto, flexWrap). Se una tabella è irrinunciabile: prima colonna leggibile
  e scroll consapevole, ma preferire SEMPRE le card.
- Tap target ≥ 44px, press scale(.97), stati vuoti sempre dichiarati con testo.
- Collaudo: genera il file `collaudo_pagine.html` (link cliccabili a OGNI pagina con
  checklist: centrata / no scroll orizzontale / colori ok) e consegnalo al titolare.
