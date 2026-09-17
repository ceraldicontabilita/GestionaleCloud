---
name: collaudo-funzionale
description: Verifica end-to-end di un flusso dell'app con dati di prova reali sul backend live (poi ripuliti). Usare quando il titolare chiede "controlla se funziona X" (es. scarico magazzino, riordino automatico, doppio tap). Riusabile su tutte le app del gruppo Ceraldi.
---

# Collaudo funzionale E2E (metodo Ceraldi)

1. NON fidarsi della lettura del codice da sola: il titolare vuole la PROVA sul vivo.
2. Crea un'entità di test riconoscibile ("ZZZ TEST ..." — la pulizia dati rimuove
   automaticamente \btest\b|\bzzz\b|\bprova\b), MAI toccare dati di produzione.
3. Esegui il flusso VERO via API autenticata, passo per passo, verificando dopo ogni
   passo lo stato reale (stock, stati, documenti creati). Testa anche i casi limite:
   quantità superiore allo stock, doppio tap (idempotenza/claim atomico), campi vuoti.
4. Esempio (magazzino Lotti): prodotto test → carico 1 → richiesta 2 colli → evadi →
   attesi: stock 0 + avviso scostamento, secondo tap respinto, bozza riordino creata
   con richiesto_da. Poi elimina bozza e prodotto di test.
5. Riporta al titolare l'esito passo-passo con i valori osservati (non "dovrebbe
   funzionare": numeri veri). Se un passo fallisce → è un bug da correggere subito.
