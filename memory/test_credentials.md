# Test Credentials — Ceraldi ERP

> Aggiornato: 22 Apr 2026 da agent Emergent
> NON committare modifiche a password reali in produzione.

## Utente admin (JWT email+password + Google whitelist)

| Campo | Valore |
|---|---|
| Email | `ceraldigroupsrl@gmail.com` |
| Password | `Ceraldi1974` |
| Ruolo | `admin` |
| Auth provider | `both` (email+password + Google OAuth) |
| is_active | `true` |

## Whitelist email (accesso consentito)

Env `ALLOWED_EMAILS` in `/app/backend/.env`:
```
ALLOWED_EMAILS="ceraldigroupsrl@gmail.com"
```

Chi NON è in whitelist viene bloccato:
- su `/api/auth/login` → **HTTP 403**
- su `/api/auth/google/session` → **HTTP 403**

## Flow di login supportati

### 1. JWT (email + password)
```bash
curl -X POST https://impresasemplice.online/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ceraldigroupsrl@gmail.com","password":"Ceraldi1974"}'
```
Riceve `access_token` JWT (usa come `Authorization: Bearer ...`).

### 2. Emergent Google Auth
- Utente clicca "Continua con Google" su `/login`
- Redirect a `https://auth.emergentagent.com/?redirect={origin}/auth/callback`
- Dopo autorizzazione Google, torna con `#session_id=xxx` nell'URL
- Frontend (`AuthCallback` → `App.jsx`) chiama `POST /api/auth/google/session`
- Backend verifica email in whitelist, crea user + session, setta cookie `session_token` httpOnly
- Cookie dura 7 giorni

## Endpoint di verifica
- `GET /api/auth/verify` — verifica JWT (Authorization header)
- `GET /api/auth/google/me` — verifica session cookie (Emergent Google Auth)
- `POST /api/auth/google/logout` — logout + cookie clear

## Note di sicurezza
- **Cambiare password** al primo login produzione (POST `/api/auth/change-password`)
- La whitelist è case-insensitive e configurabile via env (CSV: `email1,email2`)
- Middleware `AuthenticationMiddleware` protegge tutti i `/api/*` non elencati in `PUBLIC_PATHS`/`PUBLIC_PREFIXES`
- JWT scade secondo `JWT_EXPIRATION_DELTA_DAYS` in config
- Session Google scade 7 giorni
