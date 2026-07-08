import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, COLORS, BORDER_RADIUS } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { toast } from 'sonner';
import { Button, Badge, Card, Input, Select, Tabs, StatCard } from '../components/ds';

export default function PrevisioniAcquisti() {
  const { anno: annoGlobale } = useAnnoGlobale();
  const [activeTab, setActiveTab] = useState('statistiche');
  const [statistiche, setStatistiche] = useState([]);
  const [previsioni, setPrevisioni] = useState([]);
  const [loading, setLoading] = useState(false);
  const [popolando, setPopolando] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [settimanePrevisione, setSettimanePrevisione] = useState(4);
  const [costoTotale, setCostoTotale] = useState(0);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    loadData();
  }, [annoGlobale, activeTab, settimanePrevisione]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'statistiche') {
        const res = await api.get(`/api/previsioni-acquisti/statistiche?anno=${annoGlobale}`);
        setStatistiche(res.data.statistiche || []);
      } else {
        const annoRif = annoGlobale - 1;
        const res = await api.get(
          `/api/previsioni-acquisti/previsioni?anno_riferimento=${annoRif}&settimane_previsione=${settimanePrevisione}`
        );
        setPrevisioni(res.data.previsioni || []);
        setCostoTotale(res.data.costo_totale_stimato || 0);
      }
    } catch (error) {
      console.error('Errore:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePopolaStorico = async () => {
    setPopolando(true);
    try {
      const res = await api.post('/api/previsioni-acquisti/popola-storico');
      toast.success(
        `Storico popolato! Fatture processate: ${res.data.fatture_processate}, prodotti registrati: ${res.data.prodotti_registrati}`
      );
      loadData();
    } catch (error) {
      toast.error(`Errore: ${error.response?.data?.detail || error.message}`);
    } finally {
      setPopolando(false);
    }
  };

  const filteredData =
    activeTab === 'statistiche'
      ? statistiche.filter(s => s.descrizione?.toLowerCase().includes(searchTerm.toLowerCase()))
      : previsioni.filter(p => p.prodotto?.toLowerCase().includes(searchTerm.toLowerCase()));

  const getTrendVariant = trend => {
    if (trend === '↑') return 'success';
    if (trend === '↓') return 'danger';
    return 'neutral';
  };

  return (
    <PageLayout title="Previsioni Acquisti" subtitle="Analisi consumi e previsioni ordinazioni">
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
              marginBottom: 8,
            }}
          >
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold', color: COLORS.text }}>
              📊 Previsioni Acquisti
            </h1>
            <Badge variant="primary">{annoGlobale}</Badge>
          </div>
          <p style={{ margin: 0, color: COLORS.textMuted, fontSize: 13 }}>
            Analisi storico acquisti e previsioni basate sui consumi
          </p>
        </div>

        {/* Tabs e Controlli */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            marginBottom: 16,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <Tabs
            items={[
              { key: 'statistiche', label: `📈 Statistiche ${annoGlobale}` },
              { key: 'previsioni', label: '🔮 Previsioni' },
            ]}
            value={activeTab}
            onChange={setActiveTab}
          />

          <div style={{ flex: 1 }} />

          {activeTab === 'previsioni' && (
            <Select
              value={settimanePrevisione}
              onChange={e => setSettimanePrevisione(Number(e.target.value))}
            >
              <option value={1}>1 settimana</option>
              <option value={2}>2 settimane</option>
              <option value={4}>4 settimane</option>
              <option value={8}>8 settimane</option>
              <option value={12}>12 settimane</option>
            </Select>
          )}

          <Button
            variant="outline"
            onClick={loadData}
            disabled={loading}
            data-testid="refresh-btn"
          >
            🔄
          </Button>

          <Button
            variant="primary"
            onClick={handlePopolaStorico}
            disabled={popolando}
            data-testid="popola-storico-btn"
          >
            {popolando ? 'Popolando...' : '🔄 Popola Storico'}
          </Button>
        </div>

        {/* Ricerca */}
        <div style={{ marginBottom: 16 }}>
          <Input
            type="text"
            iconLeft="🔍"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Cerca prodotto (es: caffè, prosecco, farina...)"
            data-testid="search-input"
          />
        </div>

        {/* Riepilogo Previsioni */}
        {activeTab === 'previsioni' && costoTotale > 0 && (
          <StatCard
            icon="🛒"
            label={`Costo stimato prossime ${settimanePrevisione} settimane`}
            value={formatEuro(costoTotale)}
            accent="primary"
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Lista Prodotti */}
        <Card
          title={
            activeTab === 'statistiche' ? (
              <>
                📊 Consumi {annoGlobale} vs {annoGlobale - 1}
              </>
            ) : (
              <>📦 Acquisti Previsti ({filteredData.length} prodotti)</>
            )
          }
        >
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
              <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
              Caricamento...
            </div>
          ) : filteredData.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
              <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📦</div>
              <p>Nessun dato trovato</p>
              <p style={{ fontSize: 13 }}>
                Clicca &quot;Popola Storico&quot; per importare i dati dalle fatture
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filteredData.slice(0, 50).map((item, idx) => (
                <div
                  key={item.id || idx}
                  style={{
                    padding: 12,
                    background: COLORS.bgAlt,
                    borderRadius: BORDER_RADIUS.md,
                    border: `1px solid ${COLORS.border}`,
                  }}
                  data-testid={`product-item-${idx}`}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      cursor: 'pointer',
                    }}
                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                  >
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontWeight: 'bold',
                          fontSize: 14,
                          color: COLORS.text,
                          marginBottom: 4,
                        }}
                      >
                        {activeTab === 'statistiche' ? item.descrizione : item.prodotto}
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          gap: 12,
                          fontSize: 12,
                          color: COLORS.textMuted,
                          flexWrap: 'wrap',
                        }}
                      >
                        {activeTab === 'statistiche' ? (
                          <>
                            <span>
                              📦 {item.quantita_totale?.toFixed(1)} {item.unita_misura}
                            </span>
                            <span>📅 Media/gg: {item.media_giornaliera}</span>
                            <span>📆 Media/sett: {item.media_settimanale}</span>
                          </>
                        ) : (
                          <>
                            <span>
                              Prev: {item.quantita_prevista?.toFixed(1)} {item.unita_misura}
                            </span>
                            <span>{item.media_settimanale}/sett</span>
                            <span>{formatEuro(item.costo_stimato)}</span>
                          </>
                        )}
                      </div>
                    </div>

                    {activeTab === 'statistiche' && item.trend && (
                      <Badge variant={getTrendVariant(item.trend)}>
                        {item.trend === '↑' ? '📈' : item.trend === '↓' ? '📉' : ''}
                        {item.variazione_pct > 0 ? '+' : ''}
                        {item.variazione_pct}%
                      </Badge>
                    )}

                    <span style={{ marginLeft: 8 }}>{expandedId === item.id ? '▲' : '▼'}</span>
                  </div>

                  {/* Dettagli espansi */}
                  {expandedId === item.id && (
                    <div
                      style={{
                        marginTop: 12,
                        paddingTop: 12,
                        borderTop: `1px solid ${COLORS.border}`,
                        fontSize: 12,
                        color: COLORS.textMuted,
                      }}
                    >
                      {activeTab === 'statistiche' ? (
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                            gap: 8,
                          }}
                        >
                          <div>
                            <strong>Spesa totale:</strong> {formatEuro(item.spesa_totale)}
                          </div>
                          <div>
                            <strong>N. ordini:</strong> {item.num_acquisti}
                          </div>
                          <div>
                            <strong>Ogni:</strong> {item.frequenza_giorni} giorni
                          </div>
                          <div>
                            <strong>Anno prec.:</strong> {item.quantita_anno_prec?.toFixed(1)}{' '}
                            {item.unita_misura}
                          </div>
                          <div>
                            <strong>Primo:</strong> {item.primo_acquisto}
                          </div>
                          <div>
                            <strong>Ultimo:</strong> {item.ultimo_acquisto}
                          </div>
                        </div>
                      ) : (
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                            gap: 8,
                          }}
                        >
                          <div>
                            <strong>Anno rif.:</strong> {item.quantita_anno_rif?.toFixed(1)}{' '}
                            {item.unita_misura}
                          </div>
                          <div>
                            <strong>Prezzo medio:</strong> {formatEuro(item.prezzo_medio)}
                          </div>
                          <div>
                            <strong>Ordina ogni:</strong>{' '}
                            {item.frequenza_ordine_settimane?.toFixed(1)} sett.
                          </div>
                          <div>
                            <strong>Prossimo ordine:</strong> tra{' '}
                            {item.prossimo_ordine_tra_giorni} gg
                          </div>
                          {item.fornitori_abituali?.length > 0 && (
                            <div style={{ gridColumn: 'span 2' }}>
                              <strong>Fornitori:</strong> {item.fornitori_abituali.join(', ')}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Info */}
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: COLORS.infoLight,
            border: `1px solid ${COLORS.info}`,
            borderRadius: BORDER_RADIUS.md,
            fontSize: 12,
            color: COLORS.info,
          }}
        >
          💡 <strong>Come funziona:</strong> Il sistema analizza lo storico acquisti dalle fatture
          XML. Calcola medie giornaliere/settimanali e confronta con l&apos;anno precedente per
          suggerirti gli acquisti.
          <br />
          📊 <strong>Statistiche:</strong> Mostra consumi dell&apos;anno corrente vs anno
          precedente.
          <br />
          🔮 <strong>Previsioni:</strong> Propone quantità da ordinare basate sui consumi storici.
        </div>
      </div>
    </PageLayout>
  );
}
