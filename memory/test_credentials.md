# Test Credentials

## ERP Admin Access
- URL: https://food-cost-portal.preview.emergentagent.com
- No login required (direct access)

## Backend API
- Base: https://food-cost-portal.preview.emergentagent.com/api
- No auth required for standard endpoints

## MongoDB Atlas
- DB: azienda_erp_db
- Connection via MONGO_URL env var

## Portale Dipendenti
- URL: https://food-cost-portal.preview.emergentagent.com/portale
- Auth: Google Auth (Emergent-managed - auth.emergentagent.com)
- Dopo login Google: token salvato in localStorage come 'portal_token'
- Collection dipendenti: employees (con campo google_email)
- Collection contratti: employee_contracts
- Collection firme: documenti_firmati

## Tracciabilità Mini-site
- URL: https://food-cost-portal.preview.emergentagent.com/api/tracciabilita/

## Commercialista SMTP
- SMTP_USER: ceraldigroupsrl@gmail.com
- Email destinatario: rosaria.marotta@email.it
