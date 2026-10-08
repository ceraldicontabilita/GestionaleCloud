/* Ceraldi: the recovered interface uses the authenticated GestionaleCloud API.
 * Load this file before the recovered scripts: no legacy connection is allowed.
 */
(function () {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const nativeStorage = window.localStorage;
  const state = { authorized: false, user: null, started: false, installed: false, lastError: null };
  const virtualRoot = '/ceraldi-compat/rest/v1/';
  const loginUrl = '/login?next=' + encodeURIComponent('/primanota-ceraldi.html');
  const uiKeys = new Set(['fatture_theme', 'cf_reg_ordine', 'ceraldi_ricon_collassate']);
  const memory = new Map();
  const preferencePrefix = 'gestionalecloud:ceraldi-ui:v1:';
  const rules = [
    [/^\/api\/auth\/verify$/, ['GET']],
    [/^\/api\/auth\/logout$/, ['POST']],
    [/^\/api\/invoices(?:\/[^/]+)?$/, ['GET']],
    [/^\/api\/fatture-ricevute\/archivio$/, ['GET']],
    [/^\/api\/fatture-ricevute\/fattura\/[^/]+$/, ['GET', 'PUT']],
    [/^\/api\/fatture-ricevute\/candidati-bancari\/[^/]+$/, ['GET']],
    [/^\/api\/fatture-ricevute\/(?:paga-manuale|cambia-metodo-pagamento|riconcilia-con-estratto-conto)$/, ['POST']],
    [/^\/api\/fatture\/upload-xml$/, ['POST']],
    [/^\/api\/suppliers(?:\/[^/]+)?$/, ['GET', 'POST', 'PUT']],
    [/^\/api\/prima-nota\/(?:cassa|banca)$/, ['GET', 'POST']],
    [/^\/api\/prima-nota\/(?:cassa|banca)\/(?!delete-|sync-|fix-|elimina-|analisi-|verifica-|in-attesa-|candidati-|template-|crea-)[^/]+$/, ['PUT', 'DELETE']],
    [/^\/api\/estratto-conto-movimenti\/movimenti$/, ['GET']],
    [/^\/api\/corrispettivi$/, ['GET']],
    [/^\/api\/corrispettivi\/manuale$/, ['POST']],
    [/^\/api\/pos-corrispettivi\/verifica-coerenza$/, ['GET']],
    [/^\/api\/pos-corrispettivi\/controllo-due-fasi$/, ['GET']],
    [/^\/api\/pos-corrispettivi\/chiusura-giornaliera$/, ['PUT']],
    [/^\/(?:hr|lotti)\/api\/auth\/session$/, ['GET']],
    [/^\/menu\/api\/qrcode\/session$/, ['GET']]
  ];
  const derivedSessions = new Map();
  const sessionRequests = new Map();

  function error(message, status, code) {
    const value = new Error(message);
    value.status = status || 501;
    value.code = code || 'MODULO_NON_COLLEGATO';
    state.lastError = value;
    return value;
  }
  function escape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function writable() { return state.authorized && ['admin', 'operatore'].includes(state.user && state.user.role); }
  function allowed(url, method) {
    return url.origin === location.origin && rules.some(([pattern, methods]) => pattern.test(url.pathname) && methods.includes(method));
  }
  function addApiRule(pattern, methods) {
    if (!(pattern instanceof RegExp) || !Array.isArray(methods)) throw error('Regola API non valida', 400, 'REGOLA_NON_VALIDA');
    rules.push([pattern, methods.map(method => String(method).toUpperCase())]);
  }
  async function optionsFor(input, init) {
    const options = Object.assign({}, init || {});
    if (typeof Request !== 'undefined' && input instanceof Request) {
      if (!options.method) options.method = input.method;
      if (!options.headers) options.headers = input.headers;
      if (options.body === undefined && !['GET', 'HEAD'].includes(String(options.method).toUpperCase())) options.body = await input.clone().text();
    }
    return options;
  }
  function subsystem(url) { return ['hr', 'lotti', 'menu'].find(name => url.pathname.startsWith('/' + name + '/api/')); }
  function exchangePath(name) { return name === 'menu' ? '/menu/api/qrcode/session' : '/' + name + '/api/auth/session'; }
  async function checkGroupSession(status, name) {
    if (status === 401 || status === 403) {
      const verify = await nativeFetch('/api/auth/verify', { credentials: 'same-origin' });
      if ([401, 403].includes(verify.status)) { state.authorized = false; derivedSessions.clear(); showGate('La sessione del gestionale è terminata.', true); }
    }
    throw error('La sessione ' + name + ' non è disponibile per questo account.', status, 'SESSIONE_MODULO_NON_DISPONIBILE');
  }
  async function deriveToken(name) {
    if (derivedSessions.has(name)) return derivedSessions.get(name);
    if (sessionRequests.has(name)) return sessionRequests.get(name);
    const pending = (async () => {
      const response = await nativeFetch(exchangePath(name), { credentials: 'same-origin' });
      if (!response.ok) await checkGroupSession(response.status, name);
      const payload = await response.json();
      const token = payload.access_token || payload.token;
      if (!token) throw error('Il gestionale non ha restituito una sessione ' + name + '.', 503, 'SESSIONE_MODULO_ASSENTE');
      derivedSessions.set(name, token); return token;
    })();
    sessionRequests.set(name, pending);
    try { return await pending; } finally { sessionRequests.delete(name); }
  }
  async function api(path, options) {
    const url = new URL(path, location.origin);
    const opts = Object.assign({}, options || {});
    const method = String(opts.method || 'GET').toUpperCase();
    if (!allowed(url, method)) throw error('Questa operazione non è ancora collegata al gestionale: ' + url.pathname);
    if (!state.authorized && url.pathname !== '/api/auth/verify') throw error('Accedi dal gestionale per continuare', 401, 'SESSIONE_ASSENTE');
    if (!['GET', 'HEAD'].includes(method) && url.pathname !== '/api/auth/logout' && !writable()) throw error('Account in sola lettura', 403, 'SOLA_LETTURA');
    const headers = new Headers(opts.headers || {});
    headers.delete('apikey');
    const name = subsystem(url);
    const explicitToken = name && headers.has('Authorization');
    const exchange = name && url.pathname === exchangePath(name);
    if (!name) headers.delete('Authorization');
    else if (!explicitToken && !exchange) headers.set('Authorization', 'Bearer ' + await deriveToken(name));
    if (typeof opts.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    headers.delete('Range');
    headers.delete('Prefer');
    opts.headers = headers;
    opts.method = method;
    opts.credentials = 'same-origin';
    let response = await nativeFetch(url.href, opts);
    if (name && response.status === 401 && !exchange && !explicitToken) {
      derivedSessions.delete(name);
      headers.set('Authorization', 'Bearer ' + await deriveToken(name));
      response = await nativeFetch(url.href, opts);
    }
    if (name && [401, 403].includes(response.status)) await checkGroupSession(response.status, name);
    if (!name && response.status === 401 && url.pathname !== '/api/auth/verify') {
      state.authorized = false;
      showGate('La sessione è terminata. Accedi dal gestionale per continuare.', true);
    }
    return response;
  }
  window.fetch = async function (input, init) {
    const url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, location.href);
    const options = await optionsFor(input, init);
    if (url.origin === location.origin && url.pathname.startsWith(virtualRoot)) {
      if (!state.authorized) throw error('Sessione del gestionale non verificata', 401, 'SESSIONE_ASSENTE');
      if (!window.CeraldiBridgeData || typeof window.CeraldiBridgeData.request !== 'function') throw error('Il collegamento dati non è disponibile', 503, 'BRIDGE_NON_DISPONIBILE');
      const method = String(options.method || 'GET').toUpperCase();
      if (!['GET', 'HEAD'].includes(method) && !writable()) throw error('Account in sola lettura', 403, 'SOLA_LETTURA');
      return window.CeraldiBridgeData.request(url.pathname.slice(virtualRoot.length) + url.search, options, api);
    }
    if (url.protocol === 'blob:' && url.origin === location.origin) return nativeFetch(input, init);
    if (url.origin === location.origin && allowed(url, String(options.method || 'GET').toUpperCase())) return api(url.href, options);
    throw error('Fonte esterna scollegata. Usa i documenti e i servizi del gestionale.', 501, 'FONTE_SCOLLEGATA');
  };

  // The recovered page has no reason to create its own transports or workers.
  // PDF.js workers remain available through the standard Worker API.
  for (const name of ['WebSocket', 'EventSource', 'XMLHttpRequest']) {
    window[name] = function () { throw error('Usa il collegamento API autenticato del gestionale', 501, 'TRASPORTO_NON_COLLEGATO'); };
  }
  if (navigator.sendBeacon) {
    try { navigator.sendBeacon = function () { return false; }; } catch (_) { /* CSP also blocks external connections. */ }
  }

  // Existing local data and credentials never become a source for this page.
  // Business buffers live only in this tab; display preferences have new keys.
  const storage = {
    getItem(key) {
      key = String(key);
      if (uiKeys.has(key)) { try { return nativeStorage.getItem(preferencePrefix + key); } catch (_) { return null; } }
      return memory.has(key) ? memory.get(key) : null;
    },
    setItem(key, value) {
      key = String(key); value = String(value);
      if (uiKeys.has(key)) { try { nativeStorage.setItem(preferencePrefix + key, value); } catch (_) { /* Preferences are optional. */ } }
      else if (!/(?:auth|apikey|secret|client_id)/i.test(key)) memory.set(key, value);
    },
    removeItem(key) { key = String(key); memory.delete(key); if (uiKeys.has(key)) { try { nativeStorage.removeItem(preferencePrefix + key); } catch (_) {} } },
    clear() { memory.clear(); uiKeys.forEach(key => this.removeItem(key)); },
    key(index) { return Array.from(memory.keys())[index] || null; },
    get length() { return memory.size; }
  };
  try { Object.defineProperty(window, 'localStorage', { configurable: true, get: () => storage }); }
  catch (_) {
    // Fail closed if this browser cannot isolate the recovered page's cache.
    state.cacheError = error('Il browser non consente di isolare i dati locali. Apri la pagina nel browser del gestionale.', 503, 'CACHE_NON_ISOLATA');
  }

  function showGate(message, login) {
    let element = document.getElementById('ceraldiSessionGate');
    if (!element) {
      element = document.createElement('div'); element.id = 'ceraldiSessionGate';
      element.style.cssText = 'position:fixed;inset:0;z-index:2147483000;background:var(--bg,#f7f8fa);display:grid;place-items:center;padding:24px';
      document.body.appendChild(element);
    }
    element.innerHTML = '<div style="max-width:420px;text-align:center;font-family:Inter,Arial,sans-serif"><h1 style="font-size:23px">Ceraldi · GestionaleCloud</h1><p style="font-size:15px;line-height:1.6">' + escape(message) + '</p>' + (login ? '<a class="sk-btn prim" href="' + loginUrl + '">Accedi dal gestionale</a>' : '') + '<p><a href="/">Apri GestionaleCloud</a></p></div>';
  }
  function showUnsupported(message, destination) {
    const old = document.getElementById('ceraldiUnsupported'); if (old) old.remove();
    const overlay = document.createElement('div'); overlay.id = 'ceraldiUnsupported';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:12000;background:rgba(0,0,0,.38);display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = '<div style="background:var(--surface,#fff);color:var(--ink,#111);border-radius:18px;max-width:430px;padding:24px;box-shadow:0 20px 80px #0003"><h2 style="font-size:19px;margin:0 0 12px">Completa nel gestionale</h2><p style="font-size:14px;line-height:1.6">' + escape(message || 'Questa operazione richiede il modulo del gestionale.') + '</p><a class="sk-btn prim" href="' + escape(destination || '/prima-nota') + '">Apri il modulo</a><button class="sk-btn" type="button" data-close>Chiudi</button></div>';
    overlay.addEventListener('click', event => { if (event.target === overlay || event.target.closest('[data-close]')) overlay.remove(); });
    document.body.appendChild(overlay);
  }
  function block(name, destination) {
    window[name] = function () {
      const failure = error('Questa operazione è disponibile nel modulo del gestionale; non viene eseguita con le regole del vecchio database.');
      showUnsupported('Apri la sezione dedicata per completare questa operazione.', destination);
      return Promise.reject(failure);
    };
  }
  function runAutomation(name, args) {
    if (window.CeraldiAutomations && typeof window.CeraldiAutomations.runAutomation === 'function') return window.CeraldiAutomations.runAutomation(name, args || {}, window.CeraldiBridge);
    const automations = window.CeraldiAutomazioni;
    if (automations && typeof automations.runLegacy === 'function') return Promise.resolve(automations.runLegacy(name, args || [], window.CeraldiBridge));
    if (automations && typeof automations[name] === 'function') return Promise.resolve(automations[name].apply(automations, args || []));
    const failure = error('Automazione ' + name + ': collegamento al servizio canonico non ancora disponibile.');
    if (typeof window.toast === 'function') window.toast(failure.message);
    return Promise.reject(failure);
  }

  const modules = new Map();
  const modulePanels = new Map();
  let currentModule = null;
  function renderModuleNavigation() {
    const bar = document.getElementById('ceraldiModulesNav'); if (!bar) return;
    bar.replaceChildren();
    modules.forEach(module => {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'ceraldi-module-btn' + (module.id === currentModule ? ' active' : '');
      button.textContent = (module.icon ? module.icon + ' ' : '') + module.title;
      button.addEventListener('click', () => openModule(module.id)); bar.appendChild(button);
    });
  }
  async function openModule(id) {
    const module = modules.get(id); if (!module) throw error('Modulo non disponibile');
    if (!state.authorized) { showGate('Accedi dal gestionale per aprire questo modulo.', true); return; }
    const root = document.getElementById('ceraldiModuleView'); if (!root) return;
    document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
    document.querySelectorAll('.tab-item').forEach(button => button.classList.remove('active'));
    let panel = modulePanels.get(id);
    if (!panel) { panel = document.createElement('div'); modulePanels.set(id, panel); }
    root.classList.add('active'); root.replaceChildren(panel); currentModule = id; renderModuleNavigation();
    try {
      const context = window.CeraldiBridge;
      if (!panel._ceraldiMounted && typeof module.mount === 'function') { await module.mount(panel, context); panel._ceraldiMounted = true; }
      if (typeof module.onOpen === 'function') await module.onOpen(panel, context);
    } catch (failure) { panel.innerHTML = '<div class="ceraldi-module-error">' + escape(failure.message || failure) + '</div>'; panel._ceraldiMounted = false; }
  }
  window.CeraldiGestionaleModules = {
    register(module) {
      if (!module || !/^[a-z0-9_-]+$/i.test(module.id || '') || !module.title) throw error('Definizione modulo non valida');
      modules.set(module.id, module); renderModuleNavigation();
    }, open: openModule, list: () => Array.from(modules.values())
  };

  function installLegacyOverrides() {
    if (state.installed) return;
    state.installed = true;
    window._authLeggi = () => null;
    window._authScrivi = () => {};
    window._authApplica = () => { throw error('La sessione è gestita dal gestionale', 501, 'SESSIONE_CENTRALE'); };
    window._authRefresh = async () => false;
    window._authPronto = async () => { if (!state.authorized) throw error('Sessione non verificata', 401, 'SESSIONE_ASSENTE'); };
    window._authControllaAccesso = async () => window._authSess && window._authSess.acc;
    window._authAvvio = bootstrap;
    window._authEntra = bootstrap;
    window._authGoogle = () => { location.href = loginUrl; };
    ['_authPassword', '_authInviaCodice', '_authVerificaCodice', '_authPost', '_authDaIndirizzo'].forEach(name => block(name, '/login'));
    window._authEsci = async function () {
      const response = await api('/api/auth/logout', { method: 'POST' });
      if (!response.ok) throw error('Uscita non completata. Riprova.', response.status, 'LOGOUT_NON_COMPLETATO');
      state.authorized = false; memory.clear(); derivedSessions.clear(); location.href = loginUrl;
    };
    window._accSonoAdmin = () => state.authorized && state.user.role === 'admin';
    window._accSoloLettura = () => !writable();
    window._accLivello = () => writable() ? 'completo' : 'lettura';
    window._accAvvisa = () => {};
    window._authRigaImpostazioni = () => '<div class="imp-group-label">Account GestionaleCloud</div><div class="imp-group" style="padding:14px 16px">' + escape(state.user && (state.user.name || state.user.email)) + '<br><small>' + escape(state.user && state.user.role) + '</small><br><button class="sk-btn" onclick="_authEsci()">Esci</button></div>';
    ['_accCarica', '_accSalva'].forEach(name => block(name, '/utenti'));
    window._avviaRealtimeSync = () => {};
    window._ntfAvvio = async () => {};
    window._ntfRegistra = async () => null;
    window._ntfAttiva = () => runAutomation('notifiche', []);
    window._ntfSpegni = async () => {};
    window._esAvvio = async () => {};
    window.sbFetch = async function (path, opts) {
      const options = Object.assign({}, opts || {});
      const method = String(options.method || 'GET').toUpperCase();
      if (!state.authorized) throw error('Sessione del gestionale non verificata', 401, 'SESSIONE_ASSENTE');
      const response = await window.fetch(location.origin + virtualRoot + path, options);
      const body = await response.text();
      let payload; try { payload = body ? JSON.parse(body) : []; } catch (_) { throw error('Risposta dati non valida', 502, 'RISPOSTA_NON_VALIDA'); }
      if (!response.ok) {
        const failure = error(payload.detail || payload.message || 'Operazione non completata', response.status, payload.code);
        failure.body = body;
        if (!['GET', 'HEAD'].includes(method) && response.status === 501) showUnsupported(failure.message, path.startsWith('fatture') ? '/fatture' : '/prima-nota');
        throw failure;
      }
      return payload;
    };
    const originalLoad = window.loadAll;
    window.loadAll = async function () {
      const loaded = await originalLoad(true);
      const note = document.getElementById('ceraldiConnectionNote');
      if (note && !loaded) note.textContent = 'Sessione valida · sincronizzazione dati non completata. Riprova con Sincronizza.';
      if (note && loaded) {
        const rows = typeof fatture !== 'undefined' && Array.isArray(fatture) ? fatture : [];
        const missing = rows.filter(row => row.importo === null || row.importo === undefined || row.importo === '' || !Number.isFinite(Number(row.importo))).length;
        note.textContent = note.textContent.replace(/ · Totali parziali:.*$/, '');
        if (missing) note.textContent += ' · Totali parziali: manca l’importo di ' + missing + (missing === 1 ? ' documento.' : ' documenti.');
      }
      return loaded;
    };

    window._purgaCestinoScaduto = function () {
      const pending = Promise.reject(error('La cancellazione definitiva automatica è disabilitata. Usa l’archivio del gestionale.', 501, 'PURGA_AUTOMATICA_DISABILITATA'));
      pending.catch(() => {});
      return pending;
    };
    ['_ncAutoAggancia', '_autoRecuperaChiusuraMancante', 'autoEstraiPrezzi', 'ricalcolaIvaFattureXml', 'pnAggiornaScioperiNapoli'].forEach(name => {
      window[name] = function () {
        const pending = Promise.resolve().then(() => window.CeraldiBridge.runAutomation(name, { action: 'status', legacy_args: Array.from(arguments) }));
        // Observe passive timers too; callers still receive a rejected promise.
        pending.catch(failure => { if (typeof window.toast === 'function') window.toast(failure.message || 'Automazione non disponibile'); });
        return pending;
      };
    });
    window.pnFetchMeteo = async () => ({});
    window.apriScriptableRT = () => showUnsupported('Importa le chiusure del registratore attraverso Import Documenti del gestionale.', '/documenti/import');
    ['_paypalServer', '_eseguiSyncSumUp', '_ebChiamata', '_ebAvviaCollegamento', '_ebSincronizza', '_bkAdesso', 'ripristinaBackup', 'inviaNotifica', '_rsChiama', '_faChiediRicetta'].forEach(name => block(name, name.includes('bk') || name === 'ripristinaBackup' ? '/admin' : '/integrazioni'));
    ['_chiamataAI', 'analizzaPDF', 'analizzaXmlTesto', '_aiCicloConStrumenti', '_ceAiProponi'].forEach(name => block(name, '/documenti/import'));
    ['correggiFattureDifferite', 'bonificaFornitoriErrati'].forEach(name => block(name, '/fatture'));
    ['salvaApiKey', 'salvaPaypalKeys'].forEach(name => block(name, '/integrazioni'));
    window._paypalMigra = async () => {};
    const originalSettingsPage = window._impRenderSub;
    window._impRenderSub = function (page) {
      if (page === 'automazioni' && modules.has('automazioni_gc')) { window.chiudiImpostazioni(); return openModule('automazioni_gc'); }
      if (['apikey', 'paypal', 'banca_eb'].includes(page)) return showUnsupported('Le integrazioni sono configurate nel gestionale.', page === 'apikey' ? '/impostazioni-ai' : '/integrazioni');
      return originalSettingsPage.apply(this, arguments);
    };
    // Legacy helpers swallow REST failures and then resolve; leave them closed
    // until a semantic action installs a supported implementation.
    ['dbCestina', 'dbRipristinaDaCestino', 'dbDelete', 'dbUpdateFoto'].forEach(name => block(name, '/fatture'));
    window.apriAiAssistente = () => showUnsupported('L’assistente usa i documenti e le integrazioni del gestionale.', '/impostazioni-ai');
    // Unsupported edits must never resolve as a successful save.
    ['dbUpdate', 'dbUpdatePartial'].forEach(name => {
      const original = window[name]; if (typeof original !== 'function') return;
      window[name] = async function () {
        state.lastError = null;
        const result = await original.apply(this, arguments);
        if (result == null || (Array.isArray(result) && !result.length)) throw state.lastError || error('La modifica non è stata salvata');
        return result;
      };
    });
    const originalTab = window.goTab;
    window.goTab = function () {
      if (arguments[0] === 'fiscale' && modules.has('fiscale_gc')) return openModule('fiscale_gc');
      currentModule = null;
      const root = document.getElementById('ceraldiModuleView'); if (root) root.classList.remove('active');
      renderModuleNavigation(); return originalTab.apply(this, arguments);
    };
    window.apriFiscaleSezione = function (section) {
      if (section === 'importazioni') return showUnsupported('Importa gli originali nel gestionale: saranno disponibili anche in questa applicazione.', '/documenti/import');
      return openModule('fiscale_gc');
    };
    if (window.CeraldiBridgeActions && typeof window.CeraldiBridgeActions.install === 'function') window.CeraldiBridgeActions.install();
  }

  function installUi() {
    const header = document.querySelector('.hdr-row');
    if (header && !document.getElementById('ceraldiGestionaleLink')) {
      const link = document.createElement('a'); link.id = 'ceraldiGestionaleLink'; link.href = '/'; link.textContent = 'GestionaleCloud';
      link.style.cssText = 'font-size:11px;font-weight:600;color:var(--blue,#2563eb);text-decoration:none;margin-left:auto;white-space:nowrap'; header.appendChild(link);
    }
    const brand = document.querySelector('.hdr-row p'); if (brand) brand.textContent = 'Ceraldi · GestionaleCloud';
    const note = document.getElementById('ceraldiConnectionNote');
    if (note) note.textContent = 'Accesso: ' + (state.user.name || state.user.email) + ' · ' + (writable() ? 'Dati del gestionale' : 'Sola lettura') + ' · Sincronizzazione dal database attuale';
    const sync = document.querySelector('[aria-label="Sincronizza"]'); if (sync) sync.title = 'Sincronizza i dati reali di GestionaleCloud';
    const old = document.getElementById('authGate'); if (old) old.remove();
    if (typeof window._authNascondi === 'function') window._authNascondi();
    renderModuleNavigation();
  }
  async function bootstrap() {
    if (state.started) return;
    state.started = true;
    installLegacyOverrides();
    // start() runs before deferred adapters; bootstrap runs after they load.
    if (window.CeraldiBridgeActions && typeof window.CeraldiBridgeActions.install === 'function') window.CeraldiBridgeActions.install();
    showGate('Verifico la sessione di GestionaleCloud…', false);
    try {
      if (state.cacheError) throw state.cacheError;
      const response = await api('/api/auth/verify');
      if (response.status === 401 || response.status === 403) { location.replace(loginUrl); return; }
      if (!response.ok) throw error('Verifica della sessione temporaneamente non disponibile.', response.status, 'VERIFICA_NON_DISPONIBILE');
      const payload = await response.json();
      const user = payload.user;
      if (!payload.ok || !user || !['admin', 'operatore', 'sola_lettura'].includes(user.role)) throw error('Questo account non è autorizzato al gestionale.', 403, 'RUOLO_NON_AUTORIZZATO');
      if (!window.CeraldiBridgeData || typeof window.CeraldiBridgeData.request !== 'function') throw error('Collegamento dati non disponibile. Ricarica la pagina.', 503, 'BRIDGE_NON_DISPONIBILE');
      state.user = user; state.authorized = true;
      window._authSess = { user: { email: user.email, id: user.email }, metodo: 'GestionaleCloud', acc: { ok: true, stato: 'attivo', ruolo: user.role, nome: user.name || user.email, permessi: { fatture: writable() ? 'completo' : 'lettura' } } };
      window._authCfg = { external: { google: false }, disable_signup: true };
      if (window._authApri) { window._authApri(); window._authApri = null; }
      installUi();
      const gate = document.getElementById('ceraldiSessionGate'); if (gate) gate.remove();
      if (!window._authAppAvviata) { window._authAppAvviata = true; await window.init(); }
      window.dispatchEvent(new CustomEvent('ceraldi:authenticated', { detail: { user, bridge: window.CeraldiBridge } }));
    } catch (failure) {
      state.authorized = false;
      showGate(failure.message || 'Impossibile collegare il gestionale. Riprova.', false);
    }
  }
  window.CeraldiBridge = {
    api, addApiRule, bootstrap, installLegacyOverrides, runAutomation, showUnsupported,
    get user() { return state.user; }, get authorized() { return state.authorized; }, writable,
    get canWrite() { return writable(); },
    requireWrite() { if (!writable()) throw error('Account in sola lettura', 403, 'SOLA_LETTURA'); },
    escape,
    start() {
      installLegacyOverrides();
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootstrap, { once: true }); else bootstrap();
    }
  };
})();
