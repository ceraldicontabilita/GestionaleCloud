# Patch: PayPal API Reporting Integration

## File creati
1. `app/services/paypal_api_client.py` — Client OAuth2 PayPal con token cache
2. `app/services/paypal_api_sync.py` — Sync incrementale con upsert + pattern PagoPA
3. `app/routers/paypal_api.py` — Endpoint: /sync, /sync/month, /status

## File modificati
1. `app/config.py` — Aggiunti PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET
2. `app/router_registry.py` — Registrato paypal_api router
3. `app/database.py` — Indici paypal_transactions

## Post-deploy
1. Aggiungere al .env: PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=...
2. Creare app REST su https://developer.paypal.com/dashboard/applications/live
3. Abilitare permesso "Transaction Search"
4. Testare: POST /api/paypal-api/sync {"start_date":"2025-04-01","end_date":"2025-09-30"}

## Endpoint
- POST /api/paypal-api/sync — sync periodo custom
- POST /api/paypal-api/sync/month — sync mese corrente  
- GET /api/paypal-api/status — conteggi e ultimo sync
