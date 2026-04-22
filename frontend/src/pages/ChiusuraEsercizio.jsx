import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronRight,
  RefreshCw,
  FileText,
  Calendar,
  TrendingUp,
  TrendingDown,
  Lock,
  Unlock,
} from 'lucide-react';
import { PageLayout } from '../components/PageLayout';

export default function ChiusuraEsercizio() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [stato, setStato] = useState(null);
  const [verifica, setVerifica] = useState(null);
  const [bilancino, setBilancino] = useState(null);
  const [storico, setStorico] = useState([]);
  const [activeStep, setActiveStep] = useState(1);
  const [executing, setExecuting] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statoRes, verificaRes, bilancinoRes, storicoRes] = await Promise.all([
        api.get(`/api/chiusura-esercizio/stato/${anno}`),
        api.get(`/api/chiusura-esercizio/verifica-preliminare/${anno}`),
        api.get(`/api/chiusura-esercizio/bilancino-verifica/${anno}`),
        api.get('/api/chiusura-esercizio/storico'),
      ]);

      setStato(statoRes.data);
      setVerifica(verificaRes.data);
      setBilancino(bilancinoRes.data);
      setStorico(storicoRes.data);

      // Determina step attivo
      if (statoRes.data.stato === 'chiuso') {
        setActiveStep(4);
      } else if (verificaRes.data.pronto_per_chiusura) {
        setActiveStep(2);
      } else {
        setActiveStep(1);
      }
    } catch (err) {
      console.error('Errore caricamento dati:', err);
      setError('Errore nel caricamento dei dati');
    } finally {
      setLoading(false);
    }
  }, [anno]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const eseguiChiusura = async () => {
    setExecuting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post('/api/chiusura-esercizio/esegui-chiusura', {
        anno,
        conferma_scritture: true,
        note: note || null,
      });

      setSuccess(`Chiusura esercizio ${anno} completata con successo!`);
      await loadData();
    } catch (err) {
      console.error('Errore chiusura:', err);
      setError(err.response?.data?.detail || 'Errore durante la chiusura');
    } finally {
      setExecuting(false);
    }
  };

  const apriNuovoEsercizio = async () => {
    const nuovoAnno = anno + 1;
    setExecuting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post(
        `/api/chiusura-esercizio/apertura-nuovo-esercizio?anno_nuovo=${nuovoAnno}`
      );
      setSuccess(`Esercizio ${nuovoAnno} aperto con successo!`);
      // Recarica dati con il nuovo anno
      await loadData();
    } catch (err) {
      console.error('Errore apertura:', err);
      setError(err.response?.data?.detail || "Errore durante l'apertura");
    } finally {
      setExecuting(false);
    }
  };

  // currentYear dalla data corrente per confronti
  const currentYear = new Date().getFullYear();

  const StepIndicator = ({ number, title, active, completed }) => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        opacity: active ? 1 : 0.5,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: completed ? '#22c55e' : active ? '#2563eb' : '#e2e8f0',
          color: completed || active ? 'white' : '#64748b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 600,
          fontSize: 14,
        }}
      >
        {completed ? <CheckCircle size={20} /> : number}
      </div>
      <span
        style={{
          fontWeight: active ? 600 : 400,
          color: active ? '#1e293b' : '#64748b',
        }}
      >
        {title}
      </span>
    </div>
  );

  const ProblemaCard = ({ problema, tipo }) => {
    const isBloccante = tipo === 'bloccante';
    return (
      <div
        style={{
          background: isBloccante ? '#fef2f2' : '#fffbeb',
          border: `1px solid ${isBloccante ? '#fca5a5' : '#fcd34d'}`,
          borderRadius: 8,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          {isBloccante ? (
            <XCircle size={20} color="#dc2626" />
          ) : (
            <AlertTriangle size={20} color="#d97706" />
          )}
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontWeight: 600,
                color: isBloccante ? '#dc2626' : '#92400e',
                marginBottom: 4,
              }}
            >
              {problema.messaggio}
            </div>
            <div style={{ fontSize: 13, color: '#64748b' }}>{problema.azione}</div>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '60vh',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <RefreshCw size={32} style={{ animation: 'spin 1s linear infinite' }} color="#2563eb" />
        <span style={{ color: '#64748b' }}>Caricamento...</span>
      </div>
    );
  }

  return (
    <PageLayout
      title="Chiusura Esercizio"
      icon="📅"
      subtitle={`Wizard guidato per la chiusura annuale - Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              background: '#1e3a5f',
              color: 'white',
              fontSize: 16,
              fontWeight: 600,
            }}
          >
            Anno {anno}
          </span>

          <button
            onClick={loadData}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              background: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
            data-testid="refresh-button"
          >
            <RefreshCw size={18} />
            Aggiorna
          </button>
        </div>
      }
    >
      <div data-testid="chiusura-esercizio-page">
        {/* Alerts */}
        {error && (
          <div
            style={{
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              color: '#dc2626',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
            data-testid="error-alert"
          >
            <XCircle size={20} />
            {error}
          </div>
        )}

        {success && (
          <div
            style={{
              background: '#f0fdf4',
              border: '1px solid #86efac',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              color: '#166534',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
            data-testid="success-alert"
          >
            <CheckCircle size={20} />
            {success}
          </div>
        )}

        {/* Stato Esercizio Card */}
        <div
          style={{
            background: stato?.stato === 'chiuso' ? '#f0fdf4' : '#eff6ff',
            borderRadius: 12,
            padding: 24,
            marginBottom: 32,
            border: `1px solid ${stato?.stato === 'chiuso' ? '#86efac' : '#bfdbfe'}`,
          }}
          data-testid="stato-card"
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {stato?.stato === 'chiuso' ? (
                <Lock size={32} color="#16a34a" />
              ) : (
                <Unlock size={32} color="#2563eb" />
              )}
              <div>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: stato?.stato === 'chiuso' ? '#166534' : '#1e40af',
                  }}
                >
                  Esercizio {anno}
                </div>
                <div
                  style={{ color: stato?.stato === 'chiuso' ? '#15803d' : '#3b82f6', marginTop: 4 }}
                >
                  {stato?.stato === 'chiuso' ? 'Chiuso' : 'Aperto'}
                  {stato?.data_chiusura && ` il ${formatDateIT(stato.data_chiusura)}`}
                </div>
              </div>
            </div>

            {stato?.risultato_esercizio !== undefined && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 14, color: '#64748b' }}>Risultato</div>
                <div
                  style={{
                    fontSize: 24,
                    fontWeight: 700,
                    color: stato.risultato_esercizio >= 0 ? '#16a34a' : '#dc2626',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  {stato.risultato_esercizio >= 0 ? (
                    <TrendingUp size={24} />
                  ) : (
                    <TrendingDown size={24} />
                  )}
                  {formatEuro(stato.risultato_esercizio)}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Steps Progress */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 24,
            marginBottom: 32,
            padding: 20,
            background: '#f8fafc',
            borderRadius: 12,
          }}
        >
          <StepIndicator
            number={1}
            title="Verifica Preliminare"
            active={activeStep === 1}
            completed={activeStep > 1}
          />
          <ChevronRight size={20} color="#cbd5e1" />
          <StepIndicator
            number={2}
            title="Bilancino Verifica"
            active={activeStep === 2}
            completed={activeStep > 2}
          />
          <ChevronRight size={20} color="#cbd5e1" />
          <StepIndicator
            number={3}
            title="Chiusura"
            active={activeStep === 3}
            completed={activeStep > 3}
          />
          <ChevronRight size={20} color="#cbd5e1" />
          <StepIndicator
            number={4}
            title="Nuovo Esercizio"
            active={activeStep === 4}
            completed={false}
          />
        </div>

        <div
          style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 24 }}
        >
          {/* Left Column - Verifica */}
          <div>
            <div
              style={{
                background: 'white',
                borderRadius: 12,
                padding: 24,
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              }}
              data-testid="verifica-section"
            >
              <h3
                style={{
                  fontSize: 18,
                  fontWeight: 600,
                  marginBottom: 20,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <FileText size={20} />
                Verifica Preliminare
              </h3>

              {/* Punteggio Completezza */}
              <div
                style={{
                  background: '#f8fafc',
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 20,
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: 14, color: '#64748b', marginBottom: 8 }}>
                  Punteggio Completezza
                </div>
                <div
                  style={{
                    fontSize: 36,
                    fontWeight: 700,
                    color:
                      verifica?.punteggio_completezza >= 80
                        ? '#16a34a'
                        : verifica?.punteggio_completezza >= 50
                          ? '#d97706'
                          : '#dc2626',
                  }}
                >
                  {verifica?.punteggio_completezza || 0}%
                </div>
                <div
                  style={{
                    height: 8,
                    background: '#e2e8f0',
                    borderRadius: 4,
                    marginTop: 12,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${verifica?.punteggio_completezza || 0}%`,
                      background:
                        verifica?.punteggio_completezza >= 80
                          ? '#22c55e'
                          : verifica?.punteggio_completezza >= 50
                            ? '#f59e0b'
                            : '#ef4444',
                      borderRadius: 4,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              </div>

              {/* Problemi Bloccanti */}
              {verifica?.problemi_bloccanti?.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: '#dc2626', marginBottom: 12 }}>
                    Problemi Bloccanti ({verifica.problemi_bloccanti.length})
                  </h4>
                  {verifica.problemi_bloccanti.map((p, i) => (
                    <ProblemaCard key={i} problema={p} tipo="bloccante" />
                  ))}
                </div>
              )}

              {/* Avvisi */}
              {verifica?.avvisi?.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: '#d97706', marginBottom: 12 }}>
                    Avvisi ({verifica.avvisi.length})
                  </h4>
                  {verifica.avvisi.map((a, i) => (
                    <ProblemaCard key={i} problema={a} tipo="avviso" />
                  ))}
                </div>
              )}

              {/* Completamenti */}
              {verifica?.completamenti?.length > 0 && (
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: '#16a34a', marginBottom: 12 }}>
                    Completamenti ({verifica.completamenti.length})
                  </h4>
                  {verifica.completamenti.map((c, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '8px 0',
                        color: '#166534',
                      }}
                    >
                      <CheckCircle size={16} />
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Bilancino e Azioni */}
          <div>
            {/* Bilancino */}
            <div
              style={{
                background: 'white',
                borderRadius: 12,
                padding: 24,
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                marginBottom: 24,
              }}
              data-testid="bilancino-section"
            >
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>
                Bilancino di Verifica {anno}
              </h3>

              {bilancino?.bilancino && (
                <>
                  {/* Ricavi */}
                  <div
                    style={{
                      background: '#f0fdf4',
                      borderRadius: 8,
                      padding: 16,
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: '#166534', marginBottom: 12 }}>
                      RICAVI
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>Corrispettivi</span>
                      <span>{formatEuro(bilancino.bilancino.ricavi.corrispettivi)}</span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>Fatture Emesse</span>
                      <span>{formatEuro(bilancino.bilancino.ricavi.fatture_emesse)}</span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #86efac',
                        fontWeight: 600,
                      }}
                    >
                      <span>Totale Ricavi</span>
                      <span style={{ color: '#16a34a' }}>
                        {formatEuro(bilancino.bilancino.ricavi.totale)}
                      </span>
                    </div>
                  </div>

                  {/* Costi */}
                  <div
                    style={{
                      background: '#fef2f2',
                      borderRadius: 8,
                      padding: 16,
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: '#dc2626', marginBottom: 12 }}>COSTI</div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>Acquisti Merce</span>
                      <span>{formatEuro(bilancino.bilancino.costi.acquisti_merce)}</span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>Personale</span>
                      <span>{formatEuro(bilancino.bilancino.costi.personale)}</span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>Ammortamenti</span>
                      <span>{formatEuro(bilancino.bilancino.costi.ammortamenti)}</span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: '#64748b' }}>TFR</span>
                      <span>{formatEuro(bilancino.bilancino.costi.tfr)}</span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #fca5a5',
                        fontWeight: 600,
                      }}
                    >
                      <span>Totale Costi</span>
                      <span style={{ color: '#dc2626' }}>
                        {formatEuro(bilancino.bilancino.costi.totale)}
                      </span>
                    </div>
                  </div>

                  {/* Risultato */}
                  <div
                    style={{
                      background:
                        bilancino.bilancino.risultato.utile_perdita >= 0 ? '#ecfdf5' : '#fef2f2',
                      borderRadius: 8,
                      padding: 20,
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>RISULTATO D'ESERCIZIO</div>
                    <div
                      style={{
                        fontSize: 28,
                        fontWeight: 700,
                        color:
                          bilancino.bilancino.risultato.utile_perdita >= 0 ? '#16a34a' : '#dc2626',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 8,
                      }}
                    >
                      {bilancino.bilancino.risultato.utile_perdita >= 0 ? (
                        <TrendingUp size={28} />
                      ) : (
                        <TrendingDown size={28} />
                      )}
                      {formatEuro(bilancino.bilancino.risultato.utile_perdita)}
                    </div>
                    <div
                      style={{
                        fontSize: 14,
                        color: '#64748b',
                        marginTop: 8,
                      }}
                    >
                      {bilancino.bilancino.risultato.tipo.toUpperCase()} • Margine:{' '}
                      {bilancino.bilancino.risultato.margine_percentuale}%
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Azioni */}
            {stato?.stato !== 'chiuso' && (
              <div
                style={{
                  background: 'white',
                  borderRadius: 12,
                  padding: 24,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                }}
                data-testid="azioni-section"
              >
                <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Esegui Chiusura</h3>

                <div style={{ marginBottom: 16 }}>
                  <label
                    style={{ display: 'block', fontSize: 14, fontWeight: 500, marginBottom: 8 }}
                  >
                    Note (opzionale)
                  </label>
                  <textarea
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    placeholder="Inserisci eventuali note per la chiusura..."
                    style={{
                      width: '100%',
                      padding: 12,
                      borderRadius: 8,
                      border: '1px solid #e2e8f0',
                      minHeight: 80,
                      resize: 'vertical',
                    }}
                    data-testid="note-input"
                  />
                </div>

                <button
                  onClick={eseguiChiusura}
                  disabled={!verifica?.pronto_per_chiusura || executing}
                  style={{
                    width: '100%',
                    padding: '14px 24px',
                    borderRadius: 8,
                    border: 'none',
                    background: verifica?.pronto_per_chiusura ? '#2563eb' : '#94a3b8',
                    color: 'white',
                    fontWeight: 600,
                    fontSize: 16,
                    cursor: verifica?.pronto_per_chiusura ? 'pointer' : 'not-allowed',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                  data-testid="chiudi-esercizio-button"
                >
                  {executing ? (
                    <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <Lock size={20} />
                  )}
                  {executing ? 'Elaborazione...' : `Chiudi Esercizio ${anno}`}
                </button>

                {!verifica?.pronto_per_chiusura && (
                  <p
                    style={{
                      fontSize: 13,
                      color: '#ef4444',
                      marginTop: 12,
                      textAlign: 'center',
                    }}
                  >
                    Risolvi i problemi bloccanti prima di procedere
                  </p>
                )}
              </div>
            )}

            {/* Apertura Nuovo Esercizio */}
            {stato?.stato === 'chiuso' && (
              <div
                style={{
                  background: 'white',
                  borderRadius: 12,
                  padding: 24,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                }}
                data-testid="apertura-section"
              >
                <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>
                  Apertura Nuovo Esercizio
                </h3>

                <p style={{ color: '#64748b', marginBottom: 16 }}>
                  L'esercizio {anno} è stato chiuso. Puoi ora aprire l'esercizio {anno + 1}
                  riportando automaticamente i saldi.
                </p>

                <button
                  onClick={apriNuovoEsercizio}
                  disabled={executing}
                  style={{
                    width: '100%',
                    padding: '14px 24px',
                    borderRadius: 8,
                    border: 'none',
                    background: '#16a34a',
                    color: 'white',
                    fontWeight: 600,
                    fontSize: 16,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                  data-testid="apri-esercizio-button"
                >
                  {executing ? (
                    <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <Unlock size={20} />
                  )}
                  {executing ? 'Elaborazione...' : `Apri Esercizio ${anno + 1}`}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Storico Chiusure */}
        {storico.length > 0 && (
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              marginTop: 32,
            }}
            data-testid="storico-section"
          >
            <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Storico Chiusure</h3>

            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600 }}>Anno</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600 }}>
                    Data Chiusura
                  </th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>
                    Risultato
                  </th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600 }}>Note</th>
                </tr>
              </thead>
              <tbody>
                {storico.map((c, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600 }}>{c.anno}</td>
                    <td style={{ padding: '12px 16px', color: '#64748b' }}>
                      {formatDateIT(c.created_at)}
                    </td>
                    <td
                      style={{
                        padding: '12px 16px',
                        textAlign: 'right',
                        fontWeight: 600,
                        color: c.risultato_esercizio >= 0 ? '#16a34a' : '#dc2626',
                      }}
                    >
                      {formatEuro(c.risultato_esercizio)}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#64748b' }}>{c.note || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
      </div>
    </PageLayout>
  );
}
