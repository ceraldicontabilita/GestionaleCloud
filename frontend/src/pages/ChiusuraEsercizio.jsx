import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  FONT,
  useIsMobile,
} from '../lib/utils';
import { Button, Badge, StatCard, TableWrap, Table, Th, Td } from '../components/ds';
import { useConfirm } from '../components/ui/ConfirmDialog';
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

const MONO = FONT.mono;

export default function ChiusuraEsercizio() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [stato, setStato] = useState(null);
  const [verifica, setVerifica] = useState(null);
  const [bilancino, setBilancino] = useState(null);
  const [storico, setStorico] = useState([]);
  const [activeStep, setActiveStep] = useState(1);
  const [executing, setExecuting] = useState(false);
  const [note, setNote] = useState('');
  const [confirmationText, setConfirmationText] = useState('');
  const [openingConfirmationText, setOpeningConfirmationText] = useState('');
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
    // Scrittura contabile di chiusura: irreversibile. Conferma obbligatoria.
    const ok = await confirm({
      title: `Chiudi esercizio ${anno}`,
      message:
        `Verranno generate le scritture di chiusura dell'esercizio ${anno}. ` +
        `È un'operazione contabile importante e non reversibile. Procedere?`,
      variant: 'danger',
    });
    if (!ok) return;

    setExecuting(true);
    setError(null);
    setSuccess(null);

    try {
      await api.post('/api/chiusura-esercizio/esegui-chiusura', {
        anno,
        conferma_scritture: true,
        conferma_quadrature: true,
        conferma_testo: confirmationText,
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
    const ok = await confirm({
      title: `Apri esercizio ${nuovoAnno}`,
      message:
        `Verranno riportati i saldi di apertura sul nuovo esercizio ${nuovoAnno}. ` +
        `Procedere?`,
    });
    if (!ok) return;

    setExecuting(true);
    setError(null);
    setSuccess(null);

    try {
      await api.post('/api/chiusura-esercizio/apertura-nuovo-esercizio', {
        anno_nuovo: nuovoAnno,
        conferma_testo: openingConfirmationText,
      });
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
          background: completed ? COLORS.success : active ? COLORS.primary : COLORS.border,
          color: completed || active ? 'white' : COLORS.textMuted,
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
          color: active ? COLORS.text : COLORS.textMuted,
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
          background: isBloccante ? COLORS.dangerLight : COLORS.warningLight,
          border: `1px solid ${isBloccante ? COLORS.danger : COLORS.warning}`,
          borderRadius: BORDER_RADIUS.md,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          {isBloccante ? (
            <XCircle size={20} color={COLORS.danger} />
          ) : (
            <AlertTriangle size={20} color={COLORS.warning} />
          )}
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontWeight: 600,
                color: isBloccante ? COLORS.danger : COLORS.warning,
                marginBottom: 4,
              }}
            >
              {problema.messaggio}
            </div>
            <div style={{ fontSize: 13, color: COLORS.textMuted }}>{problema.azione}</div>
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
        <RefreshCw size={32} style={{ animation: 'spin 1s linear infinite' }} color={COLORS.primary} />
        <span style={{ color: COLORS.textMuted }}>Caricamento...</span>
      </div>
    );
  }

  return (
    <PageLayout
      title="Chiusura Esercizio"
      icon="📅"
      subtitle={`Wizard guidato per la chiusura annuale - Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Badge variant="primary" style={{ fontSize: 14, fontWeight: 600, padding: '10px 16px', textTransform: 'none' }}>
            Anno {anno}
          </Badge>

          <Button
            variant="secondary"
            size="md"
            onClick={loadData}
            iconLeft={<RefreshCw size={18} />}
            data-testid="refresh-button"
          >
            Aggiorna
          </Button>
        </div>
      }
    >
      <div data-testid="chiusura-esercizio-page">
        {/* Alerts */}
        {error && (
          <div
            style={{
              background: COLORS.dangerLight,
              border: `1px solid ${COLORS.danger}`,
              borderRadius: BORDER_RADIUS.md,
              padding: 16,
              marginBottom: 24,
              color: COLORS.danger,
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
              background: COLORS.successLight,
              border: `1px solid ${COLORS.success}`,
              borderRadius: BORDER_RADIUS.md,
              padding: 16,
              marginBottom: 24,
              color: COLORS.success,
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
            background: stato?.stato === 'chiuso' ? COLORS.successLight : COLORS.infoLight,
            borderRadius: BORDER_RADIUS.md,
            padding: 24,
            marginBottom: 32,
            border: `1px solid ${stato?.stato === 'chiuso' ? COLORS.success : COLORS.info}`,
          }}
          data-testid="stato-card"
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {stato?.stato === 'chiuso' ? (
                <Lock size={32} color={COLORS.success} />
              ) : (
                <Unlock size={32} color={COLORS.primary} />
              )}
              <div>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: stato?.stato === 'chiuso' ? COLORS.success : COLORS.info,
                  }}
                >
                  Esercizio {anno}
                </div>
                <div
                  style={{ color: stato?.stato === 'chiuso' ? COLORS.success : COLORS.info, marginTop: 4 }}
                >
                  {stato?.stato === 'chiuso' ? 'Chiuso' : 'Aperto'}
                  {stato?.data_chiusura && ` il ${formatDateIT(stato.data_chiusura)}`}
                </div>
              </div>
            </div>

            {stato?.risultato_esercizio !== undefined && (
              <StatCard
                icon={
                  stato.risultato_esercizio >= 0 ? (
                    <TrendingUp size={20} />
                  ) : (
                    <TrendingDown size={20} />
                  )
                }
                label="Risultato"
                value={formatEuro(stato.risultato_esercizio)}
                accent={stato.risultato_esercizio >= 0 ? 'success' : 'danger'}
                style={{ minWidth: 200 }}
              />
            )}
          </div>
        </div>

        {/* Steps Progress */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
            marginBottom: 32,
            padding: 20,
            background: COLORS.bgAlt,
            border: `1px solid ${COLORS.border}`,
            borderLeft: `4px solid ${COLORS.primary}`,
            borderRadius: BORDER_RADIUS.md,
          }}
        >
          <StepIndicator
            number={1}
            title="Verifica Preliminare"
            active={activeStep === 1}
            completed={activeStep > 1}
          />
          <ChevronRight size={20} color={COLORS.borderDark} />
          <StepIndicator
            number={2}
            title="Bilancino Verifica"
            active={activeStep === 2}
            completed={activeStep > 2}
          />
          <ChevronRight size={20} color={COLORS.borderDark} />
          <StepIndicator
            number={3}
            title="Chiusura"
            active={activeStep === 3}
            completed={activeStep > 3}
          />
          <ChevronRight size={20} color={COLORS.borderDark} />
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
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                padding: 24,
                boxShadow: SHADOWS.sm,
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
                  background: COLORS.bgAlt,
                  borderRadius: BORDER_RADIUS.md,
                  padding: 16,
                  marginBottom: 20,
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 8 }}>
                  Punteggio Completezza
                </div>
                <div
                  style={{
                    fontSize: 36,
                    fontWeight: 700,
                    fontFamily: MONO,
                    color:
                      verifica?.punteggio_completezza >= 80
                        ? COLORS.success
                        : verifica?.punteggio_completezza >= 50
                          ? COLORS.warning
                          : COLORS.danger,
                  }}
                >
                  {verifica?.punteggio_completezza || 0}%
                </div>
                <div
                  style={{
                    height: 8,
                    background: COLORS.border,
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
                          ? COLORS.success
                          : verifica?.punteggio_completezza >= 50
                            ? COLORS.warning
                            : COLORS.danger,
                      borderRadius: 4,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              </div>

              {/* Problemi Bloccanti */}
              {verifica?.problemi_bloccanti?.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: COLORS.danger, marginBottom: 12 }}>
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
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: COLORS.warning, marginBottom: 12 }}>
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
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: COLORS.success, marginBottom: 12 }}>
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
                        color: COLORS.success,
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
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                padding: 24,
                boxShadow: SHADOWS.sm,
                marginBottom: 24,
              }}
              data-testid="bilancino-section"
            >
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>
                Bilancino di Verifica {anno}
              </h3>

              {bilancino?.disponibile && bilancino?.bilancino ? (
                <>
                  {/* Ricavi */}
                  <div
                    style={{
                      background: COLORS.successLight,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 16,
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: COLORS.success, marginBottom: 12 }}>
                      RICAVI
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: COLORS.textMuted }}>Conti ricavo inclusi</span>
                      <span style={{ fontFamily: MONO }}>{bilancino.bilancino.ricavi.conti?.length || 0}</span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: `1px solid ${COLORS.success}`,
                        fontWeight: 600,
                      }}
                    >
                      <span>Totale Ricavi</span>
                      <span style={{ color: COLORS.success, fontFamily: MONO }}>
                        {formatEuro(bilancino.bilancino.ricavi.totale)}
                      </span>
                    </div>
                  </div>

                  {/* Costi */}
                  <div
                    style={{
                      background: COLORS.dangerLight,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 16,
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: COLORS.danger, marginBottom: 12 }}>COSTI</div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: COLORS.textMuted }}>Conti costo inclusi</span>
                      <span style={{ fontFamily: MONO }}>{bilancino.bilancino.costi.conti?.length || 0}</span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: COLORS.textMuted }}>Scritture registrate</span>
                      <span style={{ fontFamily: MONO }}>
                        {bilancino.registro?.completezza?.scritture_registrate || 0}
                      </span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: COLORS.textMuted }}>Documenti da registrare</span>
                      <span style={{ fontFamily: MONO }}>
                        {bilancino.registro?.completezza?.documenti_da_registrare || 0}
                      </span>
                    </div>
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}
                    >
                      <span style={{ color: COLORS.textMuted }}>Fonte</span>
                      <span style={{ fontFamily: MONO }}>Registro definitivo</span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: `1px solid ${COLORS.danger}`,
                        fontWeight: 600,
                      }}
                    >
                      <span>Totale Costi</span>
                      <span style={{ color: COLORS.danger, fontFamily: MONO }}>
                        {formatEuro(bilancino.bilancino.costi.totale)}
                      </span>
                    </div>
                  </div>

                  {/* Risultato */}
                  <div
                    style={{
                      background:
                        bilancino.bilancino.risultato.utile_perdita >= 0 ? COLORS.successLight : COLORS.dangerLight,
                      borderRadius: BORDER_RADIUS.md,
                      padding: 20,
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>RISULTATO D'ESERCIZIO</div>
                    <div
                      style={{
                        fontSize: 28,
                        fontWeight: 700,
                        fontFamily: MONO,
                        color:
                          bilancino.bilancino.risultato.utile_perdita >= 0 ? COLORS.success : COLORS.danger,
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
                        color: COLORS.textMuted,
                        marginTop: 8,
                      }}
                    >
                      {bilancino.bilancino.risultato.tipo.toUpperCase()}
                      {bilancino.bilancino.risultato.margine_percentuale !== null && (
                        <> • Margine: {bilancino.bilancino.risultato.margine_percentuale}%</>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div
                  style={{
                    background: COLORS.warningLight,
                    border: `1px solid ${COLORS.warning}`,
                    borderRadius: BORDER_RADIUS.md,
                    padding: 20,
                  }}
                  data-testid="bilancino-non-disponibile"
                >
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <AlertTriangle size={22} color={COLORS.warning} />
                    <div>
                      <div style={{ fontWeight: 700, color: COLORS.warning, marginBottom: 6 }}>
                        Bilancino non disponibile
                      </div>
                      <div style={{ color: COLORS.text, lineHeight: 1.5 }}>
                        {bilancino?.motivo || 'Il registro contabile non è ancora pronto per la chiusura.'}
                      </div>
                      <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 10 }}>
                        Scritture: {bilancino?.registro?.completezza?.scritture_registrate || 0} ·{' '}
                        Documenti da registrare:{' '}
                        {bilancino?.registro?.completezza?.documenti_da_registrare || 0} ·{' '}
                        Quadratura: {bilancino?.registro?.quadratura ? 'sì' : 'no'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Azioni */}
            {stato?.stato !== 'chiuso' && (
              <div
                style={{
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  border: `1px solid ${COLORS.border}`,
                  padding: 24,
                  boxShadow: SHADOWS.sm,
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
                      borderRadius: BORDER_RADIUS.sm,
                      border: `1px solid ${COLORS.border}`,
                      minHeight: 80,
                      resize: 'vertical',
                      fontFamily: FONT.family,
                    }}
                    data-testid="note-input"
                  />
                </div>

                <div
                  style={{
                    background: COLORS.dangerLight,
                    border: `1px solid ${COLORS.danger}`,
                    borderRadius: BORDER_RADIUS.md,
                    padding: 16,
                    marginBottom: 16,
                  }}
                >
                  <label
                    htmlFor="conferma-chiusura"
                    style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}
                  >
                    Per confermare le quadrature, digita <strong>CHIUDI {anno}</strong>
                  </label>
                  <input
                    id="conferma-chiusura"
                    value={confirmationText}
                    onChange={event => setConfirmationText(event.target.value)}
                    autoComplete="off"
                    placeholder={`CHIUDI ${anno}`}
                    style={{
                      width: '100%',
                      padding: 12,
                      borderRadius: BORDER_RADIUS.sm,
                      border: `1px solid ${COLORS.danger}`,
                      fontFamily: MONO,
                    }}
                    data-testid="conferma-chiusura-input"
                  />
                </div>

                <Button
                  variant="primary"
                  size="lg"
                  onClick={eseguiChiusura}
                  disabled={
                    !verifica?.pronto_per_chiusura ||
                    !bilancino?.disponibile ||
                    confirmationText !== `CHIUDI ${anno}` ||
                    executing
                  }
                  iconLeft={
                    executing ? (
                      <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <Lock size={20} />
                    )
                  }
                  style={{ width: '100%' }}
                  data-testid="chiudi-esercizio-button"
                >
                  {executing ? 'Elaborazione...' : `Chiudi Esercizio ${anno}`}
                </Button>

                {!verifica?.pronto_per_chiusura && (
                  <p
                    style={{
                      fontSize: 13,
                      color: COLORS.danger,
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
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  border: `1px solid ${COLORS.border}`,
                  padding: 24,
                  boxShadow: SHADOWS.sm,
                }}
                data-testid="apertura-section"
              >
                <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>
                  Apertura Nuovo Esercizio
                </h3>

                <p style={{ color: COLORS.textMuted, marginBottom: 16 }}>
                  L'esercizio {anno} è stato chiuso. Puoi ora aprire l'esercizio {anno + 1}
                  salvando uno snapshot dei saldi canonici, senza duplicare righe in Prima Nota.
                </p>

                <label
                  htmlFor="conferma-apertura"
                  style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}
                >
                  Digita <strong>APRI {anno + 1}</strong>
                </label>
                <input
                  id="conferma-apertura"
                  value={openingConfirmationText}
                  onChange={event => setOpeningConfirmationText(event.target.value)}
                  autoComplete="off"
                  placeholder={`APRI ${anno + 1}`}
                  style={{
                    width: '100%',
                    padding: 12,
                    borderRadius: BORDER_RADIUS.sm,
                    border: `1px solid ${COLORS.border}`,
                    fontFamily: MONO,
                    marginBottom: 16,
                  }}
                  data-testid="conferma-apertura-input"
                />

                <Button
                  variant="primary"
                  size="lg"
                  onClick={apriNuovoEsercizio}
                  disabled={openingConfirmationText !== `APRI ${anno + 1}` || executing}
                  iconLeft={
                    executing ? (
                      <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <Unlock size={20} />
                    )
                  }
                  style={{ width: '100%' }}
                  data-testid="apri-esercizio-button"
                >
                  {executing ? 'Elaborazione...' : `Apri Esercizio ${anno + 1}`}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Storico Chiusure */}
        {storico.length > 0 && (
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${COLORS.border}`,
              padding: 24,
              boxShadow: SHADOWS.sm,
              marginTop: 32,
            }}
            data-testid="storico-section"
          >
            <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Storico Chiusure</h3>

            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th align="left">Anno</Th>
                    <Th align="left">Data Chiusura</Th>
                    <Th align="right">Risultato</Th>
                    <Th align="left">Note</Th>
                  </tr>
                </thead>
                <tbody>
                  {storico.map((c, i) => (
                    <tr key={i}>
                      <Td style={{ fontWeight: 600 }}>{c.anno}</Td>
                      <Td style={{ color: COLORS.textMuted }}>{formatDateIT(c.created_at)}</Td>
                      <Td
                        align="right"
                        mono
                        style={{
                          fontWeight: 600,
                          color: c.risultato_esercizio >= 0 ? COLORS.success : COLORS.danger,
                        }}
                      >
                        {formatEuro(c.risultato_esercizio)}
                      </Td>
                      <Td style={{ color: COLORS.textMuted }}>{c.note || '-'}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
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
