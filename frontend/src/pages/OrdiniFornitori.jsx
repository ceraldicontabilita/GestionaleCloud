import React, { useState, useEffect } from "react";
import api from "../api";
import { formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';

// Dati azienda per intestazione email/PDF
const AZIENDA = {
  nome: "CERALDI GROUP S.R.L.",
  indirizzo: "Via Example, 123",
  cap: "00100",
  citta: "Roma",
  piva: "12345678901",
  email: "ordini@ceraldi.it",
  tel: "+39 06 12345678"
};

const styles = {
  container: {
    padding: 12,
    maxWidth: 1400,
    margin: '0 auto'
  },
  card: {
    background: 'white',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    border: '1px solid #e5e7eb'
  },
  cardOrange: {
    background: '#fff7ed',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    border: '1px solid #fed7aa'
  },
  cardGreen: {
    background: '#f0fdf4',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    border: '1px solid #bbf7d0'
  },
  header: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1e293b',
    marginBottom: 8,
    display: 'flex',
    alignItems: 'center',
    gap: 6
  },
  subtitle: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 10
  },
  row: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
    flexWrap: 'wrap'
  },
  btnPrimary: {
    padding: '6px 12px',
    background: '#1535a8',
    color: 'white',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 12
  },
  btnSuccess: {
    padding: '6px 12px',
    background: '#15803d',
    color: 'white',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 12
  },
  btnSecondary: {
    padding: '5px 10px',
    background: '#f1f5f9',
    color: '#475569',
    border: '1px solid #e2e8f0',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11
  },
  error: {
    background: '#fef2f2',
    color: '#dc2626',
    padding: 8,
    borderRadius: 6,
    marginBottom: 10,
    fontSize: 12,
    border: '1px solid #fecaca'
  },
  success: {
    background: '#f0fdf4',
    color: '#166534',
    padding: 8,
    borderRadius: 6,
    marginBottom: 10,
    fontSize: 12,
    border: '1px solid #bbf7d0'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12
  },
  th: {
    padding: 8,
    textAlign: 'left',
    fontWeight: '600',
    color: '#475569',
    borderBottom: '2px solid #e2e8f0',
    background: '#f8fafc',
    fontSize: 11
  },
  td: {
    padding: 8,
    borderBottom: '1px solid #f1f5f9'
  },
  supplierCard: {
    background: 'white',
    padding: 10,
    borderRadius: 8,
    marginBottom: 10,
    border: '1px solid #fed7aa'
  },
  emptyState: {
    textAlign: 'center',
    padding: 24,
    color: '#64748b',
    fontSize: 13
  },
  modal: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999
  },
  modalContent: {
    background: 'white',
    borderRadius: 10,
    width: '90%',
    maxWidth: 650,
    maxHeight: '80vh',
    overflow: 'auto'
  },
  modalHeader: {
    padding: 14,
    borderBottom: '1px solid #eee',
    background: '#1535a8',
    color: 'white',
    borderRadius: '10px 10px 0 0'
  },
  grid4: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))',
    gap: 10
  },
  statCard: {
    textAlign: 'center',
    padding: 8
  }
};

