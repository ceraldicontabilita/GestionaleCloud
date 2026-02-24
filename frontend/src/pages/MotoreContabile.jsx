import React, { useState, useEffect } from 'react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Loader2, TrendingUp, TrendingDown, Building2, Calculator, FileText, RefreshCw } from 'lucide-react';
import api from '../api';
import { PageLayout } from '../components/PageLayout';

export default function MotoreContabile() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('bilancio');
  
  const [statoPatrimoniale, setStatoPatrimoniale] = useState(null);
  const [contoEconomico, setContoEconomico] = useState(null);
  const [cespiti, setCespiti] = useState([]);
  const [bilancioVerifica, setBilancioVerifica] = useState(null);
  
  const fetchStatoPatrimoniale = async () => {
    try {
      const res = await api.get(`/api/contabilita/bilancio/stato-patrimoniale?anno=${selectedYear}`);
      if (res.data?.success) {
        setStatoPatrimoniale(res.data);
      }
    } catch (err) {
      console.error('Errore caricamento SP:', err);
    }
  };
  
  const fetchContoEconomico = async () => {
    try {
      const res = await api.get(`/api/contabilita/bilancio/conto-economico?anno=${selectedYear}`);
      if (res.data?.success) {
        setContoEconomico(res.data);
      }
    } catch (err) {
      console.error('Errore caricamento CE:', err);
    }
  };
  
  const fetchCespiti = async () => {
    try {
      const res = await api.get(`/api/contabilita/cespiti`);
      if (res.data?.success) {
        setCespiti(res.data.cespiti || []);
      }
    } catch (err) {
      console.error('Errore caricamento cespiti:', err);
    }
  };
  
  const fetchBilancioVerifica = async () => {
    try {
      const res = await api.get(`/api/contabilita/bilancio-verifica?anno=${selectedYear}`);
      if (res.data?.success !== false) {
        setBilancioVerifica(res.data);
      }
    } catch (err) {
      console.error('Errore caricamento BV:', err);
    }
  };
  
  const loadAllData = async () => {
    setLoading(true);
    await Promise.all([
      fetchStatoPatrimoniale(),
      fetchContoEconomico(),
      fetchCespiti(),
      fetchBilancioVerifica()
    ]);
    setLoading(false);
  };
  
  useEffect(() => {
    loadAllData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear]);
  
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('it-IT', {
      style: 'currency',
      currency: 'EUR'
    }).format(value);
  };

  return (
    <PageLayout title="Motore Contabile" subtitle="Bilancio, Stato Patrimoniale, Conto Economico e Cespiti">
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: 24 
      }}>
        <div>
          <h1 style={{ 
            fontSize: 28, 
            fontWeight: 700, 
            color: '#1e293b',
            margin: 0
          }}>
            <Calculator style={{ display: 'inline', marginRight: 10, verticalAlign: 'middle' }} />
            Motore Contabile
          </h1>
          <p style={{ color: '#64748b', marginTop: 4 }}>
            Bilancio CEE, Stato Patrimoniale, Conto Economico, Cespiti - Anno {selectedYear}
          </p>
        </div>
        <Button 
          onClick={loadAllData} 
          disabled={loading}
          variant="outline"
        >
          <RefreshCw style={{ width: 16, height: 16, marginRight: 8 }} />
          Aggiorna
        </Button>
      </div>
      
      {loading && (
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          padding: 60 
        }}>
          <Loader2 className="animate-spin" style={{ width: 40, height: 40, color: '#1535a8' }} />
        </div>
      )}
      
      {!loading && (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList style={{ marginBottom: 20 }}>
            <TabsTrigger value="bilancio" data-testid="tab-bilancio">
              <FileText style={{ width: 16, height: 16, marginRight: 6 }} />
              Bilancio di Verifica
            </TabsTrigger>
            <TabsTrigger value="stato-patrimoniale" data-testid="tab-sp">
              <Building2 style={{ width: 16, height: 16, marginRight: 6 }} />
              Stato Patrimoniale
            </TabsTrigger>
            <TabsTrigger value="conto-economico" data-testid="tab-ce">
              <TrendingUp style={{ width: 16, height: 16, marginRight: 6 }} />
              Conto Economico
            </TabsTrigger>
            <TabsTrigger value="cespiti" data-testid="tab-cespiti">
              <Calculator style={{ width: 16, height: 16, marginRight: 6 }} />
              Cespiti
            </TabsTrigger>
          </TabsList>
          
          {/* TAB: Bilancio di Verifica */}
          <TabsContent value="bilancio">
            <Card>
              <CardHeader>
                <CardTitle>Bilancio di Verifica</CardTitle>
                <CardDescription>
                  Saldi di tutti i conti al {selectedYear}-12-31
                </CardDescription>
              </CardHeader>
              <CardContent>
                {bilancioVerifica?.conti?.length > 0 ? (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                        <th style={{ textAlign: 'left', padding: '12px 8px' }}>Codice</th>
                        <th style={{ textAlign: 'left', padding: '12px 8px' }}>Conto</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Dare</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Avere</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Saldo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bilancioVerifica.conti.map((conto, idx) => (
                        <tr 
                          key={idx}
                          style={{ 
                            borderBottom: '1px solid #f1f5f9',
                            background: idx % 2 === 0 ? '#fafafa' : 'white'
                          }}
                        >
                          <td style={{ padding: '10px 8px', fontFamily: 'monospace' }}>
                            {conto.codice}
                          </td>
                          <td style={{ padding: '10px 8px' }}>{conto.nome}</td>
                          <td style={{ 
                            padding: '10px 8px', 
                            textAlign: 'right',
                            color: conto.dare > 0 ? '#059669' : '#94a3b8'
                          }}>
                            {formatCurrency(conto.dare)}
                          </td>
                          <td style={{ 
                            padding: '10px 8px', 
                            textAlign: 'right',
                            color: conto.avere > 0 ? '#dc2626' : '#94a3b8'
                          }}>
                            {formatCurrency(conto.avere)}
                          </td>
                          <td style={{ 
                            padding: '10px 8px', 
                            textAlign: 'right',
                            fontWeight: 600,
                            color: conto.saldo >= 0 ? '#059669' : '#dc2626'
                          }}>
                            {formatCurrency(conto.saldo)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ 
                        borderTop: '2px solid #1e293b',
                        fontWeight: 700,
                        background: '#f8fafc'
                      }}>
                        <td colSpan={2} style={{ padding: '12px 8px' }}>TOTALI</td>
                        <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                          {formatCurrency(bilancioVerifica.totale_dare)}
                        </td>
                        <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                          {formatCurrency(bilancioVerifica.totale_avere)}
                        </td>
                        <td style={{ 
                          padding: '12px 8px', 
                          textAlign: 'right',
                          color: bilancioVerifica.quadratura ? '#059669' : '#dc2626'
                        }}>
                          {bilancioVerifica.quadratura ? '✓ Quadra' : '✗ Sbilancio'}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                ) : (
                  <div style={{ 
                    textAlign: 'center', 
                    padding: 40, 
                    color: '#64748b' 
                  }}>
                    <FileText style={{ width: 48, height: 48, margin: '0 auto 16px', opacity: 0.3 }} />
                    <p>Nessun movimento contabile per {selectedYear}</p>
                    <p style={{ fontSize: 13, marginTop: 8 }}>
                      I dati appariranno dopo aver registrato operazioni contabili
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
          
          {/* TAB: Stato Patrimoniale */}
          <TabsContent value="stato-patrimoniale">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              {/* ATTIVO */}
              <Card>
                <CardHeader style={{ background: '#ecfdf5', borderRadius: '12px 12px 0 0' }}>
                  <CardTitle style={{ color: '#059669' }}>
                    <TrendingUp style={{ display: 'inline', marginRight: 8 }} />
                    ATTIVO
                  </CardTitle>
                  <CardDescription>
                    Totale: {formatCurrency(statoPatrimoniale?.attivo?.totale || 0)}
                  </CardDescription>
                </CardHeader>
                <CardContent style={{ padding: 16 }}>
                  {statoPatrimoniale?.attivo?.sezioni && 
                   Object.entries(statoPatrimoniale.attivo.sezioni).map(([key, section]) => (
                    <div key={key} style={{ marginBottom: 16 }}>
                      <div style={{ 
                        fontWeight: 600, 
                        color: '#1e293b',
                        marginBottom: 8,
                        fontSize: 14
                      }}>
                        Sezione {key}
                      </div>
                      {section.conti?.map((conto, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between',
                            padding: '6px 0',
                            fontSize: 13,
                            borderBottom: '1px solid #f1f5f9'
                          }}
                        >
                          <span style={{ color: '#64748b' }}>
                            {conto.codice} - {conto.nome}
                          </span>
                          <span style={{ fontWeight: 500 }}>
                            {formatCurrency(conto.saldo)}
                          </span>
                        </div>
                      ))}
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between',
                        padding: '8px 0',
                        fontWeight: 600,
                        borderTop: '1px solid #e5e7eb',
                        marginTop: 4
                      }}>
                        <span>Totale sezione</span>
                        <span>{formatCurrency(section.totale)}</span>
                      </div>
                    </div>
                  ))}
                  
                  {!statoPatrimoniale?.attivo?.sezioni && (
                    <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>
                      Nessun dato disponibile
                    </div>
                  )}
                </CardContent>
              </Card>
              
              {/* PASSIVO */}
              <Card>
                <CardHeader style={{ background: '#fef2f2', borderRadius: '12px 12px 0 0' }}>
                  <CardTitle style={{ color: '#dc2626' }}>
                    <TrendingDown style={{ display: 'inline', marginRight: 8 }} />
                    PASSIVO
                  </CardTitle>
                  <CardDescription>
                    Totale: {formatCurrency(statoPatrimoniale?.passivo?.totale || 0)}
                  </CardDescription>
                </CardHeader>
                <CardContent style={{ padding: 16 }}>
                  {statoPatrimoniale?.passivo?.sezioni && 
                   Object.entries(statoPatrimoniale.passivo.sezioni).map(([key, section]) => (
                    <div key={key} style={{ marginBottom: 16 }}>
                      <div style={{ 
                        fontWeight: 600, 
                        color: '#1e293b',
                        marginBottom: 8,
                        fontSize: 14
                      }}>
                        Sezione {key}
                      </div>
                      {section.conti?.map((conto, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between',
                            padding: '6px 0',
                            fontSize: 13,
                            borderBottom: '1px solid #f1f5f9'
                          }}
                        >
                          <span style={{ color: '#64748b' }}>
                            {conto.codice} - {conto.nome}
                          </span>
                          <span style={{ fontWeight: 500 }}>
                            {formatCurrency(Math.abs(conto.saldo))}
                          </span>
                        </div>
                      ))}
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between',
                        padding: '8px 0',
                        fontWeight: 600,
                        borderTop: '1px solid #e5e7eb',
                        marginTop: 4
                      }}>
                        <span>Totale sezione</span>
                        <span>{formatCurrency(Math.abs(section.totale))}</span>
                      </div>
                    </div>
                  ))}
                  
                  {!statoPatrimoniale?.passivo?.sezioni && (
                    <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>
                      Nessun dato disponibile
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
            
            {/* Riepilogo */}
            {statoPatrimoniale && (
              <Card style={{ marginTop: 20 }}>
                <CardContent style={{ padding: 20 }}>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-around',
                    textAlign: 'center'
                  }}>
                    <div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                        TOTALE ATTIVO
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 700, color: '#059669' }}>
                        {formatCurrency(statoPatrimoniale.attivo?.totale || 0)}
                      </div>
                    </div>
                    <div style={{ 
                      width: 1, 
                      background: '#e5e7eb',
                      margin: '0 20px'
                    }} />
                    <div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                        TOTALE PASSIVO
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 700, color: '#dc2626' }}>
                        {formatCurrency(statoPatrimoniale.passivo?.totale || 0)}
                      </div>
                    </div>
                    <div style={{ 
                      width: 1, 
                      background: '#e5e7eb',
                      margin: '0 20px'
                    }} />
                    <div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                        QUADRATURA
                      </div>
                      <div style={{ 
                        fontSize: 24, 
                        fontWeight: 700, 
                        color: statoPatrimoniale.quadratura ? '#059669' : '#dc2626'
                      }}>
                        {statoPatrimoniale.quadratura ? '✓ OK' : '✗ Sbilancio'}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
          
          {/* TAB: Conto Economico */}
          <TabsContent value="conto-economico">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              {/* RICAVI */}
              <Card>
                <CardHeader style={{ background: '#ecfdf5', borderRadius: '12px 12px 0 0' }}>
                  <CardTitle style={{ color: '#059669' }}>RICAVI</CardTitle>
                  <CardDescription>
                    Valore della Produzione
                  </CardDescription>
                </CardHeader>
                <CardContent style={{ padding: 16 }}>
                  {contoEconomico?.ricavi?.voci?.map((voce, idx) => (
                    <div 
                      key={idx}
                      style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between',
                        padding: '8px 0',
                        borderBottom: '1px solid #f1f5f9'
                      }}
                    >
                      <span>{voce.codice} - {voce.nome}</span>
                      <span style={{ fontWeight: 500, color: '#059669' }}>
                        {formatCurrency(voce.importo)}
                      </span>
                    </div>
                  )) || (
                    <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>
                      Nessun ricavo registrato
                    </div>
                  )}
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    padding: '12px 0',
                    fontWeight: 700,
                    borderTop: '2px solid #059669',
                    marginTop: 8,
                    fontSize: 16
                  }}>
                    <span>TOTALE RICAVI</span>
                    <span style={{ color: '#059669' }}>
                      {formatCurrency(contoEconomico?.ricavi?.totale || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>
              
              {/* COSTI */}
              <Card>
                <CardHeader style={{ background: '#fef2f2', borderRadius: '12px 12px 0 0' }}>
                  <CardTitle style={{ color: '#dc2626' }}>COSTI</CardTitle>
                  <CardDescription>
                    Costi della Produzione
                  </CardDescription>
                </CardHeader>
                <CardContent style={{ padding: 16 }}>
                  {contoEconomico?.costi?.voci?.map((voce, idx) => (
                    <div 
                      key={idx}
                      style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between',
                        padding: '8px 0',
                        borderBottom: '1px solid #f1f5f9'
                      }}
                    >
                      <span>{voce.codice} - {voce.nome}</span>
                      <span style={{ fontWeight: 500, color: '#dc2626' }}>
                        {formatCurrency(voce.importo)}
                      </span>
                    </div>
                  )) || (
                    <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>
                      Nessun costo registrato
                    </div>
                  )}
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    padding: '12px 0',
                    fontWeight: 700,
                    borderTop: '2px solid #dc2626',
                    marginTop: 8,
                    fontSize: 16
                  }}>
                    <span>TOTALE COSTI</span>
                    <span style={{ color: '#dc2626' }}>
                      {formatCurrency(contoEconomico?.costi?.totale || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>
            
            {/* Risultato */}
            <Card style={{ marginTop: 20 }}>
              <CardContent style={{ padding: 24 }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 14, color: '#64748b', marginBottom: 8 }}>
                    RISULTATO DI ESERCIZIO
                  </div>
                  <div style={{ 
                    fontSize: 36, 
                    fontWeight: 700, 
                    color: (contoEconomico?.risultato || 0) >= 0 ? '#059669' : '#dc2626'
                  }}>
                    {formatCurrency(contoEconomico?.risultato || 0)}
                  </div>
                  <div style={{ 
                    marginTop: 8,
                    padding: '4px 12px',
                    borderRadius: 20,
                    display: 'inline-block',
                    background: (contoEconomico?.risultato || 0) >= 0 ? '#dcfce7' : '#fee2e2',
                    color: (contoEconomico?.risultato || 0) >= 0 ? '#166534' : '#991b1b',
                    fontSize: 14
                  }}>
                    {(contoEconomico?.risultato || 0) >= 0 ? 'UTILE' : 'PERDITA'}
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
          
          {/* TAB: Cespiti */}
          <TabsContent value="cespiti">
            <Card>
              <CardHeader>
                <CardTitle>Registro Cespiti</CardTitle>
                <CardDescription>
                  {cespiti.length} cespiti registrati
                </CardDescription>
              </CardHeader>
              <CardContent>
                {cespiti.length > 0 ? (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f8fafc' }}>
                        <th style={{ textAlign: 'left', padding: '12px 8px' }}>Descrizione</th>
                        <th style={{ textAlign: 'left', padding: '12px 8px' }}>Categoria</th>
                        <th style={{ textAlign: 'center', padding: '12px 8px' }}>Data Acq.</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Val. Acquisto</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Fondo Amm.</th>
                        <th style={{ textAlign: 'right', padding: '12px 8px' }}>Val. Residuo</th>
                        <th style={{ textAlign: 'center', padding: '12px 8px' }}>% Amm.</th>
                        <th style={{ textAlign: 'center', padding: '12px 8px' }}>Stato</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cespiti.map((cespite, idx) => (
                        <tr 
                          key={cespite.id}
                          style={{ 
                            borderBottom: '1px solid #f1f5f9',
                            background: idx % 2 === 0 ? 'white' : '#fafafa'
                          }}
                        >
                          <td style={{ padding: '10px 8px', fontWeight: 500 }}>
                            {cespite.descrizione}
                          </td>
                          <td style={{ padding: '10px 8px', color: '#64748b' }}>
                            {cespite.categoria}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', fontSize: 13 }}>
                            {cespite.data_acquisto}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'right' }}>
                            {formatCurrency(cespite.valore_acquisto)}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', color: '#dc2626' }}>
                            {formatCurrency(cespite.fondo_ammortamento)}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>
                            {formatCurrency(cespite.valore_residuo)}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                            {cespite.coefficiente_ammortamento}%
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: 12,
                              fontSize: 12,
                              background: cespite.stato === 'attivo' ? '#dcfce7' : '#fee2e2',
                              color: cespite.stato === 'attivo' ? '#166534' : '#991b1b'
                            }}>
                              {cespite.stato}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ 
                        borderTop: '2px solid #1e293b',
                        fontWeight: 700,
                        background: '#f8fafc'
                      }}>
                        <td colSpan={3} style={{ padding: '12px 8px' }}>TOTALI</td>
                        <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                          {formatCurrency(cespiti.reduce((sum, c) => sum + (c.valore_acquisto || 0), 0))}
                        </td>
                        <td style={{ padding: '12px 8px', textAlign: 'right', color: '#dc2626' }}>
                          {formatCurrency(cespiti.reduce((sum, c) => sum + (c.fondo_ammortamento || 0), 0))}
                        </td>
                        <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                          {formatCurrency(cespiti.reduce((sum, c) => sum + (c.valore_residuo || 0), 0))}
                        </td>
                        <td colSpan={2}></td>
                      </tr>
                    </tfoot>
                  </table>
                ) : (
                  <div style={{ 
                    textAlign: 'center', 
                    padding: 40, 
                    color: '#64748b' 
                  }}>
                    <Building2 style={{ width: 48, height: 48, margin: '0 auto 16px', opacity: 0.3 }} />
                    <p>Nessun cespite registrato</p>
                    <p style={{ fontSize: 13, marginTop: 8 }}>
                      Registra cespiti tramite API /api/contabilita/cespiti
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
    </PageLayout>
  );
}
