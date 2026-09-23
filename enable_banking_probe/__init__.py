"""# Banco BPM Real Probe

Isolated, read-only proof of access to a real Banco BPM business account through
Enable Banking's regulated PSD2 account-information flow.

## Boundaries

- separate Git branch and Render service
- no Supabase or GestionaleCloud database connection
- no payment-initiation endpoints
- bank credentials, PINs and OTPs stay on Banco BPM / Enable Banking pages
- Enable Banking application private key is read only from a protected environment variable
- session and account identifiers stay only in process memory and disappear on restart
- public pages (`/health`, `/probe`, `/result` for anyone else) expose only status flags and counts
- balances, transactions and the CSV comparison are shown only to the browser that completed
  the bank authorization (HttpOnly cookie issued by `/callback`, kept in memory)

## What it does

- reads every page of `/transactions` (`continuation_key`) for every authorized account,
  keeping only booked (`BOOK`) rows; pending and other statuses are counted, not imported
- stops on expired consent or bank rate limit, retries only temporary errors (3 attempts)
- sends the PSU headers on user-triggered reads so they do not use the daily background quota
- compares the API rows with an uploaded Banco BPM «Elenco entrate/uscite» CSV using the
  gestionale's own `app/services/doppioni_estratto_conto.accoppia` (loaded from its file):
  new / already present (same description or cheque number) / ambiguous (date and amount
  only, `DA_VERIFICARE`) / only in the CSV
- writes nothing anywhere

## Required protected environment variables

- `ENABLE_BANKING_APPLICATION_ID`
- `ENABLE_BANKING_PRIVATE_KEY_PEM`
- `ENABLE_BANKING_REDIRECT_URL`

The production application in Enable Banking must whitelist this callback:

`https://gestionalecloud-banco-bpm-probe.onrender.com/callback`

Registration support pages:

- Privacy: `https://gestionalecloud-banco-bpm-probe.onrender.com/privacy`
- Terms: `https://gestionalecloud-banco-bpm-probe.onrender.com/terms`
"""
