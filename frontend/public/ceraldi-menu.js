/* Menu e ricette: proiezioni delle API canoniche, nella grafica Ceraldi.
 * Nessun client Supabase, nuovo login o archivio locale dei prodotti.
 * Sessioni derivate: app/menu/routes/qrcode_routes.py e app/lotti/auth.py.
 * Gli aggiornamenti di ricette passano da Lotti e dal suo ponte Menu.
 */
(function () {
  'use strict';
  var registry = window.CeraldiGestionaleModules;
  if (!registry || typeof registry.register !== 'function') return;
  var states = new WeakMap();
  var configuredBridges = new WeakSet();
  var money = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' });
  var number = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });

  function active(state) { return states.get(state.root) === state && !!state.root.querySelector('[data-menu-list]'); }
  function allowCanonicalApi(bridge) {
    if (!bridge || typeof bridge.addApiRule !== 'function' || configuredBridges.has(bridge)) return;
    // Solo i percorsi verificati nelle route di Menu/Lotti. Non viene aperto
    // un prefisso generico e i prodotti Menu non hanno un writer DELETE.
    [
      [/^\/menu\/api\/qrcode\/session$/, ['GET']],
      [/^\/menu\/api\/menu\/$/, ['GET']],
      [/^\/menu\/api\/menu\/admin\/products\/all$/, ['GET']],
      [/^\/menu\/api\/menu\/admin\/products\/\d+$/, ['PUT']],
      [/^\/menu\/api\/menu\/admin\/products\/\d+\/visibilita$/, ['PUT']],
      [/^\/lotti\/api\/auth\/session$/, ['GET']],
      [/^\/lotti\/api\/ricette-unificate$/, ['GET']],
      [/^\/lotti\/api\/food-cost\/(?:calcola|nutrizionale)\/[^/]+$/, ['GET']],
      [/^\/lotti\/api\/ricette\/[^/]+$/, ['PATCH']],
      [/^\/lotti\/api\/ricette\/[^/]+\/scheda-vendita$/, ['PUT']]
    ].forEach(function (rule) { bridge.addApiRule(rule[0], rule[1]); });
    configuredBridges.add(bridge);
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function numeric(value) {
    if (value == null || String(value).trim() === '') return null;
    var n = Number(String(value).replace(/€/g, '').trim().replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  }
  function euro(value) {
    var n = numeric(value);
    return n == null || n <= 0 ? 'Non impostato' : money.format(n);
  }
  function normalized(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }
  function canWrite(state) {
    var user = state.bridge.user || {};
    var role = String(user.role || user.ruolo || '').toLowerCase();
    var allowed = typeof state.bridge.canWrite === 'function' ? !!state.bridge.canWrite() : state.bridge.canWrite === true;
    return allowed && ['admin', 'amministratore'].indexOf(role) !== -1;
  }
  function recipeId(product) {
    var ref = String(product.lotti_ref || '');
    return product.origine === 'lotti' && ref.indexOf('ricetta:') === 0 ? ref.slice(8) : null;
  }
  function recipeLink(id) { return '/lotti/#ricette' + (id ? '/' + encodeURIComponent(id) : ''); }
  function safeImage(value) {
    if (!value) return '';
    try {
      var url = new URL(value, window.location.origin);
      return url.protocol === 'https:' || (url.protocol === 'http:' && url.origin === window.location.origin) ? url.href : '';
    } catch (_) { return ''; }
  }
  function message(error) { return error && error.message ? error.message : 'Operazione non riuscita'; }
  async function api(state, path, options, token) {
    options = Object.assign({}, options || {});
    options.headers = Object.assign({}, options.headers || {});
    if (token) options.headers.Authorization = 'Bearer ' + token;
    if (options.body != null) options.headers['Content-Type'] = 'application/json';
    var response = await state.bridge.api(path, options);
    var data;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) {
      var detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg || ''; }).join('; ');
      var error = new Error(typeof detail === 'string' ? detail : 'Richiesta non riuscita (' + response.status + ')');
      error.status = response.status;
      throw error;
    }
    if (data == null) throw new Error('Risposta del servizio non leggibile');
    return data;
  }
  function notice(state, text, failed) {
    var el = state.root.querySelector('[data-menu-notice]');
    if (!active(state) || !el) return;
    el.hidden = !text;
    el.textContent = text || '';
    el.className = 'cm-notice ' + (failed ? 'cm-error' : 'cm-success');
    el.setAttribute('role', failed ? 'alert' : 'status');
  }
  function errors(state) {
    var el = state.root.querySelector('[data-menu-errors]');
    el.hidden = !state.errors.length;
    el.innerHTML = state.errors.map(function (error) { return '<p>' + esc(error) + '</p>'; }).join('');
  }
  function summary(state) {
    var products = state.products;
    var visible = products.filter(function (p) { return p.visible !== false; }).length;
    var noPrice = products.filter(function (p) { var n = numeric(p.price); return n == null || n <= 0; }).length;
    state.root.querySelector('[data-menu-summary]').innerHTML = [
      [state.productsLoaded ? products.length : '—', state.catalogAdmin ? 'Prodotti totali' : 'Prodotti pubblici'],
      [state.productsLoaded ? visible : '—', 'Visibili'], [state.catalogAdmin ? noPrice : '—', 'Prezzi da definire'],
      [state.recipesLoaded ? state.recipes.length : '—', 'Ricette operative']
    ].map(function (pair) { return '<div class="cm-stat"><strong>' + esc(pair[0]) + '</strong><span>' + esc(pair[1]) + '</span></div>'; }).join('');
  }
  function productName(p) { return p.nameIT || p.name || 'Prodotto senza nome'; }
  function recipeName(r) { return r.nome || 'Ricetta senza nome'; }
  function categories(state) {
    var select = state.root.querySelector('[data-menu-category]');
    var choices = new Map();
    (state.tab === 'products' ? state.products : state.recipes).forEach(function (item) {
      var key = state.tab === 'products' ? String(item.category_id) : String(item.reparto || '');
      var label = state.tab === 'products' ? (item.categoryName || 'Categoria non definita') : (item.reparto || 'Reparto non definito');
      choices.set(key, label);
    });
    select.innerHTML = '<option value="">' + (state.tab === 'products' ? 'Tutte le categorie' : 'Tutti i reparti') + '</option>' +
      Array.from(choices).sort(function (a, b) { return a[1].localeCompare(b[1], 'it'); }).map(function (pair) {
        return '<option value="' + esc(pair[0]) + '">' + esc(pair[1]) + '</option>';
      }).join('');
    select.value = state.category;
    state.root.querySelector('[data-menu-visibility]').hidden = state.tab !== 'products';
    state.root.querySelector('[data-menu-category-label]').textContent = state.tab === 'products' ? 'Categoria' : 'Reparto';
  }
  function filtered(state) {
    var search = normalized(state.search);
    var items = state.tab === 'products' ? state.products : state.recipes;
    return items.filter(function (item) {
      var product = state.tab === 'products';
      var haystack = product ? [productName(item), item.codice_prodotto, item.descriptionIT, item.categoryName, item.subcategoryName].join(' ') : [recipeName(item), item.reparto, item.ingredienti_testo].join(' ');
      var category = product ? String(item.category_id) : String(item.reparto || '');
      return (!search || normalized(haystack).indexOf(search) !== -1) && (!state.category || category === state.category) &&
        (!product || state.visibility === 'all' || (state.visibility === 'visible' ? item.visible !== false : item.visible === false));
    }).sort(function (a, b) {
      return (state.tab === 'products' ? productName(a) : recipeName(a)).localeCompare(state.tab === 'products' ? productName(b) : recipeName(b), 'it');
    });
  }
  function badge(text, type) { return '<span class="cm-badge cm-' + (type || 'neutral') + '">' + esc(text) + '</span>'; }
  function renderList(state) {
    var list = state.root.querySelector('[data-menu-list]');
    var items = filtered(state);
    state.root.querySelector('[data-menu-count]').textContent = items.length + (state.tab === 'products' ? ' prodotti' : ' ricette');
    if (state.loading) { list.innerHTML = '<p class="cm-empty" role="status">Caricamento del Menu e delle ricette…</p>'; return; }
    if (!items.length) {
      list.innerHTML = '<p class="cm-empty">' + (state.tab === 'recipes' && !state.recipesLoaded ? 'Le ricette non sono disponibili per questa sessione. Usa Aggiorna per riprovare.' : 'Nessun risultato con questi filtri.') + '</p>';
      return;
    }
    list.innerHTML = items.slice(0, state.limit).map(function (item) {
      var product = state.tab === 'products';
      var image = safeImage(product ? item.image : item.foto_url);
      var id = String(item.id);
      var name = product ? productName(item) : recipeName(item);
      var price = product ? item.price : item.prezzo_tavolo;
      var flags = product ? badge(item.visible === false ? 'Nascosto' : 'Visibile', item.visible === false ? 'neutral' : 'ok') +
        (item.disponibile === false ? badge('Esaurito', 'warn') : '') + badge(item.origine === 'lotti' ? 'Da ricetta' : 'Menu') :
        badge(item.menu_pubblico === true ? 'Nel Menu' : 'Ricetta interna', item.menu_pubblico === true ? 'ok' : 'neutral') +
        (item.esaurito === true ? badge('Esaurito', 'warn') : '');
      var meta = product ? [item.categoryName, item.subcategoryName, item.codice_prodotto].filter(Boolean).join(' · ') :
        [item.reparto, item.porzioni != null ? item.porzioni + ' porzioni' : null].filter(Boolean).join(' · ');
      return '<article class="fi cm-item"><div class="fi-stripe ' + (product && item.visible === false ? 'fi-stripe-neu' : 'fi-stripe-ok') + '"></div><div class="fi-inner">' +
        (image ? '<img class="cm-image" src="' + esc(image) + '" alt="" loading="lazy">' : '<div class="fi-ic ic-b">🍽️</div>') +
        '<div class="fi-body"><div class="fi-top"><h3 class="fi-nome">' + esc(name) + '</h3><span class="cm-price">' + esc(euro(price)) + '</span></div>' +
        '<p class="fi-meta">' + esc(meta) + '</p><div class="fi-badges">' + flags + '</div>' +
        '<button class="btn btn-s cm-compact" data-menu-action="detail" data-menu-id="' + esc(id) + '">Dettaglio' + (canWrite(state) ? ' e gestione' : '') + '</button></div></div></article>';
    }).join('') + (items.length > state.limit ? '<button class="btn btn-s" data-menu-action="more">Mostra altri (' + (items.length - state.limit) + ')</button>' : '');
    list.querySelectorAll('img').forEach(function (img) {
      img.addEventListener('error', function () { img.hidden = true; }, { once: true });
    });
  }
  function clearDetail(state) {
    state.detailVersion++;
    var el = state.root.querySelector('[data-menu-detail]');
    if (!el) return;
    el.hidden = true;
    el.innerHTML = '';
    state.selected = null;
  }
  function render(state) { summary(state); errors(state); renderList(state); }
  function publicProducts(menu) {
    var result = [];
    (menu.categories || []).forEach(function (cat) {
      (cat.subcategories || []).forEach(function (sub) {
        (sub.items || []).forEach(function (p) {
          result.push(Object.assign({}, p, { categoryName: cat.nameIT || cat.name, subcategoryName: sub.nameIT || sub.name }));
        });
      });
    });
    return result;
  }
  async function refresh(state) {
    if (state.loading || !active(state)) return;
    state.loading = true;
    state.errors = [];
    state.menuToken = state.lottiToken = null;
    state.catalogAdmin = false;
    state.productsLoaded = false;
    state.recipesLoaded = false;
    state.products = []; state.recipes = [];
    state.root.querySelector('[data-menu-refresh]').disabled = true;
    notice(state, '', false);
    clearDetail(state);
    render(state);
    // L'handoff prova il cookie HttpOnly del Gestionale. I token restano in
    // memoria di questa pagina: non sono copiati in URL o localStorage.
    if (canWrite(state)) {
      var sessions = await Promise.allSettled([
        api(state, '/menu/api/qrcode/session'), api(state, '/lotti/api/auth/session')
      ]);
      if (!active(state)) return;
      ['menuToken', 'lottiToken'].forEach(function (key, i) {
        if (sessions[i].status === 'fulfilled' && sessions[i].value.token) state[key] = sessions[i].value.token;
        else state.errors.push((i ? 'Ricette: ' : 'Gestione Menu: ') + (sessions[i].status === 'rejected' ? message(sessions[i].reason) : 'Sessione non disponibile'));
      });
    }
    var tasks = [api(state, state.menuToken ? '/menu/api/menu/admin/products/all' : '/menu/api/menu/', null, state.menuToken)];
    if (state.lottiToken) tasks.push(api(state, '/lotti/api/ricette-unificate', null, state.lottiToken));
    var results = await Promise.allSettled(tasks);
    if (!active(state)) return;
    if (results[0].status === 'fulfilled') {
      var catalog = results[0].value;
      state.products = state.menuToken ? (catalog.products || []) : publicProducts(catalog);
      state.catalogAdmin = !!state.menuToken;
      state.productsLoaded = true;
    } else state.errors.push('Menu: ' + message(results[0].reason));
    if (results[1]) {
      if (results[1].status === 'fulfilled' && Array.isArray(results[1].value)) {
        state.recipes = results[1].value.filter(function (r) { return r.archiviata !== true; });
        state.recipesLoaded = true;
      } else state.errors.push('Ricette: ' + (results[1].status === 'rejected' ? message(results[1].reason) : 'Formato elenco non valido'));
    }
    state.loading = false;
    state.root.querySelector('[data-menu-refresh]').disabled = false;
    categories(state); render(state);
  }
  function priceInput(name, label, value) {
    return '<label class="field"><span>' + label + '</span><input name="' + name + '" type="text" inputmode="decimal" autocomplete="off" value="' + esc(value == null ? '' : String(value).replace(/€/g, '').trim()) + '" placeholder="Non impostato"></label>';
  }
  function nutritionHtml(data) {
    var values = data && data.valori_nutrizionali;
    if (!values || typeof values !== 'object' || !Object.keys(values).length) return '<p class="cm-muted">Valori nutrizionali non ancora disponibili.</p>';
    var fields = [['kcal', 'Energia', 'kcal'], ['grassi', 'Grassi', 'g'], ['saturi', 'di cui saturi', 'g'], ['carboidrati', 'Carboidrati', 'g'], ['zuccheri', 'di cui zuccheri', 'g'], ['proteine', 'Proteine', 'g'], ['sale', 'Sale', 'g']];
    var present = fields.filter(function (row) { return numeric(values[row[0]]) != null; });
    if (!present.length) return '<p class="cm-muted">Valori nutrizionali non ancora disponibili.</p>';
    return '<p class="cm-muted">Valori salvati per 100 g · stima del ricettario</p><dl class="cm-facts">' + present.map(function (row) {
      return '<div><dt>' + row[1] + '</dt><dd>' + number.format(numeric(values[row[0]])) + ' ' + row[2] + '</dd></div>';
    }).join('') + '</dl>';
  }
  function costHtml(data) {
    var ingredients = Array.isArray(data.ingredienti) ? data.ingredienti : [];
    var computed = ingredients.filter(function (i) { return numeric(i.costo) != null; });
    var missing = ingredients.filter(function (i) { return numeric(i.costo) == null; });
    if (!computed.length) return '<p class="cm-muted">Costo non disponibile: mancano quantità o prezzi degli ingredienti.</p>';
    return '<dl class="cm-facts"><div><dt>' + (missing.length ? 'Costo parziale della ricetta' : 'Costo ricetta') + '</dt><dd>' + (numeric(data.costo_totale) == null ? 'Non disponibile' : money.format(numeric(data.costo_totale))) + '</dd></div>' +
      '<div><dt>' + (missing.length ? 'Costo parziale per porzione' : 'Costo per porzione') + '</dt><dd>' + (numeric(data.costo_porzione) == null ? 'Non disponibile' : money.format(numeric(data.costo_porzione))) + '</dd></div></dl>' +
      (missing.length ? '<p class="cm-warn">Da completare: ' + esc(missing.map(function (i) { return i.nome; }).join(', ')) + '</p>' : '<p class="cm-muted">Costo calcolato sui prezzi disponibili degli ingredienti.</p>');
  }
  async function showDetail(state, id) {
    var product = state.tab === 'products';
    var item = (product ? state.products : state.recipes).find(function (p) { return String(p.id) === id; });
    if (!item) return;
    var rid = product ? recipeId(item) : id;
    var recipe = rid ? state.recipes.find(function (r) { return String(r.id) === rid; }) : null;
    var editable = canWrite(state) && (rid ? !!state.lottiToken && !!recipe : !!state.menuToken && item.origine !== 'lotti');
    var panel = state.root.querySelector('[data-menu-detail]');
    var version = ++state.detailVersion;
    state.selected = { item: item, recipe: recipe, rid: rid, product: product };
    panel.hidden = false;
    var name = product ? productName(item) : recipeName(item);
    var description = product ? (item.descriptionIT || item.description) : (item.descrizione || item.note);
    var tablePrice = rid && recipe ? recipe.prezzo_tavolo : item.price;
    var counterPrice = rid && recipe ? recipe.prezzo_vendita : item.prezzo_banco;
    panel.innerHTML = '<div class="cm-detail-heading"><h3>' + esc(name) + '</h3><button class="btn btn-s cm-compact" data-menu-action="close-detail">Chiudi</button></div>' +
      (description ? '<p class="cm-description">' + esc(description) + '</p>' : '') +
      '<dl class="cm-facts"><div><dt>Prezzo al tavolo</dt><dd>' + esc(euro(tablePrice)) + '</dd></div><div><dt>Prezzo al banco</dt><dd>' + esc(euro(counterPrice)) + '</dd></div></dl>' +
      (rid ? '<a class="cm-link" href="' + recipeLink(rid) + '">Apri la ricetta completa</a>' : '') +
      (editable ? '<form data-menu-price-form><div class="cm-two">' + priceInput('table', 'Prezzo al tavolo (€)', tablePrice) + priceInput('counter', 'Prezzo al banco (€)', counterPrice) +
        '</div><p class="cm-muted">Il campo vuoto rimuove il prezzo già impostato.</p><button class="btn btn-p cm-compact" type="submit">Salva prezzi</button></form>' : '') +
      (product && canWrite(state) && state.menuToken ? '<button class="btn btn-s cm-compact" data-menu-action="visibility">' + (item.visible === false ? 'Mostra nel Menu' : 'Nascondi dal Menu') + '</button>' : '') +
      (rid && editable ? '<button class="btn btn-s cm-compact" data-menu-action="availability">' + (recipe.esaurito === true ? 'Segna disponibile' : 'Segna esaurito') + '</button>' : '') +
      (rid ? '<div class="cm-analysis"><h4>Food cost</h4><div data-menu-cost class="cm-muted">Caricamento…</div><h4>Valori nutrizionali</h4><div data-menu-nutrition class="cm-muted">Caricamento…</div></div>' : '');
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    var form = panel.querySelector('[data-menu-price-form]');
    if (form) form.addEventListener('submit', function (event) { event.preventDefault(); savePrices(state, form); });
    if (!rid) return;
    if (!state.lottiToken) {
      panel.querySelector('[data-menu-cost]').textContent = 'Sessione ricette non disponibile.';
      panel.querySelector('[data-menu-nutrition]').textContent = 'Sessione ricette non disponibile.';
      return;
    }
    var results = await Promise.allSettled([
      api(state, '/lotti/api/food-cost/calcola/' + encodeURIComponent(rid), null, state.lottiToken),
      api(state, '/lotti/api/food-cost/nutrizionale/' + encodeURIComponent(rid), null, state.lottiToken)
    ]);
    if (!active(state) || version !== state.detailVersion) return;
    ['[data-menu-cost]', '[data-menu-nutrition]'].forEach(function (selector, i) {
      var target = panel.querySelector(selector);
      if (results[i].status === 'fulfilled') target.innerHTML = i ? nutritionHtml(results[i].value) : costHtml(results[i].value);
      else { target.textContent = message(results[i].reason); target.className = 'cm-error'; }
    });
  }
  function priceValue(value) {
    value = String(value).trim();
    if (!value) return null;
    if (!/^\d+(?:[.,]\d{1,2})?$/.test(value)) throw new Error('Inserisci un prezzo positivo con al massimo due decimali, oppure lascia il campo vuoto.');
    var result = numeric(value);
    if (result == null || result <= 0) throw new Error('Il prezzo deve essere maggiore di zero. Per rimuoverlo lascia il campo vuoto.');
    return result;
  }
  function checkSync(data) {
    if (data.menu_sync && ['pubblicato', 'aggiornato'].indexOf(data.menu_sync.esito) === -1) {
      throw new Error('Modifica salvata nella ricetta, ma il Menu non risulta aggiornato: ' + (data.menu_sync.motivo || data.menu_sync.esito || 'verifica la sincronizzazione') + '.');
    }
  }
  async function mutation(state, controls, operation) {
    if (state.saving || !canWrite(state)) return;
    state.saving = true;
    controls.forEach(function (control) { control.disabled = true; });
    try {
      var data = await operation();
      checkSync(data);
      await refresh(state);
      notice(state, 'Modifica salvata.', false);
    } catch (error) {
      notice(state, message(error), true);
    } finally {
      state.saving = false;
      controls.forEach(function (control) { control.disabled = false; });
    }
  }
  async function savePrices(state, form) {
    if (!state.selected || !canWrite(state)) return;
    var selected = state.selected;
    var table, counter;
    try { table = priceValue(form.elements.table.value); counter = priceValue(form.elements.counter.value); }
    catch (error) { notice(state, message(error), true); return; }
    if (!selected.rid && table == null) { notice(state, 'I prodotti creati nel Menu richiedono un prezzo al tavolo. Puoi nasconderli dal Menu.', true); return; }
    var payload = selected.rid ? { prezzo_tavolo: table, prezzo_vendita: counter } : { price: table.toFixed(2).replace('.', ','), prezzo_banco: counter == null ? 0 : counter };
    var path = selected.rid ? '/lotti/api/ricette/' + encodeURIComponent(selected.rid) : '/menu/api/menu/admin/products/' + encodeURIComponent(selected.item.id);
    var token = selected.rid ? state.lottiToken : state.menuToken;
    if (!token) return;
    await mutation(state, Array.from(form.querySelectorAll('input,button')), function () {
      return api(state, path, { method: selected.rid ? 'PATCH' : 'PUT', body: JSON.stringify(payload) }, token);
    });
  }
  async function act(state, button) {
    var action = button.getAttribute('data-menu-action');
    if (action === 'detail') { await showDetail(state, button.getAttribute('data-menu-id')); return; }
    if (action === 'more') { state.limit += 100; renderList(state); return; }
    if (action === 'close-detail') { clearDetail(state); return; }
    var selected = state.selected;
    if (!selected || !canWrite(state)) return;
    if (action === 'visibility' && state.menuToken) {
      await mutation(state, [button], function () {
        return api(state, '/menu/api/menu/admin/products/' + encodeURIComponent(selected.item.id) + '/visibilita',
          { method: 'PUT', body: JSON.stringify({ visible: selected.item.visible === false }) }, state.menuToken);
      });
    }
    if (action === 'availability' && selected.rid && selected.recipe && state.lottiToken) {
      await mutation(state, [button], function () {
        return api(state, '/lotti/api/ricette/' + encodeURIComponent(selected.rid) + '/scheda-vendita',
          { method: 'PUT', body: JSON.stringify({ esaurito: selected.recipe.esaurito !== true }) }, state.lottiToken);
      });
    }
  }
  function mount(root, bridge) {
    allowCanonicalApi(bridge);
    var previous = states.get(root);
    if (previous && previous.clickHandler) root.removeEventListener('click', previous.clickHandler);
    var state = { root: root, bridge: bridge, tab: 'products', search: '', category: '', visibility: 'all', products: [], recipes: [], errors: [], limit: 100, detailVersion: 0 };
    states.set(root, state);
    root.classList.add('ceraldi-menu-module');
    root.innerHTML = '<style>' +
      '.ceraldi-menu-module{color:var(--ink);font-family:inherit}.ceraldi-menu-module h2{font-size:23px;margin:0}.ceraldi-menu-module h3{font-size:16px}.ceraldi-menu-module h4{margin:18px 0 8px}.ceraldi-menu-module .cm-header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.ceraldi-menu-module .cm-actions{display:flex;flex-wrap:wrap;gap:8px}.ceraldi-menu-module .cm-compact{width:auto;padding:10px 14px;font-size:13px;margin-top:8px}.ceraldi-menu-module .cm-actions .btn{margin:0;text-decoration:none}.ceraldi-menu-module .cm-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:14px 0}.ceraldi-menu-module .cm-stat{background:var(--surface);border-radius:var(--radius);box-shadow:var(--shadow);padding:14px}.ceraldi-menu-module .cm-stat strong{display:block;font-size:23px}.ceraldi-menu-module .cm-stat span{display:block;font-size:11px;color:var(--ink3);margin-top:4px}.ceraldi-menu-module .cm-filters{background:var(--surface);border-radius:var(--radius);padding:14px;margin:14px 0;box-shadow:var(--shadow)}.ceraldi-menu-module .cm-tabs{display:flex;gap:8px;margin-bottom:12px}.ceraldi-menu-module .cm-tabs button{flex:1;margin:0}.ceraldi-menu-module .cm-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}.ceraldi-menu-module .field{display:block;margin:0}.ceraldi-menu-module .field>span{display:block;font-size:12px;color:var(--ink3);font-weight:600;margin-bottom:6px}.ceraldi-menu-module .cm-muted{font-size:12px;color:var(--ink3);line-height:1.5}.ceraldi-menu-module .cm-count{font-size:12px;color:var(--ink3);margin:12px 0}.ceraldi-menu-module .cm-price{font-size:14px;font-weight:700;white-space:nowrap}.ceraldi-menu-module .cm-image{width:50px;height:50px;object-fit:cover;border-radius:10px;flex-shrink:0}.ceraldi-menu-module .cm-item .fi-nome{white-space:normal}.ceraldi-menu-module .cm-badge{padding:3px 7px;border-radius:6px;font-size:10px;background:var(--surface2);color:var(--ink3)}.ceraldi-menu-module .cm-ok{background:var(--green-light);color:var(--green)}.ceraldi-menu-module .cm-warn{background:var(--orange-light);color:var(--orange);padding:8px;border-radius:8px;font-size:12px}.ceraldi-menu-module .cm-badge.cm-warn{padding:3px 7px}.ceraldi-menu-module .cm-empty{padding:25px 15px;background:var(--surface);border-radius:var(--radius);text-align:center;color:var(--ink3);font-size:13px}.ceraldi-menu-module .cm-notice,.ceraldi-menu-module .cm-errors{margin:12px 0;padding:12px;border-radius:var(--radius-sm);font-size:13px;line-height:1.5}.ceraldi-menu-module .cm-error,.ceraldi-menu-module .cm-errors{background:var(--red-light);color:var(--red)}.ceraldi-menu-module .cm-success{background:var(--green-light);color:var(--ink2)}.ceraldi-menu-module .cm-errors p+p{margin-top:6px}.ceraldi-menu-module .cm-detail{padding:16px;background:var(--surface);border-radius:var(--radius);box-shadow:var(--shadow);margin:12px 0}.ceraldi-menu-module .cm-detail-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.ceraldi-menu-module .cm-detail-heading button{margin:0}.ceraldi-menu-module .cm-description{white-space:pre-line;font-size:13px;color:var(--ink2);margin:12px 0;line-height:1.5}.ceraldi-menu-module .cm-facts{margin:12px 0}.ceraldi-menu-module .cm-facts>div{display:flex;justify-content:space-between;gap:14px;padding:7px 0;border-bottom:1px solid var(--surface2);font-size:13px}.ceraldi-menu-module .cm-facts dt{color:var(--ink3)}.ceraldi-menu-module .cm-facts dd{font-weight:600;text-align:right}.ceraldi-menu-module .cm-link{color:var(--blue);font-size:13px;display:inline-block;margin:8px 0}.ceraldi-menu-module .cm-two{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.ceraldi-menu-module [hidden]{display:none!important}@media(max-width:600px){.ceraldi-menu-module .cm-header{display:block}.ceraldi-menu-module .cm-actions{margin-top:10px}.ceraldi-menu-module .cm-summary{grid-template-columns:1fr 1fr}.ceraldi-menu-module .cm-grid{grid-template-columns:1fr 1fr}.ceraldi-menu-module .cm-search{grid-column:1/-1}.ceraldi-menu-module .cm-price{font-size:12px}.ceraldi-menu-module .cm-two{grid-template-columns:1fr}}' +
      '</style><div class="cm-header"><div><h2>Menu e ricette</h2><p class="cm-muted">Prodotti, prezzi e disponibilità collegati al gestionale.</p></div><div class="cm-actions"><button class="btn btn-s cm-compact" data-menu-refresh>Aggiorna</button><a class="btn btn-p cm-compact" href="/menu/" target="_blank" rel="noopener">Menu clienti ↗</a></div></div>' +
      '<div class="cm-notice" data-menu-notice hidden></div><div class="cm-errors" data-menu-errors role="alert" hidden></div><div class="cm-summary" data-menu-summary></div>' +
      '<div class="cm-filters"><div class="cm-tabs" role="tablist" aria-label="Catalogo"><button class="btn btn-p cm-compact" role="tab" aria-selected="true" data-menu-tab="products">Prodotti del Menu</button><button class="btn btn-s cm-compact" role="tab" aria-selected="false" data-menu-tab="recipes">Ricette</button></div>' +
      '<div class="cm-grid"><label class="field cm-search"><span>Cerca</span><input type="search" data-menu-search placeholder="Nome, codice o ingrediente"></label><label class="field"><span data-menu-category-label>Categoria</span><select data-menu-category><option value="">Tutte le categorie</option></select></label><label class="field" data-menu-visibility><span>Visibilità</span><select data-menu-visibility-select><option value="all">Tutti</option><option value="visible">Visibili</option><option value="hidden">Nascosti</option></select></label></div></div>' +
      '<section class="cm-detail" data-menu-detail aria-label="Dettaglio prodotto" hidden></section><p class="cm-count" data-menu-count></p><div data-menu-list></div>';
    root.querySelector('[data-menu-refresh]').addEventListener('click', function () { refresh(state); });
    root.querySelector('[data-menu-search]').addEventListener('input', function (event) { state.search = event.target.value; state.limit = 100; renderList(state); });
    root.querySelector('[data-menu-category]').addEventListener('change', function (event) { state.category = event.target.value; state.limit = 100; renderList(state); });
    root.querySelector('[data-menu-visibility-select]').addEventListener('change', function (event) { state.visibility = event.target.value; state.limit = 100; renderList(state); });
    state.clickHandler = function (event) {
      var button = event.target.closest('[data-menu-action], [data-menu-tab]');
      if (!button || !root.contains(button)) return;
      if (button.hasAttribute('data-menu-tab')) {
        state.tab = button.getAttribute('data-menu-tab'); state.category = ''; state.limit = 100; clearDetail(state);
        root.querySelectorAll('[data-menu-tab]').forEach(function (tab) { var active = tab === button; tab.className = 'btn ' + (active ? 'btn-p' : 'btn-s') + ' cm-compact'; tab.setAttribute('aria-selected', String(active)); });
        categories(state); renderList(state);
      } else act(state, button).catch(function (error) { notice(state, message(error), true); });
    };
    root.addEventListener('click', state.clickHandler);
    render(state);
  }
  registry.register({ id: 'menu_gc', title: 'Menu', icon: '🍽️', mount: mount, onOpen: function (root, bridge) {
    var state = states.get(root);
    if (!state) { mount(root, bridge); state = states.get(root); }
    state.bridge = bridge;
    allowCanonicalApi(bridge);
    return refresh(state);
  } });
})();
