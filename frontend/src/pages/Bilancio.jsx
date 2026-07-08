import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Button, Select, TableWrap, Table, Td } from '../components/ds';
import { FileText, Download, TrendingUp, TrendingDown, Scale } from 'lucide-react';

export default function Bilancio() {
  const { anno } = useAnnoGlobale();
  const [statoPatrimoniale, setStatoPatrimoniale] = useState(null);
  const [contoEconomico, setContoEconomico] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mese, setMese] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const match = location.pathname.match(/\/bilancio\/([\w-]+)/);
    return match ? match[1] : 'patrimoniale';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/bilancio/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);

  const mesi = [
    { value: null, label: 'Anno intero' },
    { value: 1, label: 'Gennaio' },
    { value: 2, label: 'Febbraio' },
    { value: 3, label: 'Marzo' },
    { value: 4, label: 'Aprile' },
    { value: 5, label: 'Maggio' },
    { value: 6, label: 'Giugno' },
    { value: 7, label: 'Luglio' },
    { value: 8, label: 'Agosto' },
    { value: 9, label: 'Settembre' },
    { value: 10, label: 'Ottobre' },
    { value: 11, label: 'Novembre' },
    { value: 12, label: 'Dicembre' },
  ];

  useEffect(() => {
    loadBilancio();
  }, [anno, mese]);

  const loadBilancio = async () => {
    try {
      setLoading(true);
      const [spRes, ceRes] = await Promise.all([
        api.get(`/api/bilancio/stato-patrimoniale?anno=${anno}${mese ? `&mese=${mese}` : ''}`),
        api.get(`/api/bilancio/conto-economico?anno=${anno}${mese ? `&mese=${mese}` : ''}`),
      ]);
      setStatoPatrimoniale(spRes.data);
      setContoEconomico(ceRes.data);
    } catch (error) {
      console.error('Errore caricamento bilancio:', error);
    } finally {
      setLoading(false);
    }
  };

  const StatoPatrimonialeView = () => {
    if (!statoPatrimoniale) return null;
    const { attivo, passivo } = statoPatrimoniale;
    return (
      <PageGrid cols={2} gap={24}>
        {/* ATTIVO */}
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 24,
          }}
        >
          <h3
            style={{
              color: COLORS.success,
              marginBottom: 20,
              borderBottom: `2px solid ${COLORS.success}`,
              paddingBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <TrendingUp size={20} /> ATTIVO
          </h3>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: COLORS.success, fontSize: 14, marginBottom: 12 }}>
              Disponibilità Liquide
            </h4>
            <TableWrap>
              <Table>
                <tbody>
                  <tr>
                    <Td style={{ color: COLORS.gray[700] }}>Cassa</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>
                      {formatEuro(attivo.disponibilita_liquide.cassa)}
                    </Td>
                  </tr>
                  <tr>
                    <Td style={{ color: COLORS.gray[700] }}>Banca</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>
                      {formatEuro(attivo.disponibilita_liquide.banca)}
                    </Td>
                  </tr>
                  <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <Td style={{ fontWeight: 600 }}>Totale</Td>
                    <Td align="right" mono style={{ fontWeight: 600 }}>
                      {formatEuro(attivo.disponibilita_liquide.totale)}
                    </Td>
                  </tr>
                </tbody>
              </Table>
            </TableWrap>
          </div>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: COLORS.success, fontSize: 14, marginBottom: 12 }}>Crediti</h4>
            <TableWrap>
              <Table>
                <tbody>
                  <tr>
                    <Td style={{ color: COLORS.gray[700] }}>Crediti vs Clienti</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>
                      {formatEuro(attivo.crediti.crediti_vs_clienti)}
                    </Td>
                  </tr>
                </tbody>
              </Table>
            </TableWrap>
          </div>
          <div
            style={{
              marginTop: 20,
              padding: 16,
              background: COLORS.primary,
              color: 'white',
              borderRadius: BORDER_RADIUS.md,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>TOTALE ATTIVO</span>
            <span style={{ fontSize: 24, fontWeight: 700, fontFamily: FONT.mono }}>
              {formatEuro(attivo.totale_attivo)}
            </span>
          </div>
        </div>

        {/* PASSIVO */}
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 24,
          }}
        >
          <h3
            style={{
              color: COLORS.danger,
              marginBottom: 20,
              borderBottom: `2px solid ${COLORS.danger}`,
              paddingBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <TrendingDown size={20} /> PASSIVO
          </h3>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: COLORS.danger, fontSize: 14, marginBottom: 12 }}>Debiti</h4>
            <TableWrap>
              <Table>
                <tbody>
                  <tr>
                    <Td style={{ color: COLORS.gray[700] }}>Debiti vs Fornitori</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>
                      {formatEuro(passivo.debiti.debiti_vs_fornitori)}
                    </Td>
                  </tr>
                </tbody>
              </Table>
            </TableWrap>
          </div>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: COLORS.success, fontSize: 14, marginBottom: 12 }}>
              Patrimonio Netto
            </h4>
            <TableWrap>
              <Table>
                <tbody>
                  <tr>
                    <Td style={{ color: COLORS.gray[700] }}>Capitale</Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: 600,
                        color: passivo.patrimonio_netto >= 0 ? COLORS.success : COLORS.danger,
                      }}
                    >
                      {formatEuro(passivo.patrimonio_netto)}
                    </Td>
                  </tr>
                </tbody>
              </Table>
            </TableWrap>
          </div>
          <div
            style={{
              marginTop: 20,
              padding: 16,
              background: COLORS.primary,
              color: 'white',
              borderRadius: BORDER_RADIUS.md,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>TOTALE PASSIVO</span>
            <span style={{ fontSize: 24, fontWeight: 700, fontFamily: FONT.mono }}>
              {formatEuro(passivo.totale_passivo)}
            </span>
          </div>
        </div>
      </PageGrid>
    );
  };

  const ContoEconomicoView = () => {
    if (!contoEconomico) return null;
    const { ricavi, costi, risultato } = contoEconomico;
    const isProfit = risultato.utile_perdita >= 0;
    return (
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        {/* RICAVI */}
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 24,
            marginBottom: 20,
          }}
        >
          <h3
            style={{
              color: COLORS.success,
              marginBottom: 20,
              borderBottom: `2px solid ${COLORS.success}`,
              paddingBottom: 10,
            }}
          >
            RICAVI (Vendite al Pubblico)
          </h3>
          <TableWrap>
            <Table>
              <tbody>
                <tr>
                  <Td style={{ color: COLORS.gray[700], fontSize: 15 }}>
                    Corrispettivi (Imponibile)
                  </Td>
                  <Td align="right" mono style={{ fontWeight: 500, fontSize: 16 }}>
                    {formatEuro(ricavi.corrispettivi)}
                  </Td>
                </tr>
                {ricavi.corrispettivi_lordi > 0 && (
                  <tr>
                    <Td style={{ color: COLORS.textMuted, fontSize: 13, fontStyle: 'italic' }}>
                      (Lordo incl. IVA: {formatEuro(ricavi.corrispettivi_lordi)})
                    </Td>
                    <Td></Td>
                  </tr>
                )}
                <tr style={{ borderTop: `2px solid ${COLORS.success}`, background: COLORS.successLight }}>
                  <Td style={{ fontWeight: 700, fontSize: 16 }}>TOTALE RICAVI</Td>
                  <Td
                    align="right"
                    mono
                    style={{ fontWeight: 700, fontSize: 18, color: COLORS.success }}
                  >
                    {formatEuro(ricavi.totale_ricavi)}
                  </Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
        </div>

        {/* COSTI */}
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 24,
            marginBottom: 20,
          }}
        >
          <h3
            style={{
              color: COLORS.danger,
              marginBottom: 20,
              borderBottom: `2px solid ${COLORS.danger}`,
              paddingBottom: 10,
            }}
          >
            COSTI (Fatture Ricevute da Fornitori)
          </h3>
          <TableWrap>
            <Table>
              <tbody>
                <tr>
                  <Td style={{ color: COLORS.gray[700], fontSize: 15 }}>Acquisti (Imponibile)</Td>
                  <Td align="right" mono style={{ fontWeight: 500, fontSize: 16 }}>
                    {formatEuro(costi.acquisti)}
                  </Td>
                </tr>
                {costi.note_credito > 0 && (
                  <tr>
                    <Td style={{ color: COLORS.success, fontSize: 15 }}>
                      - Note di Credito Ricevute
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{ fontWeight: 500, fontSize: 16, color: COLORS.success }}
                    >
                      -{formatEuro(costi.note_credito)}
                    </Td>
                  </tr>
                )}
                <tr style={{ borderTop: `2px solid ${COLORS.danger}`, background: COLORS.dangerLight }}>
                  <Td style={{ fontWeight: 700, fontSize: 16 }}>TOTALE COSTI (Netto)</Td>
                  <Td
                    align="right"
                    mono
                    style={{ fontWeight: 700, fontSize: 18, color: COLORS.danger }}
                  >
                    {formatEuro(costi.totale_costi)}
                  </Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
        </div>

        {/* RISULTATO */}
        <div
          style={{
            background: isProfit ? COLORS.success : COLORS.danger,
            borderRadius: BORDER_RADIUS.md,
            padding: 32,
            color: 'white',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              fontSize: 12,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              opacity: 0.9,
              marginBottom: 8,
            }}
          >
            {isProfit ? 'UTILE DI ESERCIZIO' : 'PERDITA DI ESERCIZIO'}
          </div>
          <div style={{ fontSize: 'clamp(28px, 6vw, 40px)', fontWeight: 700, fontFamily: FONT.mono }}>
            {formatEuro(Math.abs(risultato.utile_perdita))}
          </div>
          <div
            style={{
              marginTop: 16,
              padding: '8px 16px',
              background: 'rgba(255,255,255,0.2)',
              borderRadius: BORDER_RADIUS.sm,
              display: 'inline-block',
              fontSize: 13,
            }}
          >
            Margine: {risultato.margine_percentuale}%
          </div>
        </div>
      </div>
    );
  };

  return (
    <PageLayout
      title="Bilancio"
      icon={<Scale size={28} />}
      subtitle={`Stato Patrimoniale e Conto Economico - Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select
            value={mese || ''}
            onChange={e => setMese(e.target.value ? parseInt(e.target.value) : null)}
            data-testid="bilancio-mese-select"
            style={{ minHeight: 40 }}
          >
            {mesi.map(m => (
              <option key={m.label} value={m.value || ''}>
                {m.label}
              </option>
            ))}
          </Select>
          <Button
            variant="primary"
            size="lg"
            iconLeft={<Download size={16} />}
            onClick={() =>
              window.open(`${api.defaults.baseURL}/api/bilancio/export-pdf?anno=${anno}`, '_blank')
            }
            data-testid="export-pdf-btn"
            style={{ minHeight: 40 }}
          >
            PDF {anno}
          </Button>
          <Button
            variant="outline"
            size="lg"
            iconLeft={<FileText size={16} />}
            onClick={() =>
              window.open(
                `${api.defaults.baseURL}/api/bilancio/export/pdf/confronto?anno_corrente=${anno}&anno_precedente=${anno - 1}`,
                '_blank'
              )
            }
            data-testid="export-confronto-pdf-btn"
            style={{ minHeight: 40 }}
          >
            Confronto {anno - 1}/{anno}
          </Button>
        </div>
      }
    >
      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          marginBottom: 24,
          borderBottom: `2px solid ${COLORS.border}`,
          flexWrap: 'wrap',
        }}
      >
        <Button
          variant={activeTab === 'patrimoniale' ? 'primary' : 'ghost'}
          onClick={() => handleTabChange('patrimoniale')}
          data-testid="tab-stato-patrimoniale"
          style={{
            minHeight: 40,
            borderRadius: `${BORDER_RADIUS.sm}px ${BORDER_RADIUS.sm}px 0 0`,
            border: 'none',
          }}
        >
          Stato Patrimoniale
        </Button>
        <Button
          variant={activeTab === 'economico' ? 'primary' : 'ghost'}
          onClick={() => handleTabChange('economico')}
          data-testid="tab-conto-economico"
          style={{
            minHeight: 40,
            borderRadius: `${BORDER_RADIUS.sm}px ${BORDER_RADIUS.sm}px 0 0`,
            border: 'none',
          }}
        >
          Conto Economico
        </Button>
      </div>

      {loading ? (
        <PageLoading message="Caricamento bilancio..." />
      ) : (
        <>
          {activeTab === 'patrimoniale' && <StatoPatrimonialeView />}
          {activeTab === 'economico' && <ContoEconomicoView />}
        </>
      )}

      {/* Info */}
      <PageSection title="Note" icon="ℹ️" style={{ marginTop: 30 }}>
        <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted }}>
          I dati sono calcolati in base ai movimenti registrati in Prima Nota e alle fatture
          caricate. Lo Stato Patrimoniale mostra la situazione alla data selezionata, il Conto
          Economico mostra i flussi del periodo.
        </p>
      </PageSection>
    </PageLayout>
  );
}
