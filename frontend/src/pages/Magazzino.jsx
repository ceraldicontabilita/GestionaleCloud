import React, { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation } from 'react-router-dom';
import api from "../api";
import { formatDateIT, formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading, PageEmpty } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Package, Plus, RefreshCw, Search, Filter, X, Trash2 } from 'lucide-react';

export default function Magazzino() {
  const [products, setProducts] = useState([]);
  const [catalogProducts, setCatalogProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [err, setErr] = useState("");
  
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const match = location.pathname.match(/\/magazzino\/([\w-]+)/);
    return match ? match[1] : 'catalogo';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/magazzino/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [showLowStock, setShowLowStock] = useState(false);
  
  const [newProduct, setNewProduct] = useState({
    name: "", code: "", quantity: "", unit: "pz", price: "", category: ""
  });

  useEffect(() => {
    loadProducts();
  }, []);

  async function loadProducts() {
    try {
      setLoading(true);
      const [warehouseRes, catalogRes] = await Promise.all([
        api.get("/api/warehouse/products"),
        api.get("/api/products/catalog").catch(() => ({ data: [] }))
      ]);
      setProducts(Array.isArray(warehouseRes.data) ? warehouseRes.data : warehouseRes.data?.items || []);
      setCatalogProducts(Array.isArray(catalogRes.data) ? catalogRes.data : []);
    } catch (e) {
      console.error("Error loading products:", e);
    } finally {
      setLoading(false);
    }
  }

  const categories = useMemo(() => {
    const cats = new Set(catalogProducts.map(p => p.categoria).filter(Boolean));
    return Array.from(cats).sort();
  }, [catalogProducts]);

  const suppliers = useMemo(() => {
    const supps = new Set(catalogProducts.map(p => p.ultimo_fornitore).filter(Boolean));
    return Array.from(supps).sort();
  }, [catalogProducts]);

  const filteredProducts = useMemo(() => {
    return catalogProducts.filter(p => {
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matches = (p.nome || '').toLowerCase().includes(q) ||
                       (p.ultimo_fornitore || '').toLowerCase().includes(q) ||
                       (p.categoria || '').toLowerCase().includes(q);
        if (!matches) return false;
      }
      if (categoryFilter && p.categoria !== categoryFilter) return false;
      if (supplierFilter && p.ultimo_fornitore !== supplierFilter) return false;
      if (showLowStock && (p.giacenza || 0) > (p.giacenza_minima || 0)) return false;
      return true;
    });
  }, [catalogProducts, searchQuery, categoryFilter, supplierFilter, showLowStock]);

  const stats = useMemo(() => {
    const total = filteredProducts.length;
    const totalValue = filteredProducts.reduce((sum, p) => {
      return sum + ((p.prezzi?.avg || 0) * (p.giacenza || 0));
    }, 0);
    const lowStock = filteredProducts.filter(p => (p.giacenza || 0) <= (p.giacenza_minima || 0)).length;
    const categorieCounts = {};
    filteredProducts.forEach(p => {
      const cat = p.categoria || 'altro';
      categorieCounts[cat] = (categorieCounts[cat] || 0) + 1;
    });
    return { total, totalValue, lowStock, categorieCounts };
  }, [filteredProducts]);

  async function handleCreateProduct(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.post("/api/warehouse/products", {
        name: newProduct.name,
        code: newProduct.code,
        quantity: parseFloat(newProduct.quantity) || 0,
        unit: newProduct.unit,
        unit_price: parseFloat(newProduct.price) || 0,
        category: newProduct.category
      });
      setShowForm(false);
      setNewProduct({ name: "", code: "", quantity: "", unit: "pz", price: "", category: "" });
      loadProducts();
    } catch (e) {
      setErr("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  async function handleDelete(id) {
    try {
      await api.delete(`/api/warehouse/products/${id}`);
      loadProducts();
    } catch (e) {
      setErr("Errore eliminazione: " + (e.response?.data?.detail || e.message));
    }
  }

  const resetFilters = () => {
    setSearchQuery('');
    setCategoryFilter('');
    setSupplierFilter('');
    setShowLowStock(false);
  };

  const hasFilters = searchQuery || categoryFilter || supplierFilter || showLowStock;

  const inputStyle = {
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #e2e8f0',
    fontSize: 14
  };

  const KPICard = ({ label, value, subValue, color, bgColor, borderColor }) => (
    <div style={{ background: bgColor, padding: 16, borderRadius: 12, border: `1px solid ${borderColor}` }}>
      <div style={{ fontSize: 12, color, fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color.replace('0.8', '1') }}>{value}</div>
      {subValue && <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>{subValue}</div>}
    </div>
  );

  return (
    <PageLayout
      title="Magazzino"
      icon={<Package size={28} />}
      subtitle="Gestione prodotti e inventario"
      actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <button 
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: '10px 16px',
              background: '#16a34a',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <Plus size={16} /> Nuovo Prodotto
          </button>
          <button 
            onClick={loadProducts}
            style={{
              padding: '10px 16px',
              background: '#f1f5f9',
              color: '#475569',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <RefreshCw size={16} /> Aggiorna
          </button>
        </div>
      }
    >
      {err && (
        <div style={{ padding: 16, background: "#fee2e2", border: "1px solid #fecaca", borderRadius: 8, color: "#dc2626", marginBottom: 20 }}>
          {err}
        </div>
      )}

      {/* Statistiche */}
      {activeTab === 'catalogo' && (
        <PageGrid cols={4} gap={12}>
          <KPICard label="Prodotti Totali" value={stats.total} color="#0369a1" bgColor="#f0f9ff" borderColor="#bae6fd" />
          <KPICard label="Valore Stimato" value={formatEuro(stats.totalValue)} color="#16a34a" bgColor="#f0fdf4" borderColor="#bbf7d0" />
          <KPICard 
            label="Scorte Basse" 
            value={stats.lowStock} 
            color={stats.lowStock > 0 ? '#dc2626' : '#64748b'} 
            bgColor={stats.lowStock > 0 ? '#fef2f2' : '#f8fafc'} 
            borderColor={stats.lowStock > 0 ? '#fecaca' : '#e2e8f0'} 
          />
          <KPICard label="Categorie" value={categories.length} color="#ca8a04" bgColor="#fefce8" borderColor="#fef08a" />
        </PageGrid>
      )}

      {/* Filtri */}
      {activeTab === 'catalogo' && (
        <PageSection title="Filtri" icon={<Filter size={16} />} style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
            <div style={{ flex: 2, minWidth: 200, position: 'relative' }}>
              <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                placeholder="Cerca prodotto, fornitore..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ ...inputStyle, width: '100%', paddingLeft: 36 }}
              />
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              style={{ ...inputStyle, flex: 1, minWidth: 150 }}
            >
              <option value="">Tutte le categorie</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>{cat} ({stats.categorieCounts[cat] || 0})</option>
              ))}
            </select>
            <select
              value={supplierFilter}
              onChange={(e) => setSupplierFilter(e.target.value)}
              style={{ ...inputStyle, flex: 1, minWidth: 150 }}
            >
              <option value="">Tutti i fornitori</option>
              {suppliers.map(sup => (<option key={sup} value={sup}>{sup}</option>))}
            </select>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={showLowStock} onChange={(e) => setShowLowStock(e.target.checked)} />
              Solo scorte basse
            </label>
            {hasFilters && (
              <button onClick={resetFilters} style={{ padding: '8px 16px', borderRadius: 8, background: '#fee2e2', color: '#dc2626', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: 13 }}>
                <X size={14} style={{ marginRight: 4 }} /> Reset
              </button>
            )}
          </div>
        </PageSection>
      )}

      {/* Form Nuovo Prodotto */}
      {showForm && (
        <PageSection title="Nuovo Prodotto" icon={<Plus size={16} />} style={{ marginTop: 16 }}>
          <form onSubmit={handleCreateProduct}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              <input style={{ ...inputStyle, flex: 2, minWidth: 200 }} placeholder="Nome Prodotto" value={newProduct.name} onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })} required />
              <input style={{ ...inputStyle, width: 120 }} placeholder="Codice" value={newProduct.code} onChange={(e) => setNewProduct({ ...newProduct, code: e.target.value })} />
              <input style={{ ...inputStyle, width: 100 }} type="number" placeholder="Qtà" value={newProduct.quantity} onChange={(e) => setNewProduct({ ...newProduct, quantity: e.target.value })} required />
              <select style={inputStyle} value={newProduct.unit} onChange={(e) => setNewProduct({ ...newProduct, unit: e.target.value })}>
                <option value="pz">Pezzi</option>
                <option value="kg">Kg</option>
                <option value="lt">Litri</option>
              </select>
              <input style={{ ...inputStyle, width: 100 }} type="number" step="0.01" placeholder="€ Prezzo" value={newProduct.price} onChange={(e) => setNewProduct({ ...newProduct, price: e.target.value })} />
              <input style={{ ...inputStyle, width: 150 }} placeholder="Categoria" value={newProduct.category} onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button type="submit" style={{ padding: '10px 20px', background: '#16a34a', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>Salva</button>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 8, cursor: 'pointer' }}>Annulla</button>
            </div>
          </form>
        </PageSection>
      )}

      {/* Tabs */}
      <div style={{ marginTop: 20, background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #dce8f4' }}>
        <div style={{ display: 'flex', borderBottom: '2px solid #e2e8f0' }}>
          <button
            onClick={() => handleTabChange('catalogo')}
            style={{
              flex: 1, padding: '14px 20px',
              background: activeTab === 'catalogo' ? '#1e293b' : 'transparent',
              color: activeTab === 'catalogo' ? 'white' : '#64748b',
              border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: 14
            }}
          >
            📦 Catalogo Prodotti ({filteredProducts.length}{filteredProducts.length !== catalogProducts.length ? ` / ${catalogProducts.length}` : ''})
          </button>
          <button
            onClick={() => handleTabChange('manuale')}
            style={{
              flex: 1, padding: '14px 20px',
              background: activeTab === 'manuale' ? '#1e293b' : 'transparent',
              color: activeTab === 'manuale' ? 'white' : '#64748b',
              border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: 14
            }}
          >
            📋 Inventario Manuale ({products.length})
          </button>
        </div>
        
        <div style={{ padding: 20 }}>
          {loading ? (
            <PageLoading message="Caricamento prodotti..." />
          ) : activeTab === 'catalogo' ? (
            filteredProducts.length === 0 ? (
              <PageEmpty icon="📦" message={catalogProducts.length === 0 ? "I prodotti verranno aggiunti automaticamente dalle fatture XML" : "Nessun prodotto trovato. Prova a modificare i filtri."} />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid #e2e8f0", background: '#f8fafc' }}>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Prodotto</th>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Categoria</th>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Fornitore</th>
                      <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Giacenza</th>
                      <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Prezzo Min</th>
                      <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Prezzo Max</th>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Ultimo Acquisto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProducts.slice(0, 200).map((p, i) => (
                      <tr key={p.id || p.product_id || i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: 12 }}>
                          <div style={{ fontWeight: 500 }}>{p.nome || p.name || '-'}</div>
                          {p.unita_misura && <span style={{ fontSize: 11, color: '#94a3b8' }}>{p.unita_misura}</span>}
                        </td>
                        <td style={{ padding: 12 }}>
                          <span style={{ background: '#f1f5f9', padding: '3px 8px', borderRadius: 4, fontSize: 11 }}>{p.categoria || 'altro'}</span>
                        </td>
                        <td style={{ padding: 12, color: '#64748b' }}>{p.ultimo_fornitore || '-'}</td>
                        <td style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>{(p.giacenza || 0).toFixed(2)}</td>
                        <td style={{ padding: 12, textAlign: 'right', color: '#16a34a' }}>{formatEuro(p.prezzi?.min || 0)}</td>
                        <td style={{ padding: 12, textAlign: 'right', color: '#64748b' }}>{formatEuro(p.prezzi?.max || 0)}</td>
                        <td style={{ padding: 12, color: '#64748b' }}>{p.ultimo_acquisto ? formatDateIT(p.ultimo_acquisto) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            products.length === 0 ? (
              <PageEmpty icon="📦" message="Nessun prodotto nel magazzino manuale. Clicca '+ Nuovo Prodotto' per aggiungerne uno." />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid #e2e8f0", background: '#f8fafc' }}>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Codice</th>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Nome</th>
                      <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Quantità</th>
                      <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Prezzo</th>
                      <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Categoria</th>
                      <th style={{ padding: 12, textAlign: 'center', fontWeight: 600 }}>Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((p, i) => (
                      <tr key={p.id || i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: 12, fontFamily: 'monospace' }}>{p.code || "-"}</td>
                        <td style={{ padding: 12, fontWeight: 500 }}>{p.name}</td>
                        <td style={{ padding: 12, textAlign: 'right' }}>{p.quantity} {p.unit}</td>
                        <td style={{ padding: 12, textAlign: 'right', color: '#16a34a' }}>{formatEuro(p.unit_price || 0)}</td>
                        <td style={{ padding: 12 }}>{p.category || "-"}</td>
                        <td style={{ padding: 12, textAlign: 'center' }}>
                          <button onClick={() => handleDelete(p.id)} style={{ padding: '6px 10px', background: '#fef2f2', color: '#dc2626', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>
      </div>
    </PageLayout>
  );
}
