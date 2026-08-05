import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Button, Select, TableWrap, Table, Th, Td, Input } from '../components/ds';
import { FileText, Download, TrendingUp, TrendingDown, Scale, Trash2, Plus } from 'lucide-react';
import { toast } from 'sonner';

export default function Bilancio() {
  const { anno } = useAnnoGlobale();
  const [statoPatrimoniale, setStatoPatrimoniale] = useState(null);
  const [contoEconomico, setContoEconomico] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mese, setMese] = useState(null);
  const [vociBilancio, setVociBilancio] = useState(null);
  const [codiciDisponibili, setCodiciDisponibili] = useState([]);
  const [nuovaVoce, setNuovaVoce] = useState({ codice_cee: '', importo: '', note: '' });
  const [rateoAmmortamenti, setRateoAmmortamenti] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const match = location.pathname.match(/\/contabilita\/bilancio\/([\w-]+)/);
    return match ? match[1] : 'patrimoniale';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/contabilita/bilancio/${tabId}`);
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
    loadVociBilancio();
    loadRateoAmmortamenti();
  }, [anno, mese]);

  const loadRateoAmmortamenti = async () => {
    if (!mese) {
      setRateoAmmortamenti(null); // bilancio annuo pieno: il rateo mensile non si applica
      return;
    }
    try {
      const r = await api.get(`/api/cespiti/calcolo-rateo/${anno}/${mese}`);
      setRateoAmmortamenti(r.data);
    } catch (error) {
      console.error('Errore caricamento rateo ammortamenti:', error);
      setRateoAmmortamenti(null);
    }
  };

  useEffect(() => {
    api.get('/api/voci-bilancio/codici-disponibili').then(r => setCodiciDisponibili(r.data.codici)).catch(() => {});
  }, []);

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

  const loadVociBilancio = async () => {
    try {
      const r = await api.get(`/api/voci-bilancio/${anno}`);
      setVociBilancio(r.data);
    } catch (error) {
      console.error('Errore caricamento voci bilancio manuali:', error);
    }
  };

  const handleSalvaVoce = async () => {
    const importo = parseFloat(nuovaVoce.importo);
    if (!nuovaVoce.codice_cee || Number.isNaN(importo)) {
      toast.warning('Seleziona un codice e inserisci un importo valido');
      return;
    }
    try {
      await api.post('/api/voci-bilancio/', {
        codice_cee: nuovaVoce.codice_cee,
        importo,
        anno,
        note: nuovaVoce.note || null,
      });
      setNuovaVoce({ codice_cee: '', importo: '', note: '' });
      loadVociBilancio();
      loadBilancio();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleEliminaVoce = async voceId => {
    try {
      await api.delete(`/api/voci-bilancio/${voceId}`);
      loadVociBilancio();
      loadBilancio();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  // §6.2: riclassificazione sui CODICI UFFICIALI del piano dei conti (CEE del bilancio).
  const renderVociUfficiali = (vociUfficiali, titolo) => {
    if (!vociUfficiali) return null;
    const gruppi = Object.entries(vociUfficiali).filter(([, righe]) => Array.isArray(righe) && righe.length);
    if (!gruppi.length) return null;
    return (
      <details style={{ marginTop: 20 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, color: COLORS.textMuted }}>
          📓 Piano dei conti ufficiale (CEE) — {titolo}
        </summary>
        <div style={{ marginTop: 12, overflowX: 'auto' }}>
          {gruppi.map(([gruppo, righe]) => (
            <div key={gruppo} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, textTransform: 'uppercase', color: COLORS.textMuted, marginBottom: 4 }}>
                {gruppo.replace('_', ' ')}
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <tbody>
                  {righe.map((r, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                      <td style={{ padding: '4px 8px', fontFamily: FONT.mono, whiteSpace: 'nowrap' }}>{r.codice}</td>
                      <td style={{ padding: '4px 8px' }}>{r.descrizione}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: FONT.mono }}>{formatEuro(r.saldo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </details>
    );
  };

  const StatoPatrimonialeView = () => {
    if (!statoPatrimoniale) return null;
    const { attivo, passivo } = statoPatrimoniale;
    return (
      <>
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
          {attivo.immobilizzazioni && attivo.immobilizzazioni.totale > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: COLORS.success, fontSize: 14, marginBottom: 12 }}>
                Immobilizzazioni
              </h4>
              <TableWrap>
                <Table>
                  <tbody>
                    {attivo.immobilizzazioni.da_cespiti > 0 && (
                      <tr>
                        <Td style={{ color: COLORS.gray[700] }}>Da cespiti (Cespiti &amp; TFR)</Td>
                        <Td align="right" mono style={{ fontWeight: 500 }}>
                          {formatEuro(attivo.immobilizzazioni.da_cespiti)}
                        </Td>
                      </tr>
                    )}
                    {attivo.immobilizzazioni.da_voci_manuali > 0 && (
                      <tr>
                        <Td style={{ color: COLORS.gray[700] }}>Da voci inserite a mano</Td>
                        <Td align="right" mono style={{ fontWeight: 500 }}>
                          {formatEuro(attivo.immobilizzazioni.da_voci_manuali)}
                        </Td>
                      </tr>
                    )}
                    <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                      <Td style={{ fontWeight: 600 }}>Totale</Td>
                      <Td align="right" mono style={{ fontWeight: 600 }}>
                        {formatEuro(attivo.immobilizzazioni.totale)}
                      </Td>
                    </tr>
                  </tbody>
                </Table>
              </TableWrap>
            </div>
          )}
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
                  {passivo.fondo_tfr > 0 && (
                    <tr>
                      <Td style={{ color: COLORS.gray[700] }}>Fondo TFR</Td>
                      <Td align="right" mono style={{ fontWeight: 500 }}>
                        {formatEuro(passivo.fondo_tfr)}
                      </Td>
                    </tr>
                  )}
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
                    <Td style={{ color: COLORS.gray[700] }}>Capitale (calcolato per differenza)</Td>
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
                  {passivo.patrimonio_netto_dettaglio_manuale > 0 && (
                    <tr>
                      <Td style={{ color: COLORS.textMuted, fontSize: 12, fontStyle: 'italic' }}>
                        di cui da voci inserite a mano (capitale/riserve)
                      </Td>
                      <Td align="right" mono style={{ fontSize: 12, color: COLORS.textMuted }}>
                        {formatEuro(passivo.patrimonio_netto_dettaglio_manuale)}
                      </Td>
                    </tr>
                  )}
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
      {mese && rateoAmmortamenti && rateoAmmortamenti.num_cespiti > 0 && (
        <PageSection title="Ammortamenti a rateo (bilancio provvisorio)" icon="📐" style={{ marginTop: 24 }}>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: COLORS.textMuted }}>
            Rateo lineare da inizio anno (quota annuale ordinaria / 12 × mesi trascorsi):
            l'ammortamento maturato dai cespiti fino a {mesi.find(m => m.value === mese)?.label} {anno}, per
            imputarlo a un bilancio infra-annuale. Solo informativo: non modifica il registro
            cespiti né lo Stato Patrimoniale sopra — l'ammortamento definitivo resta quello
            registrato a fine anno in Cespiti &amp; TFR.
          </p>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Cespite</Th>
                  <Th align="right">Quota annua ordinaria</Th>
                  <Th align="right">Rateo al mese {mese}</Th>
                </tr>
              </thead>
              <tbody>
                {rateoAmmortamenti.cespiti.map(c => (
                  <tr key={c.cespite_id}>
                    <Td>{c.descrizione}</Td>
                    <Td align="right" mono>{formatEuro(c.quota_annua_ordinaria)}</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>{formatEuro(c.rateo_al_mese)}</Td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                  <Td style={{ fontWeight: 600 }}>Totale rateo</Td>
                  <Td></Td>
                  <Td align="right" mono style={{ fontWeight: 600 }}>{formatEuro(rateoAmmortamenti.totale_rateo)}</Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
        </PageSection>
      )}
      <PageSection title="Voci di bilancio inserite manualmente" icon="✍️" style={{ marginTop: 24 }}>
        <p style={{ margin: '0 0 12px', fontSize: 13, color: COLORS.textMuted }}>
          Capitale sociale, riserve, saldi di apertura o altre immobilizzazioni che il
          sistema non deriva da prima nota/fatture/cedolini — codici del piano dei conti
          CEE ufficiale, riferiti all'anno {anno}.
        </p>
        {vociBilancio && vociBilancio.voci.length > 0 && (
          <TableWrap style={{ marginBottom: 16 }}>
            <Table>
              <thead>
                <tr>
                  <Th>Codice CEE</Th>
                  <Th>Descrizione</Th>
                  <Th>Note</Th>
                  <Th align="right">Importo</Th>
                  <Th></Th>
                </tr>
              </thead>
              <tbody>
                {vociBilancio.voci.map(v => (
                  <tr key={v.id}>
                    <Td mono>{v.codice_cee}</Td>
                    <Td>{v.descrizione}</Td>
                    <Td style={{ color: COLORS.textMuted, fontSize: 12 }}>{v.note || '-'}</Td>
                    <Td align="right" mono style={{ fontWeight: 500 }}>{formatEuro(v.importo)}</Td>
                    <Td align="right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEliminaVoce(v.id)}
                        data-testid={`elimina-voce-bilancio-${v.id}`}
                      >
                        <Trash2 size={14} color={COLORS.danger} />
                      </Button>
                    </Td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                  <Td colSpan={3} style={{ fontWeight: 600 }}>
                    Totale — immobilizzazioni {formatEuro(vociBilancio.totale_immobilizzazioni)},
                    capitale e riserve {formatEuro(vociBilancio.totale_patrimonio_netto)}
                  </Td>
                  <Td align="right" mono style={{ fontWeight: 600 }}>
                    {formatEuro(vociBilancio.totale_immobilizzazioni + vociBilancio.totale_patrimonio_netto)}
                  </Td>
                  <Td></Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Select
            value={nuovaVoce.codice_cee}
            onChange={e => setNuovaVoce({ ...nuovaVoce, codice_cee: e.target.value })}
            data-testid="nuova-voce-codice-select"
            style={{ minWidth: 260 }}
          >
            <option value="">Seleziona voce...</option>
            {[...new Set(codiciDisponibili.map(c => c.macro))].map(macro => (
              <optgroup
                key={macro}
                label={codiciDisponibili.find(c => c.codice_cee === macro)?.descrizione || macro}
              >
                {codiciDisponibili
                  .filter(c => c.macro === macro)
                  .map(c => (
                    <option key={c.codice_cee} value={c.codice_cee}>
                      {c.codice_cee} — {c.descrizione}
                      {c.codice_cee === macro ? ' (totale gruppo)' : ''}
                    </option>
                  ))}
              </optgroup>
            ))}
          </Select>
          <Input
            type="number"
            placeholder="Importo"
            value={nuovaVoce.importo}
            onChange={e => setNuovaVoce({ ...nuovaVoce, importo: e.target.value })}
            style={{ width: 140 }}
            data-testid="nuova-voce-importo-input"
          />
          <Input
            placeholder="Note (opzionale)"
            value={nuovaVoce.note}
            onChange={e => setNuovaVoce({ ...nuovaVoce, note: e.target.value })}
            style={{ width: 220 }}
          />
          <Button
            variant="primary"
            size="sm"
            iconLeft={<Plus size={14} />}
            onClick={handleSalvaVoce}
            data-testid="salva-voce-bilancio-btn"
          >
            Salva
          </Button>
        </div>
      </PageSection>
      {renderVociUfficiali(statoPatrimoniale.voci_ufficiali, 'Stato Patrimoniale')}
      </>
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
        {renderVociUfficiali(contoEconomico.voci_ufficiali, 'Conto Economico')}
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
              window.open(
                `${api.defaults.baseURL}/api/bilancio/export-pdf?anno=${anno}${mese ? `&mese=${mese}` : ''}`,
                '_blank'
              )
            }
            data-testid="export-pdf-btn"
            style={{ minHeight: 40 }}
          >
            PDF {mese ? `${anno}/${String(mese).padStart(2, '0')}` : anno}
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
