# Auth Testing Playbook — Ceraldi ERP

> Salvato da `integration_playbook_expert_v2` il 22 Apr 2026.
> Usare questo file come riferimento quando si testa il flow di autenticazione
> Emergent Google Auth.

## Contesto app
- Dominio produzione: `impresasemplice.online`
- Preview: `gestione-contabile.preview.emergentagent.com`
- Whitelist email: `ceraldigroupsrl@gmail.com`
- Backend: FastAPI su porta 8001
- Frontend: React/Vite
- Collections MongoDB: `users` (campo `user_id` UUID), `user_sessions` (campo `session_token`)

## Step 1 — Creare test user + session (via mongosh o script python)

```javascript
// mongosh
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'ceraldigroupsrl@gmail.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
```

## Step 2 — Testare endpoint
```bash
# Test /api/auth/me con session_token
curl -X GET "https://gestione-contabile.preview.emergentagent.com/api/auth/me" \
  -H "Authorization: Bearer <SESSION_TOKEN>"

# Test endpoint protetto
curl -X GET "https://gestione-contabile.preview.emergentagent.com/api/suppliers" \
  -H "Authorization: Bearer <SESSION_TOKEN>"
```

## Step 3 — Test frontend (browser via playwright)
```python
await page.context.add_cookies([{
    "name": "session_token",
    "value": "<SESSION_TOKEN>",
    "domain": "gestione-contabile.preview.emergentagent.com",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto("https://gestione-contabile.preview.emergentagent.com")
```

## Checklist
- [ ] `users` ha `user_id` UUID (NON `_id`)
- [ ] `user_sessions.user_id` == `users.user_id`
- [ ] Tutte le query usano `{"_id": 0}` projection
- [ ] `/api/auth/me` restituisce user (mai 401 se token valido)
- [ ] Dashboard carica senza redirect a /login
- [ ] CRUD su endpoint protetti funziona con cookie session_token

## Indicatori di successo
- ✅ `/api/auth/me` → 200 + user data
- ✅ Dashboard accessibile
- ✅ Email non whitelisted → 403

## Indicatori di fallimento
- ❌ 401 Unauthorized nonostante token valido
- ❌ Redirect a /login dopo login riuscito
- ❌ "User not found" con user_id valido

## Cleanup
```javascript
db.users.deleteMany({email: /test\./});
db.user_sessions.deleteMany({session_token: /test_/});
```
