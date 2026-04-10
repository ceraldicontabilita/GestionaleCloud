import React, { useState, useEffect } from "react";
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { Link } from 'react-router-dom';
import api from "../api";
import { formatDateIT, formatEuro } from '../lib/utils';
import { useAnnoGlobale } from "../contexts/AnnoContext";
import { PageLayout, PageSection, PageGrid, PageLoading, PageEmpty, PageError } from '../components/PageLayout';
import { Receipt, Banknote, CreditCard, Percent, RefreshCw, Upload, Eye, Trash2, X } from 'lucide-react';

/**
 * PAGINA CORRISPETTIVI
 * Mostra i corrispettivi dalla collection corrispettivi
 * I corrispettivi vengono importati tramite XML dal registratore telematico
 */
export default function Corrispettivi() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [corrispettivi, setCorrispettivi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // Deep link: item selezionato sincronizzato con hash (#selected=2026-04-08)
  const [hs, setHs] = useHashState({ selected: '' });
  const selectedItem = corrispettivi.find(c => c.data === hs.selected) || null;

  useEffect(() => {
    loadCorrispettivi();
  }, [selectedYear]);

  async function loadCorrispettivi() {
    try {
      setLoading(true);
      setErr("");
      const r = await api.get(`/api/corrispettivi?anno=${selectedYear}&limit=2500`);
      const data = r.data || [];
      const corrispettiviArray = Array.isArray(data) ? data : [];
      corrispettiviArray.sort((a, b) => (b.data || '').localeCompare(a.data || ''));
      setCorrispettivi(corrispettiviArray);
    } catch (e) {
      console.error("Error loading corrispettivi:", e);
      setErr("Errore caricamento: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id) {
    try {
      await api.delete(`/api/corrispettivi/${id}`);
      loadCorrispettivi();
    } catch (e) {
      setErr("Errore eliminazione: " + (e.response?.data?.detail || e.message));
    }
  }

  const totaleGiornaliero = corrispettivi.reduce((sum, c) => sum + (c.totale || 0), 0);
  const totaleCassa = corrispettivi.reduce((sum, c) => sum + (c.pagato_contanti || 0), 0);
  const totaleElettronico = corrispettivi.reduce((sum, c) => sum + (c.pagato_elettronico || 0), 0);
  const totaleIVA = corrispettivi.reduce((sum, c) => sum + (c.totale_iva || 0), 0);
  const totaleImponibile = corrispettivi.reduce((sum, c) => sum + (c.totale_imponibile || 0), 0);

  const KPICard = ({ icon: Icon, label, value, subtext, color, bgColor }) => (
    <div style={{
      background: bgColor || '#fff',
      borderRadius: 12,
      padding: 20,
      border: '1px solid #e2e8f0'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon size={18} color={color || '#64748b'} />
        <span style={{ fontSize: 13, color: '#64748b' }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || '#1e293b' }}>
        {value}
      </div>
      {subtext && (
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6 }}>{subtext}</div>
      )}
    </div>
  );

  return (
    <PageLayout
      title="Corrispettivi Elettronici"
      icon="🧾"
      subtitle={`Corrispettivi giornalieri dal registratore telematico - Anno ${selectedYear}`}
      actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <Link
            to="/import-documenti"
            style={{
              padding: '10px 16px',
              background: '#16a34a',
              color: 'white',
              fontWeight: 600,
              borderRadius: 8,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13
            }}
          >
            <Upload size={16} /> Importa
          </Link>
          <button
            onClick={loadCorrispettivi}
            disabled={loading}
            style={{
              padding: '10px 16px',
              background: '#f1f5f9',
              color: '#475569',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
            data-testid="corrispettivi-refresh-btn"
          >
            <RefreshCw size={16} /> Aggiorna
          </button>
        </div>
      }
    >
      {err && (
        <PageError message={err} onRetry={() => { setErr(''); loadCorrispettivi(); }} />
      )}

      {loading ? (
        <PageLoading message="Caricamento corrispettivi..." />
      ) : (
        <>
          {/* KPI Cards */}
          {corrispettivi.length > 0 && (
            <PageGrid cols={4} gap={16}>
              <KPICard
                icon={Receipt}
                label="Totale Corrispettivi"
                value={formatEuro(totaleGiornaliero)}
                color="#1e3a5f"
              />
              <KPICard
                icon={Banknote}
                label="Pagato Cassa"
                value={formatEuro(totaleCassa)}
                color="#16a34a"
                bgColor="#f0fdf4"
              />
              <KPICard
                icon={CreditCard}
                label="Pagato POS"
                value={formatEuro(totaleElettronico)}
                color="#7c3aed"
                bgColor="#f5f3ff"
              />
              <KPICard
                icon={Percent}
                label="IVA 10%"
                value={formatEuro(totaleIVA)}
                subtext={`Imponibile: ${formatEuro(totaleImponibile)}`}
                color="#ea580c"
                bgColor="#fff7ed"
              />
            </PageGrid>
          )}

          {/* Dettaglio selezionato */}
          {selectedItem && (
            <PageSection title={`Dettaglio Corrispettivo ${selectedItem.data}`} icon="📋" style={{ marginTop: 20 }}>
              <button
                onClick={() => setHs('selected', '')}
                style={{
                  position: 'absolute',
                  top: 16,
                  right: 16,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 4
                }}
              >
                <X size={20} color="#64748b" />
              </button>

              <PageGrid cols={3} gap={20}>
                <div>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: 13, color: '#64748b', fontWeight: 600 }}>Dati Generali</h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div>📅 Data: <strong>{selectedItem.data}</strong></div>
                    <div>🔢 Matricola RT: {selectedItem.matricola_rt || "-"}</div>
                    <div>🏢 P.IVA: {selectedItem.partita_iva || "-"}</div>
                    <div>📄 N° Documenti: {selectedItem.numero_documenti || "-"}</div>
                  </div>
                </div>
                <div>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: 13, color: '#64748b', fontWeight: 600 }}>Pagamenti</h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div style={{ color: '#16a34a' }}>💵 Cassa: {formatEuro(selectedItem.pagato_contanti)}</div>
                    <div style={{ color: '#7c3aed' }}>💳 Elettronico: {formatEuro(selectedItem.pagato_elettronico)}</div>
                    <div style={{ fontWeight: 700, marginTop: 8, fontSize: 15 }}>
                      Totale: {formatEuro(selectedItem.totale)}
                    </div>
                  </div>
                </div>
                <div>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: 13, color: '#64748b', fontWeight: 600 }}>IVA</h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div>Imponibile: {formatEuro(selectedItem.totale_imponibile)}</div>
                    <div>Imposta: {formatEuro(selectedItem.totale_iva)}</div>
                  </div>
                </div>
              </PageGrid>

              {selectedItem.riepilogo_iva && selectedItem.riepilogo_iva.length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: 13, color: '#64748b', fontWeight: 600 }}>
                    Riepilogo per Aliquota IVA
                  </h4>
                  <div style={{overflowX:'auto'}}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                        <th style={{ padding: 10, textAlign: 'left' }}>Aliquota</th>
                        <th style={{ padding: 10, textAlign: 'right' }}>Imponibile</th>
                        <th style={{ padding: 10, textAlign: 'right' }}>Imposta</th>
                        <th style={{ padding: 10, textAlign: 'right' }}>Totale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedItem.riepilogo_iva.map((r, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: 10 }}>{r.aliquota_iva}% {r.natura && `(${r.natura})`}</td>
                          <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(r.ammontare)}</td>
                          <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(r.imposta)}</td>
                          <td style={{ padding: 10, textAlign: 'right' }}>{formatEuro(r.importo_parziale)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </div>
              )}
            </PageSection>
          )}

          {/* Lista Corrispettivi */}
          <PageSection
            title={`Elenco Corrispettivi (${corrispettivi.length})`}
            icon="📋"
            style={{ marginTop: 20, padding: 0 }}
            actions={<CopyLinkButton />}
          >
            {corrispettivi.length === 0 ? (
              <div style={{ padding: 40 }}>
                <PageEmpty
                  icon="🧾"
                  message="Nessun corrispettivo registrato per questo anno"
                />
                <div style={{ textAlign: 'center', marginTop: 16 }}>
                  <Link to="/import-documenti" style={{ color: '#2563eb', fontSize: 14 }}>
                    Vai a Import Documenti per caricare i corrispettivi
                  </Link>
                </div>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }} data-testid="corrispettivi-table">
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: 600, fontSize: 12, color: '#64748b' }}>DATA</th>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: 600, fontSize: 12, color: '#64748b' }}>MATRICOLA RT</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 600, fontSize: 12, color: '#64748b' }}>💵 CASSA</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 600, fontSize: 12, color: '#64748b' }}>💳 POS</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 600, fontSize: 12, color: '#64748b' }}>TOTALE</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 600, fontSize: 12, color: '#64748b' }}>IVA</th>
                      <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: 600, fontSize: 12, color: '#64748b' }}>AZIONI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {corrispettivi.map((c, i) => (
                      <tr
                        key={c.id || i}
                        style={{
                          borderBottom: '1px solid #f1f5f9',
                          transition: 'background 0.15s'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '14px 16px', fontWeight: 600, fontSize: 14 }}>
                          {formatDateIT(c.data) || "-"}
                        </td>
                        <td style={{ padding: '14px 16px', fontSize: 13, color: '#64748b' }}>
                          {c.matricola_rt || "-"}
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', color: '#16a34a', fontWeight: 500 }}>
                          {formatEuro(c.pagato_contanti)}
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', color: '#7c3aed', fontWeight: 500 }}>
                          {formatEuro(c.pagato_elettronico)}
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700 }}>
                          {formatEuro(c.totale)}
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', color: '#ea580c', fontWeight: 500 }}>
                          {formatEuro(c.totale_iva)}
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                          <button
                            onClick={() => setHs('selected', c.data || '')}
                            style={{
                              padding: '6px 10px',
                              background: '#eff6ff',
                              color: '#2563eb',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              marginRight: 6
                            }}
                            title="Vedi dettaglio"
                          >
                            <Eye size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(c.id)}
                            style={{
                              padding: '6px 10px',
                              background: '#fef2f2',
                              color: '#dc2626',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer'
                            }}
                            title="Elimina"
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PageSection>
        </>
      )}
    </PageLayout>
  );
}