export default function OrdiniFornitori() {
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState({ by_supplier: [], total_items: 0, total_amount: 0 });
  const [orders, setOrders] = useState([]);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");
  const [generatingOrder, setGeneratingOrder] = useState(null);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [sendingEmail, setSendingEmail] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [cartRes, ordersRes] = await Promise.all([
        api.get("/api/comparatore/cart"),
        api.get("/api/ordini-fornitori")
      ]);
      setCart(cartRes.data || { by_supplier: [], total_items: 0, total_amount: 0 });
      setOrders(ordersRes.data || []);
    } catch (e) {
      console.error("Error loading data:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateOrder(supplier) {
    setGeneratingOrder(supplier.supplier);
    setErr("");
    setSuccess("");
    
    try {
      const orderData = {
        supplier_name: supplier.supplier,
        items: supplier.items.map(item => ({
          product_name: item.normalized_name || item.original_description,
          description: item.original_description,
          quantity: item.quantity || 1,
          unit_price: item.price,
          unit: item.unit || "PZ"
        })),
        subtotal: supplier.subtotal,
        notes: ""
      };
      
      const res = await api.post("/api/ordini-fornitori", orderData);
      setSuccess(`Ordine #${res.data.order_number} generato per ${supplier.supplier}`);
      
      for (const item of supplier.items) {
        try {
          await api.delete(`/api/comparatore/cart/${item.id}`);
        } catch (e) {
          console.warn("Errore rimozione item carrello:", e);
        }
      }
      
      loadData();
    } catch (e) {
      setErr("Errore generazione ordine: " + (e.response?.data?.detail || e.message));
    } finally {
      setGeneratingOrder(null);
    }
  }

  async function handleDeleteOrder(orderId) {
    try {
      await api.delete(`/api/ordini-fornitori/${orderId}`);
      setSuccess("Ordine eliminato");
      loadData();
    } catch (e) {
      setErr("Errore eliminazione: " + (e.response?.data?.detail || e.message));
    }
  }

  async function handleUpdateStatus(orderId, newStatus) {
    try {
      await api.put(`/api/ordini-fornitori/${orderId}`, { status: newStatus });
      setSuccess(`Stato aggiornato a "${newStatus}"`);
      loadData();
    } catch (e) {
      setErr("Errore aggiornamento: " + (e.response?.data?.detail || e.message));
    }
  }

  function handlePrintOrder(order) {
    const printWindow = window.open('', '_blank');
    const imponibile = order.subtotal || order.total || 0;
    const iva = imponibile * 0.22;
    const totale = imponibile + iva;
    
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Ordine #${order.order_number}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
          .header { border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }
          .company { font-size: 22px; font-weight: bold; color: #1535a8; }
          .info { color: #666; font-size: 12px; margin-top: 5px; }
          .order-info { display: flex; justify-content: space-between; margin-bottom: 30px; }
          .order-box { background: #f5f5f5; padding: 15px; border-radius: 8px; }
          table { width: 100%; border-collapse: collapse; margin: 20px 0; }
          th { background: #1535a8; color: white; padding: 12px; text-align: left; }
          td { padding: 10px; border-bottom: 1px solid #ddd; }
          .totals { text-align: right; margin-top: 20px; }
          .totals div { margin: 5px 0; }
          .total-row { font-size: 18px; font-weight: bold; color: #1535a8; }
          .footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 11px; color: #999; }
          @media print { body { padding: 20px; } }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="company">${AZIENDA.nome}</div>
          <div class="info">${AZIENDA.indirizzo} - ${AZIENDA.cap} ${AZIENDA.citta}</div>
          <div class="info">P.IVA: ${AZIENDA.piva} | Tel: ${AZIENDA.tel} | Email: ${AZIENDA.email}</div>
        </div>
        <div class="order-info">
          <div class="order-box"><strong>ORDINE N°</strong><br/><span style="font-size: 24px; color: #1535a8;">#${order.order_number}</span></div>
          <div class="order-box"><strong>DATA</strong><br/>${new Date(order.created_at).toLocaleDateString('it-IT', { day: '2-digit', month: 'long', year: 'numeric' })}</div>
          <div class="order-box"><strong>FORNITORE</strong><br/>${order.supplier_name}</div>
        </div>
        <h3 style="color: #1535a8;">DETTAGLIO PRODOTTI</h3>
        <table>
          <thead><tr><th>Prodotto</th><th>Quantità</th><th style="text-align: right;">Prezzo Unit.</th><th style="text-align: right;">Totale</th></tr></thead>
          <tbody>
            ${(order.items || []).map(item => `
              <tr>
                <td>${item.product_name || item.description}</td>
                <td>${item.quantity || 1} ${item.unit || 'PZ'}</td>
                <td style="text-align: right;">€ ${(item.unit_price || 0).toFixed(2)}</td>
                <td style="text-align: right;">€ ${((item.unit_price || 0) * (item.quantity || 1)).toFixed(2)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        <div class="totals">
          <div>Imponibile: € ${imponibile.toFixed(2)}</div>
          <div>IVA (22%): € ${iva.toFixed(2)}</div>
          <div class="total-row">TOTALE: € ${totale.toFixed(2)}</div>
        </div>
        ${order.notes ? `<div style="margin-top: 30px; padding: 15px; background: #fff3cd; border-radius: 8px;"><strong>Note:</strong> ${order.notes}</div>` : ''}
        <div class="footer">Documento generato il ${new Date().toLocaleDateString('it-IT')} - ${AZIENDA.nome}</div>
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  }

  async function handleSendEmail(order) {
    let supplierEmail = order.supplier_email;
    if (!supplierEmail) {
      supplierEmail = window.prompt(`Inserisci email del fornitore "${order.supplier_name}":`, '');
      if (!supplierEmail || !supplierEmail.includes('@')) {
        setErr("Email non valida o annullata");
        return;
      }
    }
    
    setSendingEmail(order.id);
    setErr("");
    
    try {
      const response = await api.post(`/api/ordini-fornitori/${order.id}/send-email`, { email: supplierEmail });
      setSuccess(`✅ Email inviata con successo a ${response.data.email}! Ordine #${order.order_number} con PDF allegato.`);
      loadData();
    } catch (e) {
      const errorMsg = e.response?.data?.detail || e.message;
      setErr("Errore invio email: " + errorMsg);
    } finally {
      setSendingEmail(null);
    }
  }
  
  async function handleDownloadPDF(order) {
    try {
      const response = await api.get(`/api/ordini-fornitori/${order.id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Ordine_${order.order_number}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setErr("Errore download PDF: " + (e.response?.data?.detail || e.message));
    }
  }

  const getStatusStyle = (status) => {
    const map = {
      "bozza": { bg: "#f1f5f9", color: "#64748b" },
      "inviato": { bg: "#dbeafe", color: "#1535a8" },
      "confermato": { bg: "#fef3c7", color: "#92400e" },
      "consegnato": { bg: "#dcfce7", color: "#166534" },
      "annullato": { bg: "#fef2f2", color: "#dc2626" }
    };
    return map[status] || map["bozza"];
  };

  return (
    <PageLayout title="Ordini Fornitori" subtitle="Genera ordini ai fornitori partendo dal carrello comparatore prezzi">
    <div style={{...styles.container, padding: 0}} data-testid="ordini-fornitori-page">
      {/* Header */}
      <div style={styles.card}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 'bold', color: '#1e293b' }}>
          📦 Ordini Fornitori
        </h1>
        <p style={styles.subtitle}>
          Genera ordini ai fornitori partendo dal carrello comparatore prezzi.
        </p>

        {err && <div style={styles.error}>{err}</div>}
        {success && <div style={styles.success}>{success}</div>}
      </div>

      {/* Carrello per Fornitore */}
      {cart.by_supplier.length > 0 && (
        <div style={styles.cardOrange}>
          <h2 style={styles.header}>🛒 Carrello - Prodotti da Ordinare</h2>
          <p style={styles.subtitle}>
            {cart.total_items} prodotti | Totale: <strong>€ {cart.total_amount.toFixed(2)}</strong>
          </p>

          {cart.by_supplier.map((supplier, i) => (
            <div key={i} style={styles.supplierCard}>
              <div style={{ ...styles.row, justifyContent: 'space-between', marginBottom: 12 }}>
                <div>
                  <strong style={{ fontSize: 16, color: '#1e293b' }}>{supplier.supplier}</strong>
                  <span style={{ marginLeft: 10, color: '#64748b', fontSize: 13 }}>
                    {supplier.items.length} prodotti
                  </span>
                </div>
                <div style={styles.row}>
                  <span style={{ fontSize: 20, fontWeight: 'bold', color: '#ea580c' }}>
                    € {supplier.subtotal.toFixed(2)}
                  </span>
                  <button 
                    style={styles.btnSuccess}
                    onClick={() => handleGenerateOrder(supplier)}
                    disabled={generatingOrder === supplier.supplier}
                    data-testid={`genera-ordine-${i}`}
                  >
                    {generatingOrder === supplier.supplier ? "⏳ Generazione..." : "📝 Genera Ordine"}
                  </button>
                </div>
              </div>

              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Prodotto</th>
                    <th style={styles.th}>Quantità</th>
                    <th style={{ ...styles.th, textAlign: 'right' }}>Prezzo Unit.</th>
                    <th style={{ ...styles.th, textAlign: 'right' }}>Totale</th>
                  </tr>
                </thead>
                <tbody>
                  {supplier.items.map((item, j) => (
                    <tr key={j}>
                      <td style={styles.td}>
                        <strong>{item.normalized_name || item.original_description}</strong>
                        {item.normalized_name && item.original_description !== item.normalized_name && (
                          <div style={{ fontSize: 12, color: '#94a3b8' }}>{item.original_description}</div>
                        )}
                      </td>
                      <td style={styles.td}>{item.quantity || 1} {item.unit || "PZ"}</td>
                      <td style={{ ...styles.td, textAlign: 'right' }}>€ {item.price?.toFixed(2)}</td>
                      <td style={{ ...styles.td, textAlign: 'right', fontWeight: 'bold' }}>
                        € {((item.price || 0) * (item.quantity || 1)).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {/* Lista Ordini */}
      <div style={styles.card}>
        <h2 style={styles.header}>📋 Storico Ordini ({orders.length})</h2>

        {loading ? (
          <div style={styles.emptyState}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
            <p>Caricamento...</p>
          </div>
        ) : orders.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
            <p style={{ margin: 0 }}>Nessun ordine generato</p>
            <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>
              Aggiungi prodotti al carrello dalla pagina &quot;Ricerca Prodotti&quot;
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>N° Ordine</th>
                  <th style={styles.th}>Data</th>
                  <th style={styles.th}>Fornitore</th>
                  <th style={styles.th}>Prodotti</th>
                  <th style={{ ...styles.th, textAlign: 'right' }}>Totale</th>
                  <th style={styles.th}>Stato</th>
                  <th style={styles.th}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order, i) => {
                  const statusStyle = getStatusStyle(order.status);
                  return (
                    <tr key={order.id || i}>
                      <td style={{ ...styles.td, fontWeight: 'bold' }}>#{order.order_number}</td>
                      <td style={styles.td}>{formatDateIT(order.created_at)}</td>
                      <td style={styles.td}><strong>{order.supplier_name}</strong></td>
                      <td style={styles.td}>{order.items?.length || 0} prodotti</td>
                      <td style={{ ...styles.td, textAlign: 'right', fontWeight: 'bold' }}>
                        € {(order.total || order.subtotal || 0).toFixed(2)}
                      </td>
                      <td style={styles.td}>
                        <select
                          value={order.status}
                          onChange={(e) => handleUpdateStatus(order.id, e.target.value)}
                          style={{ 
                            background: statusStyle.bg, 
                            color: statusStyle.color,
                            border: 'none',
                            padding: '6px 12px',
                            borderRadius: 20,
                            fontWeight: '600',
                            cursor: 'pointer',
                            fontSize: 12
                          }}
                        >
                          <option value="bozza">Bozza</option>
                          <option value="inviato">Inviato</option>
                          <option value="confermato">Confermato</option>
                          <option value="consegnato">Consegnato</option>
                          <option value="annullato">Annullato</option>
                        </select>
                      </td>
                      <td style={styles.td}>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button onClick={() => handleDownloadPDF(order)} style={styles.btnSecondary} title="Scarica PDF" data-testid={`download-pdf-${order.id}`}>📄</button>
                          <button onClick={() => handlePrintOrder(order)} style={styles.btnSecondary} title="Stampa">🖨️</button>
                          <button onClick={() => handleSendEmail(order)} disabled={sendingEmail === order.id} style={styles.btnSecondary} title="Invia Email">
                            {sendingEmail === order.id ? "..." : "📧"}
                          </button>
                          <button onClick={() => setSelectedOrder(order)} style={styles.btnSecondary} title="Dettaglio">👁️</button>
                          <button onClick={() => handleDeleteOrder(order.id)} style={{ ...styles.btnSecondary, background: '#fef2f2', color: '#dc2626' }} title="Elimina">🗑️</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Riepilogo */}
      <div style={styles.cardGreen}>
        <h2 style={styles.header}>📊 Riepilogo</h2>
        <div style={styles.grid4}>
          <div style={styles.statCard}>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#166534' }}>{orders.length}</div>
            <div style={{ fontSize: 13, color: '#64748b' }}>Ordini Totali</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#64748b' }}>{orders.filter(o => o.status === "bozza").length}</div>
            <div style={{ fontSize: 13, color: '#64748b' }}>In Bozza</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#1535a8' }}>{orders.filter(o => o.status === "inviato").length}</div>
            <div style={{ fontSize: 13, color: '#64748b' }}>Inviati</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#059669' }}>{orders.filter(o => o.status === "consegnato").length}</div>
            <div style={{ fontSize: 13, color: '#64748b' }}>Consegnati</div>
          </div>
        </div>
      </div>

      {/* Modal Dettaglio Ordine */}
      {selectedOrder && (
        <div style={styles.modal} onClick={() => setSelectedOrder(null)}>
          <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <h2 style={{ margin: 0 }}>Ordine #{selectedOrder.order_number}</h2>
              <div style={{ fontSize: 13, opacity: 0.8, marginTop: 5 }}>
                {selectedOrder.supplier_name} | {formatDateIT(selectedOrder.created_at)}
              </div>
            </div>
            
            <div style={{ padding: 20 }}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Prodotto</th>
                    <th style={styles.th}>Qtà</th>
                    <th style={{ ...styles.th, textAlign: 'right' }}>Prezzo</th>
                    <th style={{ ...styles.th, textAlign: 'right' }}>Totale</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedOrder.items || []).map((item, i) => (
                    <tr key={i}>
                      <td style={styles.td}>{item.product_name || item.description}</td>
                      <td style={{ ...styles.td, textAlign: 'center' }}>{item.quantity || 1} {item.unit || "PZ"}</td>
                      <td style={{ ...styles.td, textAlign: 'right' }}>€ {(item.unit_price || 0).toFixed(2)}</td>
                      <td style={{ ...styles.td, textAlign: 'right', fontWeight: 'bold' }}>€ {((item.unit_price || 0) * (item.quantity || 1)).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              
              <div style={{ marginTop: 20, textAlign: 'right', borderTop: '2px solid #1535a8', paddingTop: 15 }}>
                <div>Imponibile: € {(selectedOrder.subtotal || 0).toFixed(2)}</div>
                <div>IVA (22%): € {((selectedOrder.subtotal || 0) * 0.22).toFixed(2)}</div>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#1535a8', marginTop: 10 }}>
                  TOTALE: € {((selectedOrder.subtotal || 0) * 1.22).toFixed(2)}
                </div>
              </div>
            </div>
            
            <div style={{ padding: 15, borderTop: '1px solid #eee', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => handleDownloadPDF(selectedOrder)} style={{ ...styles.btnSecondary, background: '#dbeafe', color: '#1535a8' }} data-testid="modal-download-pdf">📄 Scarica PDF</button>
              <button onClick={() => handlePrintOrder(selectedOrder)} style={{ ...styles.btnSecondary, background: '#f3e8ff', color: '#7c3aed' }}>🖨️ Stampa</button>
              <button onClick={() => handleSendEmail(selectedOrder)} disabled={sendingEmail === selectedOrder.id} style={{ ...styles.btnSecondary, background: '#dcfce7', color: '#166534' }} data-testid="modal-send-email">
                {sendingEmail === selectedOrder.id ? "Invio..." : "📧 Invia Email"}
              </button>
              <button onClick={() => setSelectedOrder(null)} style={styles.btnSecondary}>Chiudi</button>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}
