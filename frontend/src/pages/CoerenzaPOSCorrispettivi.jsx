/**
 * CoerenzaPOSCorrispettivi.jsx
 *
 * Verifica coerenza tra pagamenti elettronici (POS) e corrispettivi XML
 * Normativa 2026: obbligo abbinamento RT-POS
 */
import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  useIsMobile,
  RG,
  pagePad,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Button, Badge, StatCard, Tabs, Input, TableWrap, Table, Th, Td } from '../components/ds';
import {
  CreditCard,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  TrendingUp,
  Calendar,
  FileWarning,
  X,
} from 'lucide-react';

export function formatEuroConSegno(amount) {
  const valore = Number(amount || 0);
  const segno = valore > 0 ? '+' : valore < 0 ? '-' : '';
  const assoluto = new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(Math.abs(valore));
  return `€ ${segno}${assoluto}`;
}

export function BadgeRiconciliatoBanca({ riconciliato }) {
  return riconciliato
    ? <Badge variant="success">✓ Riconciliato banca</Badge>
    : null;
}

export default function CoerenzaPOSCorrispettivi() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [dati, setDati] = useState(null);
  const [riepilogoMensile, setRiepilogoMensile] = useState(null);
  // Nuova logica v2: controllo a 2 fasi (aprile 2026)
  const [dueFasi, setDueFasi] = useState(null);
  const [alertOggi, setAlertOggi] = useState(null);
  const [tab, setTab] = useState('due_fasi');  // nuovo tab default
  const [err, setErr] = useState('');

  useEffect(() => {
    loadDati();
  }, [anno]);

  const loadDati = async () => {
    setLoading(true);
    setErr('');
    try {
      const [coerenzaRes, mensileRes, dueFasiRes, alertRes] = await Promise.all([
        api.get(`/api/pos-corrispettivi/verifica-coerenza?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/riepilogo-mensile?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/controllo-due-fasi?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/alert-oggi`),
      ]);
      setDati(coerenzaRes.data);
      setRiepilogoMensile(mensileRes.data);
      setDueFasi(dueFasiRes.data);
      setAlertOggi(alertRes.data);
    } catch (e) {
      setErr('Errore caricamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const handleRiconcilia = async data => {
    try {
      const res = await api.post(`/api/pos-corrispettivi/riconcilia-pos-giorno?data=${data}`);
      toast.success(res.data.message);
      loadDati();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const getStatoIcon = stato => {
    switch (stato) {
      case 'ok':
        return <CheckCircle size={16} color={COLORS.success} />;
      case 'mancante':
        return <XCircle size={16} color={COLORS.danger} />;
      case 'differenza':
        return <AlertTriangle size={16} color={COLORS.warning} />;
      case 'extra':
        return <FileWarning size={16} color={COLORS.purple} />;
      default:
        return null;
    }
  };

  const statoBadgeVariant = stato =>
    ({
      ok: 'success',
      mancante: 'danger',
      differenza: 'warning',
      extra: 'accent',
      warning: 'warning',
      error: 'danger',
    })[stato] || 'neutral';

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <RefreshCw size={32} style={{ animation: 'spin 1s linear infinite', color: COLORS.info }} />
        <p style={{ marginTop: 12, color: COLORS.textMuted }}>Analisi coerenza POS/Corrispettivi...</p>
      </div>
    );
  }

  if (err) {
    return (
      <div
        style={{
          padding: 20,
          background: COLORS.dangerLight,
          borderRadius: BORDER_RADIUS.md,
          color: COLORS.danger,
        }}
      >
        {err}
        <Button variant="danger" size="sm" onClick={loadDati} style={{ marginLeft: 12 }}>
          Riprova
        </Button>
      </div>
    );
  }

  const statsPos = dueFasi?.statistiche || {};
  const gruppiPosVerificati = (statsPos.fase2_ok || 0)
    + (statsPos.fase2_mancante || 0)
    + (statsPos.fase2_diff || 0)
    + (statsPos.fase2_extra || 0);
  const percentualeQuadrata = gruppiPosVerificati > 0
    ? Math.round(((statsPos.fase2_ok || 0) / gruppiPosVerificati) * 1000) / 10
    : 0;

  return (
    <div style={{ padding: 20 }} data-testid="coerenza-pos-page">
      {/* KPI Summary - Compatto */}
      {dueFasi?.statistiche && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
            gap: 12,
            marginBottom: 20,
          }}
        >
          <StatCard
            icon={<CheckCircle size={18} />}
            label="Quadrature POS-Banca"
            value={`${percentualeQuadrata}%`}
            accent="success"
          />
          <StatCard
            icon={<CreditCard size={18} />}
            label="POS terminale inserito"
            value={formatEuro(statsPos.fase2_pos_totale || 0)}
            accent="info"
          />
          <StatCard
            icon={<TrendingUp size={18} />}
            label="Accrediti bancari reali"
            value={formatEuro(statsPos.fase2_accrediti_totale || 0)}
            accent="accent"
          />
          <StatCard
            icon={<AlertTriangle size={18} />}
            label="Saldo da verificare"
            value={formatEuro(statsPos.fase2_saldo_finale || 0)}
            accent={Math.abs(statsPos.fase2_saldo_finale || 0) > 0.01 ? 'danger' : 'success'}
          />
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <Tabs
          items={[
            {
              key: 'due_fasi',
              label: (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  ⚡ Controllo 2 Fasi
                  {alertOggi && (alertOggi.num_alert_compensazione + alertOggi.num_alert_banca) > 0 && (
                    <Badge variant="danger" style={{ padding: '1px 7px' }}>
                      {alertOggi.num_alert_compensazione + alertOggi.num_alert_banca}
                    </Badge>
                  )}
                </span>
              ),
            },
            { key: 'giornaliero', label: 'Giornaliero', icon: <Calendar size={14} /> },
            { key: 'mensile', label: 'Mensile', icon: <TrendingUp size={14} /> },
            {
              key: 'anomalie',
              label: `Anomalie (${dati?.anomalie_count || 0})`,
              icon: <AlertTriangle size={14} />,
            },
          ]}
          value={tab}
          onChange={setTab}
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={loadDati}
          iconLeft={<RefreshCw size={14} />}
          style={{ marginLeft: 'auto' }}
        >
          Aggiorna
        </Button>
      </div>

      {/* Tab nuovo: Controllo 2 Fasi (logica 2026) */}
      {tab === 'due_fasi' && dueFasi && (
        <ControlloDueFasi
          dati={dueFasi}
          alertOggi={alertOggi}
          isMobile={isMobile}
          onReload={loadDati}
        />
      )}

      {/* Tab Giornaliero */}
      {tab === 'giornaliero' && dati?.riepilogo_giornaliero && (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>DATA</Th>
                <Th align="right">ELETTR. XML</Th>
                <Th align="right">POS BANCA</Th>
                <Th align="right">DIFF.</Th>
                <Th align="center">STATO</Th>
              </tr>
            </thead>
            <tbody>
              {dati.riepilogo_giornaliero
                .slice()
                .reverse()
                .map((g, i) => (
                  <tr key={g.data} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }}>
                    <Td>
                      <span style={{ fontWeight: 600 }}>{formatDateIT(g.data)}</span>
                      <span style={{ marginLeft: 8, fontSize: 11, color: COLORS.textSubtle }}>
                        {g.giorno_settimana}
                      </span>
                    </Td>
                    <Td align="right" style={{ color: COLORS.info }}>
                      {formatEuro(g.elettronico_xml)}
                    </Td>
                    <Td align="right" style={{ color: COLORS.purple }}>
                      {formatEuro(g.pos_accreditato)}
                    </Td>
                    <Td
                      align="right"
                      style={{
                        fontWeight: 600,
                        color:
                          g.differenza > 10
                            ? COLORS.danger
                            : g.differenza < -10
                              ? COLORS.info
                              : COLORS.success,
                      }}
                    >
                      {g.differenza > 0 ? '+' : ''}
                      {formatEuro(g.differenza)}
                    </Td>
                    <Td align="center">
                      <Badge
                        variant={statoBadgeVariant(g.stato)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                      >
                        {getStatoIcon(g.stato)} {g.stato}
                      </Badge>
                    </Td>
                  </tr>
                ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {/* Tab Mensile */}
      {tab === 'mensile' && riepilogoMensile?.mesi && (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>MESE</Th>
                <Th align="right">CORRISPETTIVI</Th>
                <Th align="right">CONTANTI</Th>
                <Th align="right">ELETTR. XML</Th>
                <Th align="right">POS BANCA</Th>
                <Th align="right">DIFF.</Th>
                <Th align="center">STATO</Th>
              </tr>
            </thead>
            <tbody>
              {riepilogoMensile.mesi.map(m => (
                <tr key={m.mese} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }}>
                  <Td style={{ fontWeight: 600 }}>
                    {m.nome} {anno}
                  </Td>
                  <Td align="right">{formatEuro(m.totale_corrispettivi)}</Td>
                  <Td align="right" style={{ color: COLORS.success }}>
                    {formatEuro(m.contanti)}
                  </Td>
                  <Td align="right" style={{ color: COLORS.info }}>
                    {formatEuro(m.elettronico_xml)}
                  </Td>
                  <Td align="right" style={{ color: COLORS.purple }}>
                    {formatEuro(m.pos_accreditato)}
                  </Td>
                  <Td
                    align="right"
                    style={{
                      fontWeight: 600,
                      color: Math.abs(m.differenza) > 50 ? COLORS.danger : COLORS.success,
                    }}
                  >
                    {m.differenza > 0 ? '+' : ''}
                    {formatEuro(m.differenza)}
                  </Td>
                  <Td align="center">
                    <Badge variant={statoBadgeVariant(m.stato)}>{m.stato}</Badge>
                  </Td>
                </tr>
              ))}
              {/* Totale */}
              <tr style={{ background: COLORS.bgAlt, fontWeight: 700 }}>
                <Td style={{ fontWeight: 700 }}>TOTALE {anno}</Td>
                <Td align="right">-</Td>
                <Td align="right">-</Td>
                <Td align="right" style={{ color: COLORS.info, fontWeight: 700 }}>
                  {formatEuro(riepilogoMensile.totali.elettronico_xml)}
                </Td>
                <Td align="right" style={{ color: COLORS.purple, fontWeight: 700 }}>
                  {formatEuro(riepilogoMensile.totali.pos_accreditato)}
                </Td>
                <Td
                  align="right"
                  style={{
                    fontWeight: 700,
                    color:
                      Math.abs(riepilogoMensile.totali.differenza) > 100 ? COLORS.danger : COLORS.success,
                  }}
                >
                  {riepilogoMensile.totali.differenza > 0 ? '+' : ''}
                  {formatEuro(riepilogoMensile.totali.differenza)}
                </Td>
                <Td />
              </tr>
            </tbody>
          </Table>
        </TableWrap>
      )}

      {/* Tab Anomalie */}
      {tab === 'anomalie' && (
        <div>
          {dati?.anomalie?.length === 0 ? (
            <div
              style={{
                padding: 40,
                textAlign: 'center',
                background: COLORS.successLight,
                borderRadius: BORDER_RADIUS.lg,
              }}
            >
              <CheckCircle size={48} color={COLORS.success} />
              <p style={{ marginTop: 12, color: COLORS.success, fontWeight: 600 }}>
                Nessuna anomalia rilevata
              </p>
              <p style={{ fontSize: 13, color: COLORS.textMuted }}>
                I dati POS e corrispettivi XML sono coerenti
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {dati.anomalie.map((a, i) => (
                <div
                  key={a.data}
                  style={{
                    background: COLORS.card,
                    borderRadius: BORDER_RADIUS.lg,
                    border: `1px solid ${COLORS.dangerLight}`,
                    padding: 16,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                  }}
                >
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: BORDER_RADIUS.md,
                      background: COLORS.dangerLight,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {getStatoIcon(a.stato)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>
                      {formatDateIT(a.data)}{' '}
                      <span style={{ fontSize: 12, color: COLORS.textSubtle }}>({a.giorno_settimana})</span>
                    </div>
                    <div style={{ fontSize: 13, color: COLORS.textMuted }}>{a.messaggio}</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      <span style={{ color: COLORS.info }}>XML: {formatEuro(a.elettronico_xml)}</span>
                      <span style={{ margin: '0 8px', color: COLORS.textSubtle }}>|</span>
                      <span style={{ color: COLORS.purple }}>POS: {formatEuro(a.pos_accreditato)}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: COLORS.danger,
                        marginBottom: 4,
                      }}
                    >
                      {formatEuro(a.differenza)}
                    </div>
                    <Button variant="info" size="sm" onClick={() => handleRiconcilia(a.data)}>
                      Riconcilia
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Nota normativa */}
      <div
        style={{
          marginTop: 16,
          padding: 12,
          background: COLORS.warningLight,
          borderRadius: BORDER_RADIUS.md,
          fontSize: 12,
          color: COLORS.warning,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
        }}
      >
        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Normativa 2026:</strong> Dal 1° gennaio 2026 è obbligatorio collegare RT e POS.
          Eventuali discrepanze tra corrispettivi e transazioni POS possono generare avvisi
          dall'Agenzia delle Entrate. Accredito POS: Lun-Gio +1g lavorativo, Ven-Dom → Lunedì.
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// COMPONENTE: Controllo Incassi a 2 Fasi (v2 - aprile 2026)
// ═══════════════════════════════════════════════════════════════════════════
//
// Visualizza giorno per giorno:
//   - FASE 1: RT (XML) vs POS reale → errori di battitura + alert compensazione
//   - FASE 2: POS reale vs accredito banca → verifica accrediti
//
// Basato sulla specifica utente (spiegazione_coerenza.xlsx).
// ═══════════════════════════════════════════════════════════════════════════
function ControlloDueFasi({ dati, alertOggi, isMobile, onReload }) {
  const stats = dati?.statistiche || {};
  const giorni = dati?.giorni || [];
  const riepilogoSettimanale = dati?.riepilogo_settimanale || [];

  const [filtroStato, setFiltroStato] = useState('tutti'); // tutti | problemi | ok
  const [modalAperta, setModalAperta] = useState(false);
  const [importAperto, setImportAperto] = useState(false);
  const [vista, setVista] = useState('giornaliero'); // giornaliero | settimanale

  const giorniFiltrati = giorni.filter(g => {
    if (filtroStato === 'tutti') return true;
    if (filtroStato === 'ok') {
      return g.stato_serale === 'ok' && g.stato_accredito === 'ok' && g.stato_corrispettivo !== 'manca_xml';
    }
    // problemi: almeno una fase con problemi
    return (g.stato_serale !== 'ok' && g.stato_serale !== 'no_dati' && g.stato_serale !== 'in_attesa_xml') ||
           (g.stato_accredito !== 'ok' && g.stato_accredito !== 'in_attesa' && g.stato_accredito !== 'no_pos_manuale') ||
           g.stato_corrispettivo === 'manca_xml';
  });

  return (
    <div>
      {/* Toolbar con bottone inserimento manuale */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'center' }}>
        <Button
          variant="primary"
          onClick={() => setModalAperta(true)}
          style={{ background: COLORS.accent, borderColor: COLORS.accent }}
        >
          + Inserisci chiusura serale
        </Button>
        <Button
          variant="secondary"
          onClick={() => setImportAperto(true)}
          aria-label="Importa totali POS"
        >
          Importa totali POS
        </Button>
        <div style={{ fontSize: 12, color: COLORS.textMuted }}>
          Il POS del terminale si inserisce anche direttamente nella tabella. Salva in
          Prima Nota Cassa e crea il trasferimento atteso in Banca; l'XML resta solo confronto fiscale.
          La differenza è XML − POS: positiva significa che gli scontrini coprono i pagamenti con carta.
        </div>
      </div>

      {modalAperta && (
        <ModalChiusuraSerale
          onClose={() => setModalAperta(false)}
          onSaved={() => {
            setModalAperta(false);
            if (onReload) onReload();
          }}
        />
      )}

      {importAperto && (
        <ModalImportTotaliPos
          onClose={() => setImportAperto(false)}
          onSaved={() => {
            setImportAperto(false);
            if (onReload) onReload();
          }}
        />
      )}

      {/* Sezione Alert Oggi */}
      {alertOggi && (alertOggi.num_alert_compensazione + alertOggi.num_alert_banca + (alertOggi.num_alert_xml_mancante || 0)) > 0 && (
        <div style={{
          background: COLORS.warningLight,
          border: `2px solid ${COLORS.warning}`,
          borderRadius: BORDER_RADIUS.lg,
          padding: 16,
          marginBottom: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <AlertTriangle size={20} color={COLORS.warning} />
            <strong style={{ fontSize: 15, color: COLORS.warning }}>
              Cose da sistemare oggi
            </strong>
          </div>

          {alertOggi.alert_compensazione?.map((a, i) => (
            <div key={`comp-${i}`} style={{
              background: COLORS.card,
              padding: 10,
              marginBottom: 6,
              borderRadius: BORDER_RADIUS.sm,
              borderLeft: `4px solid ${COLORS.warning}`,
              fontSize: 13,
              color: COLORS.warning,
            }}>
              <strong>Registratore fiscale:</strong> {a.messaggio}
            </div>
          ))}

          {alertOggi.alert_banca?.map((a, i) => (
            <div key={`banca-${i}`} style={{
              background: COLORS.card,
              padding: 10,
              marginBottom: 6,
              borderRadius: BORDER_RADIUS.sm,
              borderLeft: `4px solid ${COLORS.danger}`,
              fontSize: 13,
              color: COLORS.warning,
            }}>
              <strong>Accredito banca:</strong> {a.messaggio}
            </div>
          ))}

          {alertOggi.alert_xml_mancante?.map((a, i) => (
            <div key={`xml-${i}`} style={{
              background: COLORS.card,
              padding: 10,
              marginBottom: 6,
              borderRadius: BORDER_RADIUS.sm,
              borderLeft: `4px solid ${COLORS.purple}`,
              fontSize: 13,
              color: COLORS.warning,
            }}>
              <strong>XML mancante:</strong> {a.messaggio}
            </div>
          ))}
        </div>
      )}

      {/* Statistiche riassuntive */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(5, 1fr)',
        gap: 10,
        marginBottom: 20,
      }}>
        <StatCard
          icon={<FileWarning size={16} />}
          label="XML mancanti (≥7gg)"
          value={stats.fase0_manca_xml || 0}
          subtext={`${stats.fase0_provvisori || 0} provvisori · ${stats.fase0_definitivi_xml || 0} definitivi`}
          accent="accent"
        />
        <StatCard
          icon={<AlertTriangle size={16} />}
          label="Giorni con errore battitura"
          value={stats.fase1_diff_piu + stats.fase1_diff_meno || 0}
          subtext={`${stats.fase1_ok || 0} giorni OK`}
          accent="warning"
        />
        <StatCard
          icon={<TrendingUp size={16} />}
          label="Da compensare in PIÙ"
          value={formatEuro(stats.importo_tot_da_compensare_piu)}
          subtext="sul registratore"
          accent="accent"
        />
        <StatCard
          icon={<CheckCircle size={16} />}
          label="Giorni coperti dall'XML"
          value={stats.fase1_ok || 0}
          subtext="XML ≥ POS reale (o entro tolleranza)"
          accent="success"
        />
        <StatCard
          icon={<XCircle size={16} />}
          label="Accrediti banca mancanti"
          value={formatEuro(stats.importo_tot_mancante_banca)}
          subtext={`${stats.fase2_mancante || 0} giorni`}
          accent="danger"
        />
      </div>

      {/* Vista + Filtro */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        {[
          { k: 'giornaliero', l: 'Giornaliero' },
          { k: 'settimanale', l: 'Settimana per settimana' },
        ].map(o => (
          <Button
            key={o.k}
            size="sm"
            variant={vista === o.k ? 'primary' : 'secondary'}
            onClick={() => setVista(o.k)}
            style={vista === o.k ? { background: COLORS.accent, borderColor: COLORS.accent } : {}}
          >
            {o.l}
          </Button>
        ))}
        <div style={{ width: 1, alignSelf: 'stretch', background: COLORS.border, margin: '2px 4px' }} />
        {vista === 'giornaliero' && [
          { k: 'tutti', l: 'Tutti' },
          { k: 'problemi', l: 'Solo problemi' },
          { k: 'ok', l: 'Solo OK' },
        ].map(o => (
          <Button
            key={o.k}
            size="sm"
            variant={filtroStato === o.k ? 'primary' : 'secondary'}
            onClick={() => setFiltroStato(o.k)}
          >
            {o.l}
          </Button>
        ))}
        {vista === 'giornaliero' && (
          <div style={{ marginLeft: 'auto', fontSize: 12, color: COLORS.textMuted, alignSelf: 'center' }}>
            {giorniFiltrati.length} / {giorni.length} giorni
          </div>
        )}
      </div>

      {vista === 'settimanale' ? (
        <TabellaSettimanale settimane={riepilogoSettimanale} />
      ) : (
      <>
      {/* Tabella giornaliera */}
      <TableWrap>
        <Table>
          <thead>
            <tr style={{ background: COLORS.primary }}>
              <Th style={{ color: '#fff', background: 'transparent' }}>Data</Th>
              <Th align="center" style={{ color: '#fff', background: 'transparent', borderLeft: '2px solid #fff' }}>
                Stato
              </Th>
              <Th colSpan={3} align="center" style={{ color: '#fff', background: 'transparent', borderLeft: '2px solid #fff', borderRight: '2px solid #fff' }}>
                FASE 1: RT vs POS reale
              </Th>
              <Th colSpan={3} align="center" style={{ color: '#fff', background: 'transparent' }}>
                FASE 2: POS reale vs Banca
              </Th>
            </tr>
            <tr style={{ background: COLORS.gray[800] }}>
              <Th style={{ color: '#fff', background: 'transparent' }} />
              <Th align="center" style={{ color: '#fff', background: 'transparent', fontSize: 11, borderLeft: '2px solid #fff' }}>Corrisp.</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>XML elettr. (confronto)</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>POS terminale (modifica)</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11, borderRight: '2px solid #fff' }}>Diff. XML − POS</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>POS terminale</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Accredito banca</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Diff. accr.</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Saldo progr.</Th>
            </tr>
          </thead>
          <tbody>
            {giorniFiltrati.map((g, i) => (
              <RigaGiornaliera key={g.data} g={g} even={i % 2 === 0} onReload={onReload} />
            ))}
          </tbody>
          {stats && (
            <tfoot>
              <tr style={{ background: COLORS.primary, color: '#fff', fontWeight: 700 }}>
                <Td colSpan={5} align="right" style={{ color: '#fff', background: 'transparent' }}>
                  TOTALI (accrediti maturati)
                </Td>
                <Td align="right" style={{ color: '#fff', background: 'transparent' }}>
                  {formatEuro(stats.fase2_pos_totale || 0)}
                </Td>
                <Td align="right" style={{ color: '#fff', background: 'transparent' }}>
                  {formatEuro(stats.fase2_accrediti_totale || 0)}
                </Td>
                <Td colSpan={2} align="right" style={{
                  background: 'transparent',
                  color: (stats.fase2_saldo_finale || 0) >= 0 ? COLORS.successLight : COLORS.dangerLight,
                }}>
                  SALDO {formatEuro(stats.fase2_saldo_finale || 0)}
                </Td>
              </tr>
            </tfoot>
          )}
        </Table>
        {giorniFiltrati.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
            Nessun giorno da mostrare con questo filtro.
          </div>
        )}
      </TableWrap>
      </>
      )}
    </div>
  );
}

// ─── Vista settimanale: quanto incassato vs quanto accreditato, settimana per settimana ───
function TabellaSettimanale({ settimane }) {
  if (!settimane || settimane.length === 0) {
    return (
      <div style={{
        padding: 40, textAlign: 'center', color: COLORS.textSubtle,
        background: COLORS.card, borderRadius: BORDER_RADIUS.lg, border: `1px solid ${COLORS.border}`,
      }}>
        Nessun dato settimanale disponibile per il periodo selezionato.
      </div>
    );
  }
  const statoLabel = {
    ok: 'OK', in_attesa: 'In attesa', mancante: 'Mancante', differenza: 'Differenza',
  };
  const statoVariant = {
    ok: 'success', in_attesa: 'info', mancante: 'danger', differenza: 'warning',
  };
  return (
    <TableWrap>
      <Table>
        <thead>
          <tr style={{ background: COLORS.primary }}>
            <Th style={{ color: '#fff', background: 'transparent' }}>Settimana</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>Incassato (POS reale)</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>Accreditato in banca</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>Differenza</Th>
            <Th align="center" style={{ color: '#fff', background: 'transparent' }}>Stato</Th>
          </tr>
        </thead>
        <tbody>
          {settimane.map((sw, i) => (
            <tr key={sw.settimana} style={{ background: i % 2 === 0 ? COLORS.card : COLORS.bgAlt, borderBottom: `1px solid ${COLORS.gray[100]}` }}>
              <Td style={{ fontWeight: 600 }}>
                {formatDateIT(sw.data_inizio)} – {formatDateIT(sw.data_fine)}
                <div style={{ fontSize: 10, color: COLORS.textSubtle, fontWeight: 400 }}>
                  {sw.settimana} · {sw.num_giorni_con_pos} giorni con incasso
                </div>
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                {formatEuro(sw.pos_totale)}
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                {sw.accredito_totale > 0 ? formatEuro(sw.accredito_totale) : '—'}
              </Td>
              <Td align="right" style={{
                fontWeight: 700,
                color: sw.stato === 'in_attesa' ? COLORS.info : sw.diff_totale >= 0 ? COLORS.success : COLORS.danger,
              }}>
                {sw.stato === 'in_attesa' ? '—' : formatEuro(sw.diff_totale)}
              </Td>
              <Td align="center">
                <Badge variant={statoVariant[sw.stato] || 'neutral'}>{statoLabel[sw.stato] || sw.stato}</Badge>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  );
}

export function EditorPosReale({ g, onSaved }) {
  const valoreIniziale = g.pos_manuale_presente
    ? Number(g.pos_manuale || 0).toFixed(2).replace('.', ',')
    : '';
  const [valore, setValore] = useState(valoreIniziale);
  const [importoSalvato, setImportoSalvato] = useState(
    g.pos_manuale_presente ? Number(g.pos_manuale || 0) : null
  );
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setValore(g.pos_manuale_presente
      ? Number(g.pos_manuale || 0).toFixed(2).replace('.', ',')
      : '');
    setImportoSalvato(g.pos_manuale_presente ? Number(g.pos_manuale || 0) : null);
  }, [g.data, g.pos_manuale, g.pos_manuale_presente]);

  const normalizzato = String(valore).trim().replace(/\s/g, '').replace(',', '.');
  const importoCorrente = Number(normalizzato);
  const valoreModificato = normalizzato !== '' && (
    !Number.isFinite(importoCorrente)
    || importoSalvato === null
    || Math.round(importoCorrente * 100) !== Math.round(importoSalvato * 100)
  );

  const salva = async () => {
    const importo = importoCorrente;
    if (normalizzato === '' || !Number.isFinite(importo) || importo < 0) {
      toast.error('Inserisci un importo POS valido, anche 0,00');
      return;
    }
    setSalvando(true);
    try {
      const res = await api.put('/api/pos-corrispettivi/chiusura-giornaliera', {
        data: g.data,
        importo,
        note: 'Inserimento manuale da Coerenza POS',
      });
      setImportoSalvato(importo);
      toast.success(res.data?.message || `POS reale del ${formatDateIT(g.data)} salvato`);
      if (onSaved) await onSaved();
    } catch (e) {
      toast.error('Errore salvataggio POS: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', alignItems: 'center', minWidth: 168 }}>
      <Input
        aria-label={`POS reale terminale ${g.data}`}
        type="text"
        inputMode="decimal"
        value={valore}
        onChange={e => setValore(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') salva();
        }}
        placeholder="0,00"
        disabled={salvando}
        style={{ width: 92, textAlign: 'right', padding: '6px 8px', minHeight: 36 }}
      />
      {valoreModificato && (
        <Button
          type="button"
          size="sm"
          variant="primary"
          onClick={salva}
          disabled={salvando}
          aria-label={`Salva POS reale ${g.data}`}
          style={{ minHeight: 36, padding: '6px 9px' }}
        >
          {salvando ? '...' : 'Salva'}
        </Button>
      )}
    </div>
  );
}

function RigaGiornaliera({ g, even, onReload }) {
  const [espansa, setEspansa] = useState(false);
  const diffSerColor = g.stato_serale === 'ok' ? COLORS.success :
                       g.stato_serale === 'no_dati' ? COLORS.textSubtle :
                       g.stato_serale === 'in_attesa_xml' ? COLORS.purple : COLORS.danger;
  // Regola colori richiesta: differenza POSITIVA (banca ha accreditato di
  // più) → VERDE; NEGATIVA (accredito minore o mancante) → ROSSO.
  const diffAccrColor = g.stato_accredito === 'ok' ? COLORS.success :
                        g.stato_accredito === 'in_attesa' ? COLORS.info :
                        g.stato_accredito === 'no_pos_manuale' ? COLORS.textSubtle :
                        g.stato_accredito === 'raggruppato' ? COLORS.textSubtle :
                        g.stato_accredito === 'mancante' ? COLORS.danger :
                        (g.diff_accredito || 0) >= 0 ? COLORS.success : COLORS.danger;

  const statoAccrLabel = {
    'ok': 'OK',
    'in_attesa': 'In attesa',
    'no_pos_manuale': '—',
    'raggruppato': '↳ nel gruppo',
    'mancante': 'Mancante',
    'differenza': 'Diff.',
    'extra': 'Extra',
  }[g.stato_accredito] || g.stato_accredito;

  // Badge stato corrispettivo (fase 0)
  const statoCorr = g.stato_corrispettivo;
  const statoCorrBadge = {
    'definitivo_xml': { label: 'XML', variant: 'success' },
    'provvisorio': { label: 'Provv.', variant: 'warning' },
    'manca_xml': { label: '⚠ No XML', variant: 'accent' },
    'sconosciuto': { label: '—', variant: 'neutral' },
  }[statoCorr] || { label: '—', variant: 'neutral' };

  return (
    <>
    <tr style={{ background: even ? COLORS.card : COLORS.bgAlt, borderBottom: g.dettaglio_gruppo && espansa ? 'none' : `1px solid ${COLORS.gray[100]}` }}>
      <Td style={{ fontWeight: 600 }}>
        {formatDateIT(g.data)}
      </Td>
      <Td align="center" style={{ borderLeft: `2px solid ${COLORS.border}` }}>
        <Badge variant={statoCorrBadge.variant}>{statoCorrBadge.label}</Badge>
      </Td>
      <Td align="right" style={{ borderLeft: `2px solid ${COLORS.border}` }}>
        {g.xml_elettronico > 0 ? formatEuro(g.xml_elettronico) : (statoCorr !== 'definitivo_xml' ? <em style={{ color: COLORS.textSubtle, fontSize: 11 }}>attendo XML</em> : '—')}
      </Td>
      <Td align="right">
        <EditorPosReale g={g} onSaved={onReload} />
      </Td>
      <Td
        align="right"
        style={{
          borderRight: `2px solid ${COLORS.border}`,
          color: diffSerColor,
          fontWeight: 600,
        }}
      >
        {g.stato_serale === 'no_dati' ? '—'
          : g.stato_serale === 'in_attesa_xml' ? <em style={{ color: COLORS.purple, fontSize: 11 }}>attendo XML</em>
          : formatEuroConSegno(g.diff_serale)}
      </Td>
      <Td align="right">
        {g.pos_manuale_presente ? formatEuro(g.pos_manuale) : '—'}
        {g.capogruppo && g.giorni_gruppo > 1 && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setEspansa(v => !v)}
            style={{
              display: 'block', marginLeft: 'auto', marginTop: 2,
              fontSize: 10, color: COLORS.primary, fontWeight: 700,
              padding: 0, minHeight: 'auto',
              textDecoration: 'underline', textDecorationStyle: 'dotted',
            }}
            title="Mostra il dettaglio giorno per giorno di questo accredito"
          >
            gruppo {g.giorni_gruppo} gg: {formatEuro(g.pos_gruppo)} {espansa ? '▲' : '▼'}
          </Button>
        )}
      </Td>
      <Td align="right">
        {g.stato_accredito === 'raggruppato'
          ? <em style={{ color: COLORS.textSubtle, fontSize: 11 }}>↳ accr. {formatDateIT(g.data_accredito_attesa)}</em>
          : g.accredito_banca > 0 ? formatEuro(g.accredito_banca) : '—'}
        {g.numero_movimenti_banca > 0 && (
          <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 2 }}>
            Estratto conto · {g.numero_movimenti_banca}{' '}
            {g.numero_movimenti_banca === 1 ? 'movimento' : 'movimenti'}
          </div>
        )}
      </Td>
      <Td
        align="right"
        style={{
          color: diffAccrColor,
          fontWeight: 600,
        }}
      >
        {g.riconciliato_banca_reale ? (
          <BadgeRiconciliatoBanca riconciliato />
        ) : (
          <div style={{ fontSize: 11, textTransform: 'uppercase', fontWeight: 700 }}>
            {statoAccrLabel}
          </div>
        )}
        {g.stato_accredito === 'ok' || g.stato_accredito === 'differenza' || g.stato_accredito === 'extra'
          ? formatEuro(g.diff_accredito)
          : g.stato_accredito === 'mancante'
            ? formatEuro(g.diff_accredito)
            : null}
      </Td>
      <Td
        align="right"
        style={{
          fontWeight: 700,
          color: g.saldo_progressivo == null ? COLORS.textSubtle
            : g.saldo_progressivo >= 0 ? COLORS.success : COLORS.danger,
        }}
      >
        {g.saldo_progressivo == null ? '' : formatEuro(g.saldo_progressivo)}
      </Td>
    </tr>
    {g.dettaglio_gruppo && espansa && (
      <tr style={{ background: even ? COLORS.card : COLORS.bgAlt, borderBottom: `1px solid ${COLORS.gray[100]}` }}>
        <Td colSpan={8} style={{ padding: '0 8px 10px 24px' }}>
          <div style={{
            background: COLORS.bgAlt, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
            padding: '8px 12px', fontSize: 11, color: COLORS.gray[700],
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4, color: COLORS.primary }}>
              Accredito di {formatEuro(g.accredito_banca)} del {formatDateIT(g.data_accredito_attesa)} — da dove arriva:
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody>
                {g.dettaglio_gruppo.map(dg => (
                  <tr key={dg.data}>
                    <td style={{ padding: '2px 8px 2px 0' }}>↳ {formatDateIT(dg.data)}</td>
                    <td style={{ padding: '2px 0', textAlign: 'right', fontWeight: 600 }}>{formatEuro(dg.pos_manuale)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: '4px 8px 0 0', fontWeight: 700 }}>Totale incassato</td>
                  <td style={{ padding: '4px 0 0', textAlign: 'right', fontWeight: 700 }}>{formatEuro(g.pos_gruppo)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '2px 8px 0 0', fontWeight: 700 }}>Accreditato in banca</td>
                  <td style={{ padding: '2px 0 0', textAlign: 'right', fontWeight: 700 }}>{formatEuro(g.accredito_banca)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '2px 8px 0 0', fontWeight: 700 }}>Differenza</td>
                  <td style={{
                    padding: '2px 0 0', textAlign: 'right', fontWeight: 700,
                    color: g.diff_accredito >= 0 ? COLORS.success : COLORS.danger,
                  }}>{formatEuro(g.diff_accredito)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Td>
      </tr>
    )}
    </>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// MODALE: Inserimento chiusura serale (corrispettivo manuale + POS reale)
// ═══════════════════════════════════════════════════════════════════════════
// Un form compatto per inserire in un colpo solo i due dati che l'utente ha
// a fine giornata: il totale del corrispettivo e il POS reale battuto.
// Il corrispettivo è marcato come "provvisorio" finché non arriva XML AdE.
// ═══════════════════════════════════════════════════════════════════════════
function ModalChiusuraSerale({ onClose, onSaved }) {
  const oggi = new Date().toISOString().slice(0, 10);
  const [dataForm, setDataForm] = useState(oggi);
  const [totale, setTotale] = useState('');
  const [posReale, setPosReale] = useState('');
  const [note, setNote] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');

  const salva = async () => {
    if (!dataForm) {
      setErrore('Inserisci la data');
      return;
    }
    const t = parseFloat(totale.replace(',', '.'));
    if (isNaN(t) || t <= 0) {
      setErrore('Il totale corrispettivo deve essere un numero maggiore di 0');
      return;
    }
    const p = posReale ? parseFloat(posReale.replace(',', '.')) : null;
    if (p !== null && (isNaN(p) || p < 0)) {
      setErrore('Il POS reale deve essere un numero >= 0');
      return;
    }

    setSalvando(true);
    setErrore('');
    try {
      await api.post('/api/corrispettivi/manuale', {
        data: dataForm,
        totale: t,
        pos_reale_serale: p,
        note: note || undefined,
      });
      if (onSaved) onSaved();
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore salvataggio');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10000, padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.xl, padding: 20,
          width: '100%', maxWidth: 480,
          boxShadow: SHADOWS.modal,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 17, color: COLORS.primary }}>
            Chiusura serale
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            style={{ padding: 4 }}
          >
            <X size={18} color={COLORS.textMuted} />
          </Button>
        </div>

        <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16, lineHeight: 1.5 }}>
          Inserisci il totale del corrispettivo giornaliero (provvisorio) e il POS reale
          letto dall'hardware. Quando arriverà l'XML dall'Agenzia Entrate, il totale sarà
          sostituito automaticamente col dato ufficiale.
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Data
          </label>
          <Input
            type="date"
            value={dataForm}
            max={oggi}
            onChange={e => setDataForm(e.target.value)}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Totale corrispettivo (€) *
          </label>
          <Input
            type="text"
            inputMode="decimal"
            value={totale}
            onChange={e => setTotale(e.target.value)}
            placeholder="es. 1250,50"
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            POS reale dalla chiusura serale (€)
          </label>
          <Input
            type="text"
            inputMode="decimal"
            value={posReale}
            onChange={e => setPosReale(e.target.value)}
            placeholder="es. 450,00 (opzionale)"
          />
          <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 4 }}>
            Facoltativo ma consigliato: il totale battuto al POS fisico (per il controllo FASE 1).
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Note
          </label>
          <Input
            type="text"
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Eventuale nota"
          />
        </div>

        {errore && (
          <div style={{
            padding: 10, background: COLORS.dangerLight, border: `1px solid ${COLORS.danger}`,
            color: COLORS.danger, borderRadius: BORDER_RADIUS.sm, fontSize: 13, marginBottom: 12,
          }}>
            {errore}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="secondary" onClick={onClose} disabled={salvando}>
            Annulla
          </Button>
          <Button
            variant="primary"
            onClick={salva}
            disabled={salvando}
            style={{ background: COLORS.accent, borderColor: COLORS.accent }}
          >
            {salvando ? 'Salvo...' : 'Salva chiusura'}
          </Button>
        </div>
      </div>
    </div>
  );
}


export function parseTotaliPosTesto(testo) {
  const righe = [];
  const dateViste = new Set();
  const linee = String(testo || '').split(/\r?\n/);
  for (let indice = 0; indice < linee.length; indice += 1) {
    const linea = linee[indice].trim();
    if (!linea || /^data\b/i.test(linea)) continue;
    const match = linea.match(/^(\d{4}-\d{2}-\d{2})\s*[;\t]\s*([0-9]+(?:[.,][0-9]{1,2})?)$/);
    if (!match) throw new Error(`Riga ${indice + 1} non valida: usa AAAA-MM-GG;importo`);
    const data = match[1];
    const parsedDate = new Date(`${data}T00:00:00Z`);
    if (Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0, 10) !== data) {
      throw new Error(`Data non valida alla riga ${indice + 1}`);
    }
    if (dateViste.has(data)) throw new Error(`Data duplicata: ${data}`);
    dateViste.add(data);
    const importo = Number(match[2].replace(',', '.'));
    if (!Number.isFinite(importo) || importo < 0) {
      throw new Error(`Importo non valido alla riga ${indice + 1}`);
    }
    righe.push({ data, importo: Math.round(importo * 100) / 100 });
  }
  if (!righe.length) throw new Error('Incolla almeno una giornata POS');
  return righe;
}


export function ModalImportTotaliPos({ onClose, onSaved }) {
  const [testo, setTesto] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');
  let anteprima = null;
  try {
    if (testo.trim()) {
      const righe = parseTotaliPosTesto(testo);
      anteprima = {
        righe,
        totale: righe.reduce((somma, riga) => somma + riga.importo, 0),
      };
    }
  } catch (e) {
    anteprima = { errore: e.message };
  }

  const importa = async () => {
    setErrore('');
    let righe;
    try {
      righe = parseTotaliPosTesto(testo);
    } catch (e) {
      setErrore(e.message);
      return;
    }
    setSalvando(true);
    try {
      const res = await api.post('/api/pos-corrispettivi/chiusure-giornaliere/batch', {
        righe,
        note: 'Import Numia: solo acquisti approvati',
      });
      if (res.data?.errori) {
        setErrore(`${res.data.errori} giornate non sono state salvate`);
        return;
      }
      toast.success(`${res.data?.salvati || righe.length} totali POS importati`);
      if (onSaved) onSaved(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore importazione');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10000, padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.xl, padding: 20,
          width: '100%', maxWidth: 620, boxShadow: SHADOWS.modal,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 17, color: COLORS.primary }}>Importa totali POS giornalieri</h3>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Chiudi importazione POS">
            <X size={18} color={COLORS.textMuted} />
          </Button>
        </div>
        <p style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
          Una riga per giorno nel formato <code>AAAA-MM-GG;importo</code>. Il valore diventa il
          POS reale del terminale; il pagamento elettronico XML resta invariato.
        </p>
        <textarea
          aria-label="Totali POS giornalieri"
          value={testo}
          onChange={e => setTesto(e.target.value)}
          placeholder={'2026-07-01;1685,80\n2026-07-02;1666,90'}
          rows={14}
          disabled={salvando}
          style={{
            width: '100%', resize: 'vertical', border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md, padding: 10, fontFamily: 'monospace',
            fontSize: 13, color: COLORS.text, background: COLORS.card,
          }}
        />
        {anteprima?.righe && (
          <div style={{ marginTop: 8, fontSize: 12, color: COLORS.success }}>
            {anteprima.righe.length} giornate · totale {formatEuro(anteprima.totale)}
          </div>
        )}
        {(errore || anteprima?.errore) && (
          <div style={{ marginTop: 8, color: COLORS.danger, fontSize: 12 }}>
            {errore || anteprima.errore}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <Button variant="secondary" onClick={onClose} disabled={salvando}>Annulla</Button>
          <Button
            variant="primary"
            onClick={importa}
            disabled={salvando || !anteprima?.righe}
            aria-label="Conferma importazione POS"
          >
            {salvando ? 'Importo...' : 'Importa e aggiorna Prima Nota'}
          </Button>
        </div>
      </div>
    </div>
  );
}
