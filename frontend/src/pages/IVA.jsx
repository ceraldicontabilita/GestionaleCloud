import React, { useState, useEffect } from "react";
import api from "../api";
import { formatEuro, formatDateIT } from '../lib/utils';
import { useAnnoGlobale } from "../contexts/AnnoContext";
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Receipt, TrendingUp, TrendingDown, FileText, Calendar, Download } from 'lucide-react';

export default function IVA() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [todayData, setTodayData] = useState(null);
  const [annualData, setAnnualData] = useState(null);
  const [monthlyData, setMonthlyData] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [viewMode, setViewMode] = useState("annual");
  const [err, setErr] = useState("");

  const mesiItaliani = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

  useEffect(() => { loadData(); }, [selectedYear, selectedMonth]);

  async function loadData() {
    setLoading(true);
    setErr("");
    try {
      const [todayRes, annualRes, monthlyRes] = await Promise.all([
        api.get("/api/iva/today"),
        api.get(`/api/iva/annual/${selectedYear}`),
        api.get(`/api/iva/monthly/${selectedYear}/${selectedMonth}`)
      ]);
      setTodayData(todayRes.data);
      setAnnualData(annualRes.data);
      setMonthlyData(monthlyRes.data);
    } catch (e) {
      console.error("Error loading IVA data:", e);
      setErr("Errore caricamento dati IVA");
    } finally {
      setLoading(false);
    }
  }

  const getSaldoColor = (saldo) => saldo > 0 ? "#dc2626" : saldo < 0 ? "#16a34a" : "#6080a0";
  const getSaldoBadge = (stato) => {
    if (stato === "Da versare") return { bg: "#fee2e2", color: "#dc2626" };
    if (stato === "A credito") return { bg: "#dcfce7", color: "#16a34a" };
    return { bg: "#f3f4f6", color: "#6080a0" };
  };

  const viewModes = [
    { id: 'annual', label: 'Annuale' },
    { id: 'quarterly', label: 'Trimestrale' },
    { id: 'monthly', label: 'Mensile' },
    { id: 'today', label: 'Oggi' }
  ];

  const KPICard = ({ label, value, subtext, color, bgColor, icon: Icon }) => (
    <div style={{ background: bgColor, borderRadius: 12, padding: 20, textAlign: 'center' }}>
      {Icon && <Icon size={24} color={color} style={{ marginBottom: 8 }} />}
      <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      {subtext && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>{subtext}</div>}
    </div>
  );

  return (
    <PageLayout
      title="Calcolo IVA"
      icon={<Receipt size={28} />}
      subtitle="Riepilogo IVA: debito da corrispettivi, credito da fatture passive"
      actions={
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => window.open(`${api.defaults.baseURL}/api/iva/export/pdf/trimestrale/${selectedYear}/${Math.ceil(selectedMonth / 3)}`, '_blank')}
            style={{ padding: '8px 14px', background: '#16a34a', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Download size={14} /> PDF Q{Math.ceil(selectedMonth / 3)}
          </button>
          <button
            onClick={() => window.open(`${api.defaults.baseURL}/api/iva/export/pdf/annuale/${selectedYear}`, '_blank')}
            style={{ padding: '8px 14px', background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Download size={14} /> PDF Annuale
          </button>
        </div>
      }
    >
      {err && (
        <div style={{ padding: 16, background: "#fee2e2", border: "1px solid #fecaca", borderRadius: 8, color: "#dc2626", marginBottom: 20 }}>{err}</div>
      )}

      {/* Controlli */}
      <PageSection title="Filtri" icon={<Calendar size={16} />}>
        <div style={{ display: "flex", alignItems: "center", gap: 15, flexWrap: 'wrap' }}>
          <div style={{ background: '#dbeafe', padding: '8px 16px', borderRadius: 8, color: '#1535a8', fontWeight: 600 }}>
            📅 Anno: {selectedYear}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ fontSize: 13, color: '#6080a0' }}>Mese:</label>
            <select value={selectedMonth} onChange={(e) => setSelectedMonth(parseInt(e.target.value))}
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 14 }}>
              {mesiItaliani.slice(1).map((m, i) => (<option key={i+1} value={i+1}>{m}</option>))}
            </select>
          </div>
          <div style={{ marginLeft: "auto", display: 'flex', gap: 4, background: '#f1f5f9', padding: 4, borderRadius: 10 }}>
            {viewModes.map(v => (
              <button key={v.id} onClick={() => setViewMode(v.id)}
                style={{
                  padding: '8px 14px', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13,
                  background: viewMode === v.id ? '#1e293b' : 'transparent',
                  color: viewMode === v.id ? 'white' : '#64748b'
                }}>{v.label}</button>
            ))}
          </div>
        </div>
      </PageSection>

      {loading ? (
        <PageLoading message="Caricamento dati IVA..." />
      ) : (
        <>
          {/* KPI Cards */}
          {annualData && (
            <PageGrid cols={3} gap={16} style={{ marginTop: 20 }}>
              <div style={{ background: "#e0f2fe", borderRadius: 12, padding: 20, textAlign: 'center' }}>
                <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 6 }}>Saldo IVA {selectedYear}</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: getSaldoColor(annualData.totali?.saldo) }}>{formatEuro(annualData.totali?.saldo)}</div>
                <span style={{ ...getSaldoBadge(annualData.totali?.stato), padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, display: 'inline-block', marginTop: 8 }}>{annualData.totali?.stato}</span>
              </div>
              <KPICard label="IVA a Debito (Corrispettivi)" value={formatEuro(annualData.totali?.iva_debito)} subtext={`${annualData.totali?.corrispettivi_count || 0} corrispettivi`} color="#ea580c" bgColor="#fff7ed" icon={TrendingUp} />
              <KPICard label="IVA a Credito (Fatture)" value={formatEuro(annualData.totali?.iva_credito)} subtext={`${annualData.totali?.fatture_count || 0} fatture`} color="#16a34a" bgColor="#dcfce7" icon={TrendingDown} />
            </PageGrid>
          )}

          {/* Vista Annuale */}
          {viewMode === "annual" && annualData && (
            <PageSection title={`Riepilogo IVA Annuale ${selectedYear}`} icon={<FileText size={16} />} style={{ marginTop: 20 }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid #dce8f4", background: '#f2f6fd' }}>
                      <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600 }}>Mese</th>
                      <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>IVA Debito</th>
                      <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>IVA Credito</th>
                      <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>Saldo</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600 }}>Stato</th>
                    </tr>
                  </thead>
                  <tbody>
                    {annualData.mesi?.map((m, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #f3f4f6', background: idx % 2 === 0 ? 'white' : '#f2f6fd' }}>
                        <td style={{ padding: '12px 16px', fontWeight: 500 }}>{mesiItaliani[m.mese]}</td>
                        <td style={{ padding: '12px 16px', textAlign: 'right', color: '#ea580c' }}>{formatEuro(m.iva_debito)}</td>
                        <td style={{ padding: '12px 16px', textAlign: 'right', color: '#16a34a' }}>{formatEuro(m.iva_credito)}</td>
                        <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 700, color: getSaldoColor(m.saldo) }}>{formatEuro(m.saldo)}</td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          <span style={{ ...getSaldoBadge(m.stato), padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{m.stato}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ borderTop: "2px solid #1535a8", background: '#f0f9ff', fontWeight: 700 }}>
                      <td style={{ padding: '12px 16px' }}>TOTALE ANNUO</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', color: '#ea580c' }}>{formatEuro(annualData.totali?.iva_debito)}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', color: '#16a34a' }}>{formatEuro(annualData.totali?.iva_credito)}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', color: getSaldoColor(annualData.totali?.saldo) }}>{formatEuro(annualData.totali?.saldo)}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}><span style={{ ...getSaldoBadge(annualData.totali?.stato), padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{annualData.totali?.stato}</span></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </PageSection>
          )}

          {/* Vista Trimestrale */}
          {viewMode === "quarterly" && annualData && (
            <PageSection title={`Riepilogo IVA Trimestrale ${selectedYear}`} style={{ marginTop: 20 }}>
              <PageGrid cols={4} gap={16}>
                {[1, 2, 3, 4].map(q => {
                  const mesiQ = annualData.mesi?.filter(m => Math.ceil(m.mese / 3) === q) || [];
                  const totDebito = mesiQ.reduce((s, m) => s + (m.iva_debito || 0), 0);
                  const totCredito = mesiQ.reduce((s, m) => s + (m.iva_credito || 0), 0);
                  const saldo = totDebito - totCredito;
                  const stato = saldo > 0 ? "Da versare" : saldo < 0 ? "A credito" : "Neutro";
                  return (
                    <div key={q} style={{ background: '#f2f6fd', borderRadius: 12, padding: 20, border: '1px solid #dce8f4' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Q{q}</h3>
                        <span style={{ ...getSaldoBadge(stato), padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{stato}</span>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                        <div><div style={{ fontSize: 11, color: '#6080a0' }}>Debito</div><div style={{ fontSize: 16, fontWeight: 700, color: '#ea580c' }}>{formatEuro(totDebito)}</div></div>
                        <div><div style={{ fontSize: 11, color: '#6080a0' }}>Credito</div><div style={{ fontSize: 16, fontWeight: 700, color: '#16a34a' }}>{formatEuro(totCredito)}</div></div>
                      </div>
                      <div style={{ borderTop: '1px solid #dce8f4', paddingTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>Saldo</span>
                        <span style={{ fontSize: 18, fontWeight: 700, color: getSaldoColor(saldo) }}>{formatEuro(saldo)}</span>
                      </div>
                    </div>
                  );
                })}
              </PageGrid>
            </PageSection>
          )}

          {/* Vista Mensile */}
          {viewMode === "monthly" && monthlyData && (
            <PageSection title={`Dettaglio IVA ${mesiItaliani[selectedMonth]} ${selectedYear}`} style={{ marginTop: 20 }}>
              <PageGrid cols={3} gap={16}>
                <KPICard label="IVA Debito" value={formatEuro(monthlyData.totali?.iva_debito)} subtext={`${monthlyData.totali?.corrispettivi_count || 0} corr.`} color="#ea580c" bgColor="#fff7ed" />
                <KPICard label="IVA Credito" value={formatEuro(monthlyData.totali?.iva_credito)} subtext={`${monthlyData.totali?.fatture_count || 0} fatt.`} color="#16a34a" bgColor="#dcfce7" />
                <div style={{ background: '#e0f2fe', borderRadius: 12, padding: 20, textAlign: 'center' }}>
                  <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 6 }}>Saldo</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: getSaldoColor(monthlyData.totali?.saldo) }}>{formatEuro(monthlyData.totali?.saldo)}</div>
                  <span style={{ ...getSaldoBadge(monthlyData.totali?.stato), padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600 }}>{monthlyData.totali?.stato}</span>
                </div>
              </PageGrid>
              {monthlyData.giorni?.filter(g => g.iva_debito > 0 || g.iva_credito > 0).length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#374151' }}>Dettaglio Giornaliero</h4>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead><tr style={{ borderBottom: "2px solid #dce8f4", background: '#f2f6fd' }}><th style={{ padding: 10, textAlign: 'left' }}>Giorno</th><th style={{ padding: 10, textAlign: 'right' }}>Debito</th><th style={{ padding: 10, textAlign: 'right' }}>Credito</th><th style={{ padding: 10, textAlign: 'right' }}>Saldo</th></tr></thead>
                    <tbody>
                      {monthlyData.giorni.filter(g => g.iva_debito > 0 || g.iva_credito > 0).map((g, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #f3f4f6' }}>
                          <td style={{ padding: 10 }}>{g.giorno}/{selectedMonth}/{selectedYear}</td>
                          <td style={{ padding: 10, textAlign: 'right', color: '#ea580c' }}>{formatEuro(g.iva_debito)}</td>
                          <td style={{ padding: 10, textAlign: 'right', color: '#16a34a' }}>{formatEuro(g.iva_credito)}</td>
                          <td style={{ padding: 10, textAlign: 'right', fontWeight: 500, color: getSaldoColor(g.saldo) }}>{formatEuro(g.saldo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </PageSection>
          )}

          {/* Vista Oggi */}
          {viewMode === "today" && todayData && (
            <PageSection title={`IVA Oggi - ${todayData.data || formatDateIT(new Date())}`} style={{ marginTop: 20 }}>
              <PageGrid cols={3} gap={16}>
                <KPICard label="IVA Debito Oggi" value={formatEuro(todayData.iva_debito)} color="#ea580c" bgColor="#fff7ed" icon={TrendingUp} />
                <KPICard label="IVA Credito Oggi" value={formatEuro(todayData.iva_credito)} color="#16a34a" bgColor="#dcfce7" icon={TrendingDown} />
                <KPICard label="Saldo Oggi" value={formatEuro(todayData.saldo)} color={getSaldoColor(todayData.saldo)} bgColor="#e0f2fe" />
              </PageGrid>
            </PageSection>
          )}
        </>
      )}

      {/* Info */}
      <PageSection title="Come funziona il calcolo IVA" icon="ℹ️" style={{ marginTop: 20 }}>
        <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 2, color: '#475569', fontSize: 13 }}>
          <li><strong>IVA Debito</strong>: calcolata dai corrispettivi giornalieri (vendite)</li>
          <li><strong>IVA Credito</strong>: estratta dalle fatture passive (acquisti)</li>
          <li><strong>Saldo positivo</strong> = IVA da versare all'erario</li>
          <li><strong>Saldo negativo</strong> = IVA a credito (compensabile)</li>
        </ul>
      </PageSection>
    </PageLayout>
  );
}
