# CREDENZIALI — Ceraldi ERP
> Template credenziali — le reali sono in `backend/.env`
> ⚠️ NON committare mai le password reali nel repo

---

## Database
```
MONGO_URL = mongodb+srv://Ceraldidatabase:[PASSWORD]@cluster0.vofh7iz.mongodb.net/?retryWrites=true&w=majority
DB_NAME   = Gestionale
```
> ⚠️ DB name è `Gestionale` (NON `azienda_erp_db`)

## PEC Aruba (Fatture SDI)
```
ARUBA_PEC_HOST = imaps.pec.aruba.it
ARUBA_PEC_PORT = 993
ARUBA_PEC_USER = fatturazioneceraldi@pec.it
ARUBA_PEC_PASSWORD = [PASSWORD_PEC]
```

## Gmail Amministrazione
```
IMAP_HOST = imap.gmail.com
IMAP_USER = ceraldigroupsrl@gmail.com
IMAP_PASSWORD = [APP_PASSWORD_GOOGLE]
```

## WhatsApp Meta API
```
WHATSAPP_API_TOKEN = [TOKEN_META]
WHATSAPP_PHONE_NUMBER_ID = [PHONE_ID]
WHATSAPP_RECIPIENT_1 = [NUMERO_1]
WHATSAPP_RECIPIENT_2 = [NUMERO_2]
```

## Servizi Esterni
```
OPENAPI_COMPANY_TOKEN = [TOKEN_CAMERA_COMMERCIO]
EMERGENT_LLM_KEY = [CHIAVE_AI]
SECRET_KEY = [JWT_SECRET]
```

## Impostazioni
```
AUTH_DISABLED = true
ENVIRONMENT = production
CORS_ORIGINS = *
```

---

*Le credenziali reali sono SOLO in `/app/backend/.env` — mai nel codice sorgente*
