# Banco BPM Real Probe

Isolated, read-only proof of access to a real Banco BPM business account through
Enable Banking's regulated PSD2 account-information flow.

## Boundaries

- separate Git branch and Render service
- no Supabase or GestionaleCloud database connection
- no payment-initiation endpoints
- bank credentials, PINs and OTPs stay on Banco BPM / Enable Banking pages
- Enable Banking application private key is read only from a protected environment variable
- session and account identifiers stay only in process memory and disappear on restart
- diagnostics expose only status flags and counts, never balances or transaction data

## Required protected environment variables

- `ENABLE_BANKING_APPLICATION_ID`
- `ENABLE_BANKING_PRIVATE_KEY_PEM`
- `ENABLE_BANKING_REDIRECT_URL`

The production application in Enable Banking must whitelist this callback:

`https://gestionalecloud-banco-bpm-probe.onrender.com/callback`

Registration support pages:

- Privacy: `https://gestionalecloud-banco-bpm-probe.onrender.com/privacy`
- Terms: `https://gestionalecloud-banco-bpm-probe.onrender.com/terms`
