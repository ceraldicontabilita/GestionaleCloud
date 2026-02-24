import React, { useState, useEffect, useCallback } from 'react';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription } from '../components/ui/alert';
import { PageLayout } from '../components/PageLayout';
import { 
  FileText, RefreshCw, Search, CheckCircle2, AlertCircle, 
  Upload, Link2, Download, Eye, Calendar
} from 'lucide-react';
import { toast } from '../components/ui/sonner';
import api from '../api';

export default function GestionePagoPA() {
  const [ricevute, setRicevute] = useState([]);
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [loading, setLoading] = useState(false);
  const [autoAssociaLoading, setAutoAssociaLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [filtro, setFiltro] = useState('');
  const [statoFiltro, setStatoFiltro] = useState('tutti');

  const fetchStats = useCallback(async () => {
    try {
      const response = await api.get('/api/pagopa/stats');
      setStats(response.data);
    } catch (error) {
      console.error('Errore fetch stats:', error);
    }
  }, []);

  const fetchRicevute = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/pagopa/ricevute');
      setRicevute(response.data || []);
    } catch (error) {
      console.error('Errore fetch ricevute:', error);
      toast.error('Errore nel caricamento ricevute');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMovimentiBanca = useCallback(async () => {
    try {
      const response = await api.get('/api/bank/movements?tipo=pagopa&limit=100');
      setMovimentiBanca(response.data || []);
    } catch (error) {
      console.error('Errore fetch movimenti:', error);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    fetchRicevute();
    fetchMovimentiBanca();
  }, [fetchStats, fetchRicevute, fetchMovimentiBanca]);

  const handleAutoAssocia = async () => {
    setAutoAssociaLoading(true);
    try {
      const response = await api.post('/api/pagopa/auto-associa');
      toast.success(`Associati ${response.data?.associazioni_effettuate || 0} ricevute`);
      fetchStats();
      fetchRicevute();
    } catch (error) {
      console.error('Errore auto-associa:', error);
      toast.error('Errore nell\'associazione automatica');
    } finally {
      setAutoAssociaLoading(false);
    }
  };

  const ricevuteFiltrate = ricevute.filter(r => {
    if (filtro) {
      const search = filtro.toLowerCase();
      if (!r.codice_cbill?.toLowerCase().includes(search) &&
          !r.beneficiario?.toLowerCase().includes(search)) {
        return false;
      }
    }
    if (statoFiltro === 'associati' && !r.movimento_banca_id) return false;
    if (statoFiltro === 'non_associati' && r.movimento_banca_id) return false;
    return true;
  });

  return (
    <PageLayout title="Gestione PagoPA" subtitle="Ricevute e riconciliazione pagamenti PagoPA">
    <div style={{ maxWidth: 1400, margin: '0 auto' }} data-testid="gestione-pagopa">
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: 20,
        padding: '15px 20px',
        background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
        borderRadius: 12,
        color: 'white',
        flexWrap: 'wrap',
        gap: 10
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold' }}>💳 Gestione PagoPA</h1>
          <p style={{ margin: '4px 0 0 0', fontSize: 13, opacity: 0.9 }}>
            Associa ricevute PagoPA ai movimenti bancari
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button 
            onClick={() => { fetchStats(); fetchRicevute(); }}
            disabled={loading}
            style={{ 
              padding: '10px 20px',
              background: 'rgba(255,255,255,0.95)',
              color: '#1535a8',
              border: 'none',
              borderRadius: 8,
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              opacity: loading ? 0.6 : 1
            }}
            data-testid="refresh-pagopa-btn"
          >
            🔄 Aggiorna
          </button>
          <button 
            onClick={handleAutoAssocia}
            disabled={autoAssociaLoading}
            style={{ 
              padding: '10px 20px',
              background: '#15803d',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              cursor: autoAssociaLoading ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              opacity: autoAssociaLoading ? 0.6 : 1
            }}
            data-testid="auto-associa-pagopa-btn"
          >
            🔗 Auto-Associa
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div style={{ 
          background: 'white', 
          borderRadius: 12, 
          padding: 16, 
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)', 
          marginBottom: 20 
        }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <div style={{ 
              background: 'white', 
              borderRadius: 8, 
              padding: '10px 12px', 
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)', 
              borderLeft: '3px solid #1535a8' 
            }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>📄 Ricevute Totali</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#1535a8' }} data-testid="stats-totali">{stats.totale_ricevute || 0}</div>
            </div>
            <div style={{ 
              background: 'white', 
              borderRadius: 8, 
              padding: '10px 12px', 
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)', 
              borderLeft: '3px solid #22c55e' 
            }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>✅ Associate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#22c55e' }} data-testid="stats-associate">{stats.associate || 0}</div>
            </div>
            <div style={{ 
              background: 'white', 
              borderRadius: 8, 
              padding: '10px 12px', 
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)', 
              borderLeft: '3px solid #f97316' 
            }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>⏳ Da Associare</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#f97316' }} data-testid="stats-da-associare">{stats.da_associare || 0}</div>
            </div>
            <div style={{ 
              background: '#1535a8', 
              borderRadius: 8, 
              padding: '10px 12px', 
              color: 'white'
            }}>
              <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 4 }}>💰 Importo Totale</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }} data-testid="stats-importo">
                {formatEuro((stats.importo_totale || 0))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Info Card */}
      <div style={{ 
        padding: 12, 
        background: '#eff6ff', 
        borderRadius: 8, 
        borderLeft: '4px solid #1535a8',
        fontSize: 13,
        color: '#1535a8',
        marginBottom: 20
      }}>
        <strong>ℹ️ Come funziona:</strong> Il sistema cerca nei movimenti bancari il codice CBILL (bollettino) 
        presente nella ricevuta PagoPA e li associa automaticamente. Puoi anche associare manualmente 
        cliccando su una ricevuta non associata.
      </div>
      {/* Categorie Pagamenti CBILL */}
      <div style={{ 
        background: 'white', 
        borderRadius: 12, 
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        overflow: 'hidden',
        marginBottom: 20
      }}>
        <div style={{ 
          padding: '16px 20px', 
          background: '#f8fafc', 
          borderBottom: '1px solid #e5e7eb'
        }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
            📋 Tipologie Pagamenti CBILL
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: 13, color: '#6b7280' }}>
            Pagamenti identificabili tramite codice CBILL per rateizzazioni e tributi
          </p>
        </div>
        <div style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {/* INPS */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #bfdbfe', background: '#eff6ff' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>🏛️</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#1535a8' }}>Rateizzi INPS</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#1535a8' }}>Dilazioni contributive</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#1535a8', margin: 0, paddingLeft: 16 }}>
                <li>Rateizzazione contributi</li>
                <li>Avvisi di addebito</li>
                <li>Sanzioni INPS</li>
              </ul>
            </div>

            {/* Agenzia Entrate */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #bbf7d0', background: '#f0fdf4' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>📊</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#166534' }}>Agenzia delle Entrate</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#22c55e' }}>Imposte e tributi</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#166534', margin: 0, paddingLeft: 16 }}>
                <li>Rateizzazione imposte</li>
                <li>Avvisi bonari</li>
                <li>Comunicazioni di irregolarità</li>
              </ul>
            </div>

            {/* AdER */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #fecaca', background: '#fef2f2' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>⚖️</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#991b1b' }}>Agenzia Riscossione</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#ef4444' }}>AdER - Cartelle esattoriali</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#991b1b', margin: 0, paddingLeft: 16 }}>
                <li>Rottamazione quater</li>
                <li>Rateizzazione cartelle</li>
                <li>Definizione agevolata</li>
              </ul>
            </div>

            {/* TARI */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #fde68a', background: '#fefce8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>🗑️</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#92400e' }}>TARI</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#d97706' }}>Tassa rifiuti</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#92400e', margin: 0, paddingLeft: 16 }}>
                <li>Rate TARI annuali</li>
                <li>Conguagli</li>
                <li>Accertamenti</li>
              </ul>
            </div>

            {/* COSAP / Tosap */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #e9d5ff', background: '#faf5ff' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>🏪</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#7c3aed' }}>COSAP / TOSAP</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#a855f7' }}>Occupazione suolo pubblico</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#7c3aed', margin: 0, paddingLeft: 16 }}>
                <li>Canone occupazione</li>
                <li>Rinnovi annuali</li>
                <li>Plateatici</li>
              </ul>
            </div>

            {/* Altri tributi */}
            <div style={{ padding: 16, borderRadius: 8, border: '2px solid #e5e7eb', background: '#f9fafb' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 24 }}>📄</span>
                <div>
                  <h4 style={{ margin: 0, fontWeight: 600, color: '#374151' }}>Altri Tributi</h4>
                  <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Pagamenti vari</p>
                </div>
              </div>
              <ul style={{ fontSize: 13, color: '#374151', margin: 0, paddingLeft: 16 }}>
                <li>IMU / TASI</li>
                <li>Bollo auto</li>
                <li>Multe e sanzioni</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Filtri */}
      <div style={{ 
        background: 'white', 
        borderRadius: 12, 
        padding: 16, 
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)', 
        marginBottom: 20 
      }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ flex: 1, minWidth: 250 }}>
            <input
              type="text"
              placeholder="🔍 Cerca per codice CBILL o beneficiario..."
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              style={{ 
                width: '100%', 
                padding: '10px 12px', 
                border: '1px solid #e5e7eb', 
                borderRadius: 8,
                fontSize: 14
              }}
              data-testid="search-pagopa-input"
            />
          </div>
          
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setStatoFiltro('tutti')}
              style={{
                padding: '8px 16px',
                background: statoFiltro === 'tutti' ? '#1535a8' : 'white',
                color: statoFiltro === 'tutti' ? 'white' : '#6b7280',
                border: '1px solid #e5e7eb',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: 13
              }}
            >
              Tutti
            </button>
            <button
              onClick={() => setStatoFiltro('associati')}
              style={{
                padding: '8px 16px',
                background: statoFiltro === 'associati' ? '#22c55e' : 'white',
                color: statoFiltro === 'associati' ? 'white' : '#6b7280',
                border: '1px solid #e5e7eb',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: 13
              }}
            >
              ✅ Associati
            </button>
            <button
              onClick={() => setStatoFiltro('non_associati')}
              style={{
                padding: '8px 16px',
                background: statoFiltro === 'non_associati' ? '#f97316' : 'white',
                color: statoFiltro === 'non_associati' ? 'white' : '#6b7280',
                border: '1px solid #e5e7eb',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: 13
              }}
            >
              ⏳ Da Associare
            </button>
          </div>
        </div>
      </div>

      {/* Lista Ricevute */}
      <div style={{ 
        background: 'white', 
        borderRadius: 12, 
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        overflow: 'hidden'
      }}>
        <div style={{ 
          padding: '16px 20px', 
          background: '#f8fafc', 
          borderBottom: '1px solid #e5e7eb'
        }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
            📄 Ricevute PagoPA
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: 13, color: '#6b7280' }}>
            {ricevuteFiltrate.length} ricevute {filtro && `(filtrate per "${filtro}")`}
          </p>
        </div>
        <div style={{ padding: 16 }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
              <RefreshCw style={{ width: 32, height: 32, animation: 'spin 1s linear infinite', color: '#9ca3af' }} />
            </div>
          ) : ricevuteFiltrate.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af' }}>
              <FileText style={{ width: 48, height: 48, margin: '0 auto 16px', opacity: 0.5 }} />
              <p style={{ margin: 0 }}>Nessuna ricevuta PagoPA trovata</p>
              <p style={{ fontSize: 13, marginTop: 8 }}>
                Carica le ricevute PDF dalla sezione Documenti o importa da email
              </p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                    <th style={{ textAlign: 'left', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Data</th>
                    <th style={{ textAlign: 'left', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Codice CBILL</th>
                    <th style={{ textAlign: 'left', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Beneficiario</th>
                    <th style={{ textAlign: 'right', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Importo</th>
                    <th style={{ textAlign: 'center', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Stato</th>
                    <th style={{ textAlign: 'center', padding: '12px 16px', fontWeight: 500, color: '#6b7280', fontSize: 13 }}>Azioni</th>
                  </tr>
                </thead>
                <tbody>
                  {ricevuteFiltrate.map((ricevuta, idx) => (
                    <tr key={ricevuta._id || idx} style={{ borderBottom: '1px solid #e5e7eb' }}>
                      <td style={{ padding: '12px 16px' }}>
                        📅 {ricevuta.data_pagamento || '-'}
                      </td>
                      <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: 13 }}>
                        {ricevuta.codice_cbill || '-'}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {ricevuta.beneficiario || '-'}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 500 }}>
                        {formatEuro((ricevuta.importo || 0))}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        {ricevuta.movimento_banca_id ? (
                          <span style={{ padding: '4px 8px', background: '#dcfce7', color: '#166534', borderRadius: 4, fontSize: 12, fontWeight: 600 }}>
                            ✅ Associata
                          </span>
                        ) : (
                          <span style={{ padding: '4px 8px', background: '#ffedd5', color: '#9a3412', borderRadius: 4, fontSize: 12, fontWeight: 600 }}>
                            ⏳ Da Associare
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
                          <button 
                            style={{ padding: '6px 10px', background: 'transparent', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer' }}
                            data-testid={`view-ricevuta-${idx}`}
                          >
                            👁️
                          </button>
                          {ricevuta.pdf_url && (
                            <a 
                              href={ricevuta.pdf_url} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              style={{ padding: '6px 10px', background: 'transparent', border: '1px solid #e5e7eb', borderRadius: 6, textDecoration: 'none' }}
                            >
                              📥
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
    </PageLayout>
  );
}
