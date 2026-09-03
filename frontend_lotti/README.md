# Frontend Ceraldi Group HACCP

Applicazione React per tracciabilità lotti, produzione, magazzino, acquisti e registri HACCP.

## Comandi

```bash
npm ci
npm start
```

Build di produzione:

```bash
CI=false npm run build
```

## Struttura principale

- `src/App.js`: shell applicativa e rendering delle viste.
- `src/config/navigation.js`: menu, nomi pagina, metadati e autorizzazioni.
- `src/components/haccp/`: moduli operativi.
- `src/hooks/`: caricamento e gestione dati condivisi.
- `public/`: file statici, guida e risorse cataloghi.

La navigazione principale contiene solo cinque aree: **Oggi**, **Produzione**, **Tracciabilità**, **Magazzino** e **Acquisti**. Le funzioni secondarie sono raggruppate nel menu **Altro**.
