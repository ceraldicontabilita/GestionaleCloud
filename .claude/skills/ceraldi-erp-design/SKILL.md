---
name: ceraldi-erp-design
description: Use this skill to generate well-branded interfaces and assets for Ceraldi ERP (the internal web ERP of Ceraldi Group SRL, Napoli), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files (tokens/, components/core/, guidelines/, ui_kits/ceraldi_erp/).

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view: link `styles.css`, load `_ds_bundle.js`, mount components from `window.CeraldiERPDesignSystem_9a014a`, and pull Lucide from CDN. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

Ground rules for staying on-brand: Italian copy; navy `#0f2744` + sober gold `#b8860b`; system sans for UI and system mono for numbers (`€ 1.234,56`); flat slate/white surfaces, no gradients; dense 13px tables with uppercase muted headers; left-accent-border page headers & stat boxes; Lucide icons; zero chromatic ambiguity (red=error, green=ok, gold=attention, blue=info).

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
