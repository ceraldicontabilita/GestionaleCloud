import React, { useState, useEffect } from 'react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection, PageGrid, PageEmpty, PageLoading, PageError } from '../components/PageLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Users, Calendar, Clock, AlertCircle, CheckCircle, RefreshCw, Search, Edit, Trash2 } from 'lucide-react';
import api from '../api';

export default function SaldiFeriePermessi() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dipendenti, setDipendenti] = useState([]);
  const [saldi, setSaldi] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDip, setSelectedDip] = useState(null);
  const [dettaglio, setDettaglio] = useState(null);
  const [loadingDettaglio, setLoadingDettaglio] = useState(false);
  
  // Modale modifica saldi
  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState({ ferie: 0, rol: 0, exf: 0, per: 0 });
  const [saving, setSaving] = useState(false);
  
  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Carica dipendenti
      const dipRes = await api.get('/api/dipendenti');
      const employees = dipRes.data || [];
      setDipendenti(employees);
      
      // Carica saldi finali
      const saldiRes = await api.get(`/api/giustificativi/saldi-finali-tutti?anno=${selectedYear}`);
      setSaldi(saldiRes.data?.saldi || []);
    } catch (err) {
      console.error('Errore caricamento:', err);
      setError(err.message || 'Errore di connessione');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear]);
  
  const loadDettaglio = async (employeeId) => {
    setLoadingDettaglio(true);
    setSelectedDip(employeeId);
    try {
      const res = await api.get(`/api/giustificativi/riepilogo-progressivo/${employeeId}?anno=${selectedYear}`);
      setDettaglio(res.data);
    } catch (err) {
      console.error('Errore caricamento dettaglio:', err);
      setDettaglio(null);
    } finally {
      setLoadingDettaglio(false);
    }
  };
  
  const openEditModal = (dip, currentSaldi) => {
    setSelectedDip(dip.id);
    setEditData({
      ferie: currentSaldi?.FER || 0,
      rol: currentSaldi?.ROL || 0,
      exf: currentSaldi?.EXF || 0,
      per: currentSaldi?.PER || 0
    });
    setShowEditModal(true);
  };
  
  const saveSaldi = async () => {
    setSaving(true);
    try {
      await api.post('/api/giustificativi/salva-saldi-finali', {
        employee_id: selectedDip,
        anno: selectedYear,
        periodo: `${selectedYear}-${String(new Date().getMonth() + 1).padStart(2, '0')}`,
        saldi: {
          FER: parseFloat(editData.ferie) || 0,
          ROL: parseFloat(editData.rol) || 0,
          EXF: parseFloat(editData.exf) || 0,
          PER: parseFloat(editData.per) || 0
        },
        source: 'manual'
      });
      setShowEditModal(false);
      await loadData();
    } catch (err) {
      console.error('Errore salvataggio:', err);
      alert('Errore nel salvataggio: ' + (err.message || 'Riprova'));
    } finally {
      setSaving(false);
    }
  };
  
  // Unisci dipendenti con saldi
  const getDipendentiConSaldi = () => {
    const saldiMap = {};
    saldi.forEach(s => {
      saldiMap[s.employee_id] = s;
    });
    
    return dipendenti
      .filter(d => {
        if (!searchTerm) return true;
        const nome = (d.nome_completo || `${d.cognome} ${d.nome}`).toLowerCase();
        return nome.includes(searchTerm.toLowerCase());
      })
      .map(d => ({
        ...d,
        saldi: saldiMap[d.id]?.saldi || null,
        periodo: saldiMap[d.id]?.periodo || null,
        source: saldiMap[d.id]?.source || null
      }));
  };
  
  const formatOre = (ore) => {
    if (ore === null || ore === undefined) return '-';
    const giorni = Math.floor(ore / 8);
    const oreRes = ore % 8;
    if (giorni > 0 && oreRes > 0) {
      return `${ore}h (${giorni}gg ${oreRes}h)`;
    } else if (giorni > 0) {
      return `${ore}h (${giorni}gg)`;
    }
    return `${ore}h`;
  };

  const dipendentiConSaldi = getDipendentiConSaldi();

  return (
    <PageLayout
      title="Saldi Ferie e Permessi"
      subtitle={`Riepilogo giustificativi dipendenti - Anno ${selectedYear}`}
      icon={<Users size={24} />}
      actions={
        <Button onClick={loadData} disabled={loading} variant="outline">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} style={{ marginRight: 8 }} />
          Aggiorna
        </Button>
      }
    >
      {loading ? (
        <PageLoading message="Caricamento saldi..." />
      ) : error ? (
        <PageError message={error} onRetry={loadData} />
      ) : (
        <>
          {/* KPI */}
          <PageGrid cols={4} gap={16}>
            <Card>
              <CardContent style={{ padding: 16, textAlign: 'center' }}>
                <div style={{ fontSize: 32, fontWeight: 700, color: '#1e293b' }}>
                  {dipendenti.length}
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>Dipendenti</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent style={{ padding: 16, textAlign: 'center' }}>
                <div style={{ fontSize: 32, fontWeight: 700, color: '#22c55e' }}>
                  {saldi.length}
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>Con Saldi Registrati</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent style={{ padding: 16, textAlign: 'center' }}>
                <div style={{ fontSize: 32, fontWeight: 700, color: '#f59e0b' }}>
                  {dipendenti.length - saldi.length}
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>Senza Saldi</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent style={{ padding: 16, textAlign: 'center' }}>
                <div style={{ fontSize: 32, fontWeight: 700, color: '#3b82f6' }}>
                  {saldi.filter(s => s.source === 'libro_unico_pdf').length}
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>Da Libro Unico</div>
              </CardContent>
            </Card>
          </PageGrid>
          
          {/* Ricerca */}
          <div style={{ marginTop: 20, marginBottom: 16 }}>
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 12,
              background: '#f8fafc',
              padding: 12,
              borderRadius: 12
            }}>
              <Search size={20} color="#64748b" />
              <input
                type="text"
                placeholder="Cerca dipendente..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  fontSize: 14
                }}
              />
              <span style={{ fontSize: 13, color: '#64748b' }}>
                {dipendentiConSaldi.length} risultati
              </span>
            </div>
          </div>
          
          {/* Tabella Dipendenti */}
          <Card>
            <CardContent style={{ padding: 0 }}>
              {dipendentiConSaldi.length === 0 ? (
                <PageEmpty icon="👥" message="Nessun dipendente trovato" />
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                      <th style={{ padding: '12px 16px', textAlign: 'left' }}>Dipendente</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>Ferie</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>ROL</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>Ex-Fest.</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>Permessi</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>Periodo</th>
                      <th style={{ padding: '12px 16px', textAlign: 'center' }}>Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dipendentiConSaldi.map((dip, idx) => (
                      <tr 
                        key={dip.id}
                        style={{ 
                          borderBottom: '1px solid #f1f5f9',
                          background: idx % 2 === 0 ? 'white' : '#fafafa'
                        }}
                      >
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ fontWeight: 600 }}>
                            {dip.nome_completo || `${dip.cognome || ''} ${dip.nome || ''}`}
                          </div>
                          {dip.source && (
                            <div style={{ 
                              fontSize: 11, 
                              color: '#64748b',
                              marginTop: 2
                            }}>
                              Fonte: {dip.source === 'libro_unico_pdf' ? '📄 Libro Unico' : 
                                     dip.source === 'manual' ? '✏️ Manuale' : dip.source}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {dip.saldi ? (
                            <span style={{ 
                              fontWeight: 600, 
                              color: (dip.saldi.FER || 0) > 0 ? '#22c55e' : '#94a3b8'
                            }}>
                              {formatOre(dip.saldi.FER)}
                            </span>
                          ) : (
                            <span style={{ color: '#cbd5e1' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {dip.saldi ? (
                            <span style={{ 
                              fontWeight: 600, 
                              color: (dip.saldi.ROL || 0) > 0 ? '#3b82f6' : '#94a3b8'
                            }}>
                              {formatOre(dip.saldi.ROL)}
                            </span>
                          ) : (
                            <span style={{ color: '#cbd5e1' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {dip.saldi ? (
                            <span style={{ 
                              fontWeight: 600, 
                              color: (dip.saldi.EXF || 0) > 0 ? '#8b5cf6' : '#94a3b8'
                            }}>
                              {formatOre(dip.saldi.EXF)}
                            </span>
                          ) : (
                            <span style={{ color: '#cbd5e1' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {dip.saldi ? (
                            <span style={{ 
                              fontWeight: 600, 
                              color: (dip.saldi.PER || 0) > 0 ? '#f59e0b' : '#94a3b8'
                            }}>
                              {formatOre(dip.saldi.PER)}
                            </span>
                          ) : (
                            <span style={{ color: '#cbd5e1' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          {dip.periodo ? (
                            <span style={{ fontSize: 13, color: '#64748b' }}>
                              {dip.periodo}
                            </span>
                          ) : (
                            <span style={{ color: '#cbd5e1', fontSize: 13 }}>N/D</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => loadDettaglio(dip.id)}
                              disabled={loadingDettaglio && selectedDip === dip.id}
                            >
                              {loadingDettaglio && selectedDip === dip.id ? '...' : 'Dettagli'}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => openEditModal(dip, dip.saldi)}
                              title="Modifica saldi"
                            >
                              <Edit size={14} />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              data-testid={`modifica-periodo-${dip.id}`}
                              onClick={() => {
                                const nuovoPeriodo = prompt('Modifica periodo (es. 2026-02):', dip.periodo || '');
                                if (nuovoPeriodo && nuovoPeriodo !== dip.periodo) {
                                  api.put(`/api/giustificativi/saldi-finali/${dip.id}/periodo`, { anno: selectedYear, periodo: nuovoPeriodo })
                                    .then(() => { loadSaldi(); })
                                    .catch(e => alert('Errore: ' + (e.response?.data?.detail || e.message)));
                                }
                              }}
                              title="Modifica periodo"
                              style={{ color: '#3b82f6' }}
                            >
                              <Calendar size={14} />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              data-testid={`elimina-saldo-${dip.id}`}
                              onClick={() => {
                                if (window.confirm(`Eliminare i saldi ferie/permessi di ${dip.nome}?`)) {
                                  api.delete(`/api/giustificativi/saldi-finali/${dip.id}?anno=${selectedYear}`)
                                    .then(() => { loadSaldi(); })
                                    .catch(e => alert('Errore: ' + (e.response?.data?.detail || e.message)));
                                }
                              }}
                              title="Elimina richiesta"
                              style={{ color: '#ef4444' }}
                            >
                              <Trash2 size={14} />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
          
          {/* Pannello Dettaglio */}
          {dettaglio && (
            <Card style={{ marginTop: 20 }}>
              <CardHeader>
                <CardTitle>
                  Dettaglio: {dettaglio.employee_nome}
                </CardTitle>
                <CardDescription>
                  Ultimo periodo letto: {dettaglio.ultimo_periodo_letto || 'N/D'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PageGrid cols={2} gap={20}>
                  {/* Saldi Attuali */}
                  <div>
                    <h4 style={{ margin: '0 0 12px 0', fontWeight: 600 }}>Saldi Ultimo Periodo</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {Object.entries(dettaglio.saldi_ultimo_periodo || {}).map(([codice, ore]) => (
                        <div 
                          key={codice}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: 12,
                            background: '#f8fafc',
                            borderRadius: 8
                          }}
                        >
                          <span style={{ fontWeight: 500 }}>{codice}</span>
                          <span style={{ fontWeight: 700, color: '#1e293b' }}>{formatOre(ore)}</span>
                        </div>
                      ))}
                      {Object.keys(dettaglio.saldi_ultimo_periodo || {}).length === 0 && (
                        <div style={{ color: '#94a3b8', fontStyle: 'italic' }}>
                          Nessun saldo disponibile
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* Totali Anno */}
                  <div>
                    <h4 style={{ margin: '0 0 12px 0', fontWeight: 600 }}>Totali Anno {selectedYear}</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {Object.entries(dettaglio.totali_anno || {}).map(([codice, ore]) => (
                        <div 
                          key={codice}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: 12,
                            background: '#f0fdf4',
                            borderRadius: 8
                          }}
                        >
                          <span style={{ fontWeight: 500 }}>{codice}</span>
                          <span style={{ fontWeight: 700, color: '#166534' }}>{formatOre(ore)}</span>
                        </div>
                      ))}
                      {Object.keys(dettaglio.totali_anno || {}).length === 0 && (
                        <div style={{ color: '#94a3b8', fontStyle: 'italic' }}>
                          Nessun totale disponibile
                        </div>
                      )}
                    </div>
                  </div>
                </PageGrid>
                
                {/* Storico Mesi */}
                {dettaglio.storico_mesi && dettaglio.storico_mesi.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <h4 style={{ margin: '0 0 12px 0', fontWeight: 600 }}>Storico per Mese</h4>
                    <div style={{ 
                      display: 'grid', 
                      gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                      gap: 12 
                    }}>
                      {dettaglio.storico_mesi.slice(0, 12).map((mese, idx) => (
                        <div 
                          key={idx}
                          style={{
                            padding: 12,
                            background: '#f8fafc',
                            borderRadius: 8,
                            border: '1px solid #e2e8f0'
                          }}
                        >
                          <div style={{ fontWeight: 600, marginBottom: 8, color: '#1e293b' }}>
                            {mese.mese}
                          </div>
                          {Object.entries(mese.giustificativi || {}).map(([cod, ore]) => (
                            <div key={cod} style={{ fontSize: 13, color: '#64748b' }}>
                              {cod}: {ore}h
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
          
          {/* Modal Modifica */}
          {showEditModal && (
            <div style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}>
              <div style={{
                background: 'white',
                borderRadius: 16,
                padding: 24,
                width: '100%',
                maxWidth: 400
              }}>
                <h3 style={{ margin: '0 0 20px 0' }}>Modifica Saldi Finali</h3>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                      Ferie (ore)
                    </label>
                    <input
                      type="number"
                      value={editData.ferie}
                      onChange={(e) => setEditData(prev => ({ ...prev, ferie: e.target.value }))}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        border: '1px solid #e2e8f0',
                        borderRadius: 8
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                      ROL (ore)
                    </label>
                    <input
                      type="number"
                      value={editData.rol}
                      onChange={(e) => setEditData(prev => ({ ...prev, rol: e.target.value }))}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        border: '1px solid #e2e8f0',
                        borderRadius: 8
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                      Ex-Festività (ore)
                    </label>
                    <input
                      type="number"
                      value={editData.exf}
                      onChange={(e) => setEditData(prev => ({ ...prev, exf: e.target.value }))}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        border: '1px solid #e2e8f0',
                        borderRadius: 8
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                      Permessi (ore)
                    </label>
                    <input
                      type="number"
                      value={editData.per}
                      onChange={(e) => setEditData(prev => ({ ...prev, per: e.target.value }))}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        border: '1px solid #e2e8f0',
                        borderRadius: 8
                      }}
                    />
                  </div>
                </div>
                
                <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
                  <Button
                    variant="outline"
                    onClick={() => setShowEditModal(false)}
                    style={{ flex: 1 }}
                  >
                    Annulla
                  </Button>
                  <Button
                    onClick={saveSaldi}
                    disabled={saving}
                    style={{ flex: 1 }}
                  >
                    {saving ? 'Salvataggio...' : 'Salva'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}
