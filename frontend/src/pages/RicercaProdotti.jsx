import React, { useState, useEffect, useRef } from 'react';
import api from '../api';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function RicercaProdotti() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [exactSearch, setExactSearch] = useState(false); // Filtro esatto
  const [cart, setCart] = useState({});
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [err, setErr] = useState('');
  const searchTimeout = useRef(null);

  useEffect(() => {
    loadProducts();
    loadCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exactSearch]); // Ricarica quando cambia il tipo di ricerca

  async function loadProducts() {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedCategory) params.append('category', selectedCategory);
      if (searchQuery) params.append('search', searchQuery);
      params.append('days', '90');
      if (exactSearch) params.append('exact', 'true');

      const r = await api.get(`/api/products/catalog?${params}`);
      setProducts(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      console.error('Error loading products:', e);
      setErr('Errore caricamento prodotti');
    } finally {
      setLoading(false);
    }
  }

  async function loadCategories() {
    try {
      const r = await api.get('/api/products/categories');
      setCategories(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      console.error('Error loading categories:', e);
    }
  }

  async function handleSearch(query) {
    setSearchQuery(query);

    // Debounce per ricerca predittiva
    if (searchTimeout.current) clearTimeout(searchTimeout.current);

    if (query.length >= 2) {
      searchTimeout.current = setTimeout(async () => {
        try {
          const r = await api.get(`/api/products/search?q=${encodeURIComponent(query)}&limit=10`);
          setSuggestions(Array.isArray(r.data) ? r.data : []);
        } catch (e) {
          console.error('Error searching:', e);
        }
      }, 300);
    } else {
      setSuggestions([]);
    }
  }

  async function loadSuppliers(productId) {
    try {
      const r = await api.get(`/api/products/${productId}/suppliers?days=90`);
      setSuppliers(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      console.error('Error loading suppliers:', e);
      setSuppliers([]);
    }
  }

  function selectSuggestion(product) {
    setSearchQuery(product.nome || '');
    setSuggestions([]);
    loadProducts();
  }

  function selectProduct(product) {
    if (selectedProduct?.id === product.id) {
      setSelectedProduct(null);
      setSuppliers([]);
    } else {
      setSelectedProduct(product);
      loadSuppliers(product.id);
    }
  }

  function addToCart(product, supplier = null) {
    const key = `${product.id}_${supplier?.supplier_name || product.best_supplier || 'default'}`;
    const supplierName = supplier?.supplier_name || product.best_supplier || 'Fornitore';
    const price = supplier?.last_price || product.best_price || product.prezzi?.avg || 0;

    setCart(prev => ({
      ...prev,
      [key]: {
        product_id: product.id,
        product_name: product.nome,
        supplier_name: supplierName,
        price: price,
        unit: product.unita_misura,
        quantity: (prev[key]?.quantity || 0) + 1,
      },
    }));
  }

  function updateCartQuantity(key, delta) {
    setCart(prev => {
      const newQty = (prev[key]?.quantity || 0) + delta;
      if (newQty <= 0) {
        const { [key]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [key]: { ...prev[key], quantity: newQty } };
    });
  }

  function removeFromCart(key) {
    setCart(prev => {
      const { [key]: _, ...rest } = prev;
      return rest;
    });
  }

  // Raggruppa carrello per fornitore
  const cartBySupplier = Object.entries(cart).reduce((acc, [key, item]) => {
    const supplier = item.supplier_name;
    if (!acc[supplier]) acc[supplier] = [];
    acc[supplier].push({ key, ...item });
    return acc;
  }, {});

  // Calcola totale carrello
  const cartTotal = Object.values(cart).reduce((sum, item) => sum + item.price * item.quantity, 0);
  const cartItemCount = Object.values(cart).reduce((sum, item) => sum + item.quantity, 0);

  // Invia ordine
  const [sendingOrder, setSendingOrder] = useState(false);

  async function handleSendOrder() {
    if (cartItemCount === 0) {
      alert('Il carrello è vuoto!');
      return;
    }

    setSendingOrder(true);
    try {
      // Raggruppa per fornitore
      const ordersData = Object.entries(cartBySupplier).map(([supplier, items]) => ({
        fornitore: supplier,
        prodotti: items.map(item => ({
          nome: item.product_name,
          quantita: item.quantity,
          unita: item.unit,
          prezzo_unitario: item.price,
          totale: item.price * item.quantity,
        })),
        totale: items.reduce((s, i) => s + i.price * i.quantity, 0),
      }));

      // Salva ordine nel database
      await api.post('/api/orders', {
        ordini: ordersData,
        totale_generale: cartTotal,
        data_creazione: new Date().toISOString(),
        stato: 'da_inviare',
      });

      alert(
        `✅ Ordine creato con successo!\n\n${ordersData.length} ordini per un totale di €${cartTotal.toFixed(2)}`
      );
      setCart({});
    } catch (error) {
      console.error('Error sending order:', error);
      // Se l'API non esiste, mostra comunque il riepilogo
      const riepilogo = Object.entries(cartBySupplier)
        .map(([supplier, items]) => {
          const tot = items.reduce((s, i) => s + i.price * i.quantity, 0);
          return `📦 ${supplier}: ${items.length} prodotti - €${tot.toFixed(2)}`;
        })
        .join('\n');

      alert(
        `📋 Riepilogo Ordine:\n\n${riepilogo}\n\nTOTALE: €${cartTotal.toFixed(2)}\n\n(Funzione salvataggio ordine in sviluppo)`
      );
    } finally {
      setSendingOrder(false);
    }
  }

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    padding: 20,
    marginBottom: 20,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: '1px solid #e5e7eb',
  };
  const h1Style = { fontSize: 24, fontWeight: 'bold', color: '#1e293b', marginBottom: 12 };
  const smallStyle = { fontSize: 13, color: '#64748b' };
  const rowStyle = { display: 'flex', alignItems: 'center' };
  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
    gap: 16,
  };
  const btnPrimary = {
    padding: '10px 18px',
    background: '#3b82f6',
    color: 'white',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: '600',
  };

  return (
    <PageLayout
      title="Ordini Fornitori"
      subtitle="Cerca prodotti, confronta prezzi per fornitore e crea ordini raggruppati"
    >
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {/* Header con ricerca */}
        <div style={cardStyle}>
          <div style={h1Style}>Ricerca e Ordini</div>
          <div style={{ ...smallStyle, marginBottom: 15 }}>
            Catalogo prodotti popolato automaticamente dalle fatture XML. Trova il miglior prezzo,
            aggiungi al carrello e invia ordini per fornitore.
          </div>

          <div style={{ ...rowStyle, gap: 10, flexWrap: 'wrap', position: 'relative' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
              <input
                type="text"
                placeholder="Cerca prodotto..."
                value={searchQuery}
                onChange={e => handleSearch(e.target.value)}
                style={{ width: '100%' }}
                data-testid="product-search-input"
              />

              {/* Suggerimenti ricerca predittiva */}
              {suggestions.length > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    background: 'white',
                    border: '1px solid #ddd',
                    borderRadius: 8,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    zIndex: 1000,
                    maxHeight: 300,
                    overflow: 'auto',
                  }}
                >
                  {suggestions.map((s, i) => (
                    <div
                      key={s.id || i}
                      onClick={() => selectSuggestion(s)}
                      style={{
                        padding: '10px 15px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #eee',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        transition: 'background 0.2s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#f5f5f5')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'white')}
                    >
                      <div>
                        <strong>{s.nome?.substring(0, 50)}</strong>
                        <div style={smallStyle}>
                          {s.categoria} | {s.best_supplier}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span style={{ color: '#2e7d32', fontWeight: 'bold' }}>
                          €{(s.best_price || 0).toFixed(2)}
                        </span>
                        <div style={{ ...smallStyle, color: '#999' }}>Match: {s.match_score}%</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Toggle Ricerca Esatta */}
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                cursor: 'pointer',
                padding: '8px 12px',
                background: exactSearch ? '#e3f2fd' : '#f5f5f5',
                borderRadius: 8,
                border: `1px solid ${exactSearch ? '#1565c0' : '#ddd'}`,
                fontSize: 13,
                fontWeight: exactSearch ? 'bold' : 'normal',
                color: exactSearch ? '#1565c0' : '#666',
              }}
            >
              <input
                type="checkbox"
                checked={exactSearch}
                onChange={e => setExactSearch(e.target.checked)}
                style={{ width: 16, height: 16, cursor: 'pointer' }}
              />
              🎯 Ricerca Esatta
            </label>

            <select
              value={selectedCategory}
              onChange={e => setSelectedCategory(e.target.value)}
              style={{ minWidth: 150 }}
            >
              <option value="">Tutte le categorie</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>

            <button onClick={loadProducts} style={btnPrimary} data-testid="search-btn">
              🔍 Cerca
            </button>
          </div>

          {err && <div style={{ ...smallStyle, color: '#c00', marginTop: 10 }}>{err}</div>}
        </div>

        {/* Carrello */}
        {cartItemCount > 0 && (
          <div style={{ ...cardStyle, background: '#dbeafe' }}>
            <div style={h1Style}>
              🛒 Carrello ({cartItemCount} prodotti)
              <span style={{ float: 'right', color: '#1565c0' }}>€{cartTotal.toFixed(2)}</span>
            </div>

            {Object.entries(cartBySupplier).map(([supplier, items]) => (
              <div
                key={supplier}
                style={{ marginBottom: 15, padding: 10, background: 'white', borderRadius: 8 }}
              >
                <div
                  style={{
                    fontWeight: 'bold',
                    marginBottom: 10,
                    borderBottom: '1px solid #eee',
                    paddingBottom: 5,
                  }}
                >
                  📦 {supplier}
                  <span style={{ float: 'right', fontSize: 12 }}>
                    Totale: €{items.reduce((s, i) => s + i.price * i.quantity, 0).toFixed(2)}
                  </span>
                </div>

                {items.map(item => (
                  <div
                    key={item.key}
                    style={{ display: 'flex', alignItems: 'center', marginBottom: 5, gap: 10 }}
                  >
                    <span style={{ flex: 1 }}>{item.product_name?.substring(0, 40)}</span>
                    <span>€{item.price.toFixed(2)}</span>
                    <button onClick={() => updateCartQuantity(item.key, -1)}>-</button>
                    <span style={{ minWidth: 30, textAlign: 'center' }}>{item.quantity}</span>
                    <button onClick={() => updateCartQuantity(item.key, 1)}>+</button>
                    <button onClick={() => removeFromCart(item.key)} style={{ color: '#c00' }}>
                      🗑️
                    </button>
                  </div>
                ))}
              </div>
            ))}

            <div style={{ display: 'flex', gap: 10, marginTop: 15 }}>
              <button onClick={() => setCart({})} style={{ flex: 1 }}>
                🗑️ Svuota Carrello
              </button>
              <button
                onClick={handleSendOrder}
                disabled={sendingOrder}
                data-testid="send-order-btn"
                style={{
                  flex: 2,
                  background: sendingOrder
                    ? '#ccc'
                    : '#15803d',
                  color: 'white',
                  fontWeight: 'bold',
                  fontSize: 16,
                  cursor: sendingOrder ? 'not-allowed' : 'pointer',
                }}
              >
                {sendingOrder
                  ? '⏳ Invio in corso...'
                  : `📤 Invia Ordine (€${cartTotal.toFixed(2)})`}
              </button>
            </div>
          </div>
        )}

        {/* Statistiche */}
        <div style={{ ...cardStyle, background: '#f8fafc' }}>
          <div style={gridStyle}>
            <div>
              <strong>Prodotti nel catalogo</strong>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1565c0' }}>
                {products.length}
              </div>
            </div>
            <div>
              <strong>Categorie</strong>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#2e7d32' }}>
                {categories.length}
              </div>
            </div>
            <div>
              <strong>Nel carrello</strong>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#e65100' }}>
                {cartItemCount}
              </div>
            </div>
          </div>
        </div>

        {/* Lista Prodotti */}
        <div style={cardStyle}>
          <div style={h1Style}>Catalogo ({products.length} prodotti)</div>

          {loading ? (
            <div style={smallStyle}>Caricamento catalogo...</div>
          ) : products.length === 0 ? (
            <div style={smallStyle}>
              Nessun prodotto trovato. Il catalogo si popola automaticamente quando carichi fatture
              XML.
            </div>
          ) : (
            <div>
              {products.slice(0, 100).map((p, i) => (
                <div
                  key={p.id || i}
                  style={{
                    border: selectedProduct?.id === p.id ? '2px solid #1565c0' : '1px solid #eee',
                    borderRadius: 8,
                    padding: 15,
                    marginBottom: 10,
                    cursor: 'pointer',
                    background: selectedProduct?.id === p.id ? '#e3f2fd' : 'white',
                  }}
                  onClick={() => selectProduct(p)}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <strong>{p.nome?.substring(0, 60)}</strong>
                      <div style={{ ...smallStyle, marginTop: 3 }}>
                        Categoria:{' '}
                        <span
                          style={{
                            background: '#e3f2fd',
                            padding: '2px 8px',
                            borderRadius: 4,
                          }}
                        >
                          {p.categoria}
                        </span>
                        {' | '}Giacenza: {(p.giacenza || 0).toFixed(1)} {p.unita_misura}
                      </div>
                    </div>

                    <div style={{ textAlign: 'right', minWidth: 120 }}>
                      <div style={{ color: '#2e7d32', fontSize: 18, fontWeight: 'bold' }}>
                        €{(p.best_price || p.prezzi?.avg || 0).toFixed(2)}
                      </div>
                      <div style={smallStyle}>{p.best_supplier?.substring(0, 20)}</div>
                    </div>

                    <button
                      onClick={e => {
                        e.stopPropagation();
                        addToCart(p);
                      }}
                      style={{ marginLeft: 10, background: '#4caf50', color: 'white' }}
                    >
                      + Carrello
                    </button>
                  </div>

                  {/* Dettaglio Fornitori */}
                  {selectedProduct?.id === p.id && suppliers.length > 0 && (
                    <div style={{ marginTop: 15, paddingTop: 15, borderTop: '1px solid #ddd' }}>
                      <strong>Fornitori e Prezzi (ultimi 90 giorni)</strong>
                      <table style={{ width: '100%', marginTop: 10, fontSize: 13 }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                            <th style={{ padding: 5 }}>Fornitore</th>
                            <th style={{ padding: 5 }}>Min</th>
                            <th style={{ padding: 5 }}>Max</th>
                            <th style={{ padding: 5 }}>Media</th>
                            <th style={{ padding: 5 }}>Ultimo</th>
                            <th style={{ padding: 5 }}>Acquisti</th>
                            <th style={{ padding: 5 }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {suppliers.map((s, si) => (
                            <tr
                              key={si}
                              style={{
                                borderBottom: '1px solid #eee',
                                background: si === 0 ? '#e8f5e9' : 'transparent',
                              }}
                            >
                              <td style={{ padding: 5 }}>
                                {s.supplier_name?.substring(0, 30)}
                                {si === 0 && (
                                  <span style={{ color: '#2e7d32', marginLeft: 5 }}>⭐ Best</span>
                                )}
                              </td>
                              <td style={{ padding: 5 }}>€{s.min_price.toFixed(2)}</td>
                              <td style={{ padding: 5 }}>€{s.max_price.toFixed(2)}</td>
                              <td style={{ padding: 5 }}>€{s.avg_price.toFixed(2)}</td>
                              <td style={{ padding: 5 }}>€{s.last_price.toFixed(2)}</td>
                              <td style={{ padding: 5 }}>{s.purchase_count}x</td>
                              <td style={{ padding: 5 }}>
                                <button
                                  onClick={e => {
                                    e.stopPropagation();
                                    addToCart(p, s);
                                  }}
                                  style={{ fontSize: 12 }}
                                >
                                  Aggiungi
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {selectedProduct?.id === p.id && suppliers.length === 0 && (
                    <div style={{ marginTop: 15, paddingTop: 15, borderTop: '1px solid #ddd' }}>
                      <span style={smallStyle}>
                        Nessuno storico prezzi disponibile per questo prodotto.
                      </span>
                    </div>
                  )}
                </div>
              ))}

              {products.length > 100 && (
                <div style={{ ...smallStyle, textAlign: 'center', padding: 20 }}>
                  Mostrati 100 di {products.length} prodotti. Usa la ricerca per trovare altri
                  prodotti.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Informazioni */}
        <div style={cardStyle}>
          <div style={h1Style}>Come Funziona</div>
          <ul style={{ paddingLeft: 20 }}>
            <li>
              <strong>Auto-popolamento:</strong> Ogni fattura XML caricata aggiunge automaticamente
              i prodotti al catalogo
            </li>
            <li>
              <strong>Best Price:</strong> Il sistema calcola il miglior prezzo degli ultimi 90
              giorni per ogni prodotto
            </li>
            <li>
              <strong>Storico Prezzi:</strong> Clicca su un prodotto per vedere tutti i fornitori e
              confrontare i prezzi
            </li>
            <li>
              <strong>Carrello:</strong> Aggiungi prodotti al carrello per creare ordini raggruppati
              per fornitore
            </li>
          </ul>
        </div>
      </div>
    </PageLayout>
  );
}
