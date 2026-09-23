# OBP Sandbox Probe

Isolated read-only probe for validating Open Bank Project connectivity before integrating banking into GestionaleCloud.

## Browser Direct Login flow

Open `/direct-login`, enter the OBP sandbox username and password, and submit.
The backend uses the environment-provided consumer key to call Direct Login and
then checks, in order:

1. `/users/current`
2. `/my/accounts`
3. up to five transactions from the first accessible account

The browser is redirected to `/direct-result`, which exposes only status codes
and counts. `/direct-probe` provides the same sanitized result as JSON.

## Safety properties

- runs on a dedicated Render service / branch
- no Supabase access
- no ERP database writes
- no payment endpoints
- username and password are accepted only by the backend form handler
- credentials are not saved, returned, or logged
- the Direct Login token is held only in process memory
- token disappears on restart/deploy
- form pages and responses are marked `no-store`
- one-time CSRF protection and restrictive browser security headers

## Required environment variables

- `OBP_CONSUMER_KEY` (required; never rendered in diagnostics)
- `OBP_BASE_URL` (optional; defaults to the public OBP sandbox)
- `OBP_VERSION` (optional; defaults to `v7.0.0`)

No Supabase variables, GestionaleCloud database connection, consumer secret, or
persistent storage are used by this probe. The public connectivity check works
before the consumer key is configured.
