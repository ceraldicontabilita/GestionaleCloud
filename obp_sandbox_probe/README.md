# OBP Sandbox Probe

Isolated read-only probe for validating Open Bank Project connectivity before integrating banking into GestionaleCloud.

## Safety properties

- runs on a dedicated Render service / branch
- no Supabase access
- no ERP database writes
- no payment endpoints
- OAuth token held only in process memory
- token disappears on restart/deploy

## Required environment variables for OAuth/OIDC

- `OBP_BASE_URL`
- `OBP_VERSION`
- `OBP_AUTHORIZATION_URL`
- `OBP_TOKEN_URL`
- `OBP_CLIENT_ID`
- `OBP_CLIENT_SECRET` (when required by the client)
- `OBP_REDIRECT_URI`
- `OBP_SCOPE`

The public connectivity probe works before OAuth variables are configured.
