import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, FONT, formatEuro, formatDateIT } from '../lib/utils';
import { Badge, StatCard, TableWrap, Table, Th, Td } from '../components/ds';
import {
  PageLayout,
  PageSection,
  PageGrid,
  PageLoading,
  PageEmpty,
} from '../components/PageLayout';
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  Building2,
  Receipt,
  AlertCircle,
  Info,
  BookOpen,
  ClipboardList,
} from 'lucide-react';
import { euroOppure } from '../lib/vista';

export const DATO_NON_DISPONIBILE = 'Dato non disponibile';

/**
 * Un importo che il backend non sa calcolare arriva null (es. IVA a credito
 * con fatture senza ``iva_detraibile`` classificata): non e' 0,00.
 */
export function euroODato(valore) {
  return valore == null ? DATO_NON_DISPONIBILE : euroOppure(valore);
}

export default function Finanziaria() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    loadSummary();
  }, [selectedYear]);

  async function loadSummary() {
    try {
      setLoading(true);
      setLoadError('');
      const r = await api.get(`/api/finanziaria/summary?anno=${selectedYear}`);
      setSummary(r.data);
    } catch (e) {
      console.error('Error loading financial summary:', e);
      setSummary(null);
      setLoadError(e.response?.data?.detail || e.message || 'Errore di caricamento');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <PageLayout
        title="Situazione Finanziaria"
        subtitle={`Riepilogo finanziario ${selectedYear}`}
      >
        <PageLoading message={`Caricamento dati finanziari per ${selectedYear}...`} />
      </PageLayout>
    );
  }

  if (loadError || !summary) {
    return (
      <PageLayout title="Situazione Finanziaria" subtitle={`Riepilogo finanziario ${selectedYear}`}>
        <div role="alert" style={{ padding: 20, border: `1px solid ${COLORS.danger}`, background: COLORS.dangerLight, borderRadius: 8 }}>
          <strong>Dati finanziari non disponibili.</strong>
          <div style={{ marginTop: 6, fontSize: 13 }}>{loadError || 'Il servizio non ha restituito un riepilogo valido.'}</div>
        </div>
      </PageLayout>
    );
  }

  const hasNoData = summary?.total_income === 0 && summary?.total_expenses === 0;

  return (
    <PageLayout
      title="Situazione Finanziaria"
      subtitle={`Riepilogo finanziario e stima IVA documentale - Anno ${selectedYear}`}
      actions={
        <Badge
          variant="info"
          style={{
            fontSize: 13,
            fontWeight: 600,
            padding: '10px 20px',
            textTransform: 'none',
            letterSpacing: 'normal',
          }}
        >
          Anno: {selectedYear}
        </Badge>
      }
    >
      {/* Avviso nessun dato */}
      {hasNoData && (
        <div
          style={{
            background: COLORS.warningLight,
            borderRadius: 8,
            padding: 16,
            marginBottom: 20,
            border: `1px solid ${COLORS.warning}`,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <AlertCircle size={24} color={COLORS.warning} />
          <div>
            <div style={{ fontWeight: 600, color: COLORS.warning }}>
              Nessun movimento registrato per {selectedYear}
            </div>
            <div style={{ fontSize: 13, color: COLORS.warning, marginTop: 4 }}>
              Se hai dati per altri anni, seleziona un anno diverso dalla barra laterale.
            </div>
          </div>
        </div>
      )}

      {/* KPI Principali */}
      <PageGrid cols={4} gap={16}>
        <StatCard
          icon={<TrendingUp size={18} />}
          label="Entrate finanziarie dell'anno"
          value={euroOppure(summary?.total_income)}
          subtext={`Cassa: ${euroOppure(summary?.cassa?.entrate)} | BPM: ${euroOppure(summary?.banca?.entrate)} | SumUp: ${euroOppure(summary?.sumup?.entrate)}`}
          accent="success"
        />
        <StatCard
          icon={<TrendingDown size={18} />}
          label="Uscite finanziarie dell'anno"
          value={euroOppure(summary?.total_expenses)}
          subtext={`Cassa: ${euroOppure(summary?.cassa?.uscite)} | BPM: ${euroOppure(summary?.banca?.uscite)} | SumUp: ${euroOppure(summary?.sumup?.uscite)}`}
          accent="danger"
        />
        <StatCard
          icon={<Wallet size={18} />}
          label="Variazione finanziaria dell'anno"
          value={formatEuro(summary?.flow_balance ?? summary?.balance)}
          subtext="Entrate meno uscite, senza trasferimenti interni"
          accent={(summary?.flow_balance ?? summary?.balance) >= 0 ? 'primary' : 'danger'}
        />
        <StatCard
          icon={<Building2 size={18} />}
          label="Disponibilità contabile"
          value={formatEuro(summary?.available_balance ?? summary?.saldo_totale)}
          subtext={`Include riporti iniziali: ${euroOppure(summary?.opening_balance)}`}
          accent={(summary?.available_balance ?? summary?.saldo_totale) >= 0 ? 'success' : 'danger'}
        />
      </PageGrid>

      {/* Sezione IVA */}
      <PageSection title="Riepilogo IVA" icon={<Receipt size={16} aria-hidden />} style={{ marginTop: 20 }}>
        <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 16 }}>
          Stima IVA da Corrispettivi XML e Fatture XML classificate. La liquidazione verificata,
          l'F24 e l'addebito bancario restano controlli distinti.
        </p>
        <PageGrid cols={3} gap={16}>
          <StatCard
            label="IVA a DEBITO (Corrispettivi)"
            value={euroOppure(summary?.vat_debit)}
            subtext={
              <>
                Da {summary?.corrispettivi?.count || 0} corrispettivi
                <br />
                Totale vendite: {euroOppure(summary?.corrispettivi?.totale)}
              </>
            }
            accent="warning"
          />
          <StatCard
            label="IVA a CREDITO (Fatture)"
            value={euroODato(summary?.vat_credit)}
            subtext={
              <>
                Da {summary?.fatture?.count || 0} fatture
                <br />
                Totale acquisti: {euroOppure(summary?.fatture?.totale)}
              </>
            }
            accent="success"
          />
          <StatCard
            label="Stima saldo IVA"
            value={euroODato(summary?.vat_balance)}
            subtext={
              <Badge
                variant={
                  summary?.vat_balance == null ? 'warning' : summary.vat_balance > 0 ? 'danger' : 'success'
                }
              >
                {summary?.vat_status || '-'}
              </Badge>
            }
            accent={
              summary?.vat_balance == null ? 'warning' : summary.vat_balance > 0 ? 'danger' : 'success'
            }
          />
        </PageGrid>
      </PageSection>

      {/* Dettaglio Prima Nota */}
      <PageSection title="Dettaglio Prima Nota" icon={<BookOpen size={16} aria-hidden />} style={{ marginTop: 20 }}>
        {(summary?.avvisi_aggiornamento || []).map((a) => (
          <div
            key={a.conto}
            role="alert"
            data-testid={`finanziaria-avviso-${a.conto}`}
            style={{
              display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: 12,
              marginBottom: 12, borderRadius: 8, background: COLORS.warningLight || COLORS.bgAlt,
              border: `1px solid ${COLORS.warning}`, color: COLORS.text,
            }}
          >
            <span style={{ flex: '1 1 260px', fontSize: 14 }}>{a.messaggio}</span>
            {a.azione && (
              <Link
                to={a.azione.percorso}
                style={{
                  minHeight: 44, display: 'inline-flex', alignItems: 'center', padding: '0 16px',
                  borderRadius: 8, background: COLORS.primary, color: '#fff', fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                {a.azione.etichetta}
              </Link>
            )}
          </div>
        ))}
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th align="left">Conto</Th>
                <Th align="right">Riporto iniziale</Th>
                <Th align="right">Entrate</Th>
                <Th align="right">Uscite</Th>
                <Th align="right">Saldo contabile</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Wallet size={16} color={COLORS.textMuted} /> Cassa
                    </span>
                    <div data-testid="finanziaria-aggiornato-cassa" style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                      {summary?.cassa?.aggiornato_al ? `aggiornato al ${formatDateIT(summary.cassa.aggiornato_al)}` : 'data ultimo movimento non nota'}
                    </div>
                  </Td>
                <Td align="right" mono>{euroOppure(summary?.cassa?.riporto)}</Td>
                <Td align="right" mono style={{ color: COLORS.success, fontWeight: 500 }}>
                  {euroOppure(summary?.cassa?.entrate)}
                </Td>
                <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                  {euroOppure(summary?.cassa?.uscite)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600 }}>
                  {euroOppure(summary?.cassa?.saldo)}
                </Td>
              </tr>
              <tr>
                <Td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Building2 size={16} color={COLORS.textMuted} /> Banca BPM
                    </span>
                    <div data-testid="finanziaria-aggiornato-banca" style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                      {summary?.banca?.aggiornato_al ? `aggiornato al ${formatDateIT(summary.banca.aggiornato_al)}` : 'data ultimo movimento non nota'}
                    </div>
                  </Td>
                <Td align="right" mono>{euroOppure(summary?.banca?.riporto)}</Td>
                <Td align="right" mono style={{ color: COLORS.success, fontWeight: 500 }}>
                  {euroOppure(summary?.banca?.entrate)}
                </Td>
                <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                  {euroOppure(summary?.banca?.uscite)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600 }}>
                  {euroOppure(summary?.banca?.saldo)}
                </Td>
              </tr>
              {summary?.sumup && (
                <tr data-testid="finanziaria-riga-sumup">
                  <Td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Building2 size={16} color={COLORS.textMuted} /> Mastercard SumUp
                    </span>
                    <div data-testid="finanziaria-aggiornato-sumup" style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                      {summary?.sumup?.aggiornato_al ? `aggiornato al ${formatDateIT(summary.sumup.aggiornato_al)}` : 'data ultimo movimento non nota'}
                    </div>
                  </Td>
                  <Td align="right" mono>{euroOppure(summary.sumup.riporto)}</Td>
                  <Td align="right" mono style={{ color: COLORS.success, fontWeight: 500 }}>
                    {euroOppure(summary.sumup.entrate)}
                  </Td>
                  <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                    {euroOppure(summary.sumup.uscite)}
                  </Td>
                  <Td align="right" mono style={{ fontWeight: 600 }}>
                    {euroOppure(summary.sumup.saldo)}
                  </Td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr style={{ background: COLORS.bgAlt, fontWeight: 600 }}>
                <Td style={{ fontWeight: 600 }}>TOTALE</Td>
                <Td align="right" mono style={{ fontWeight: 600 }}>
                  {euroOppure(summary?.opening_balance)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600, color: COLORS.success }}>
                  {euroOppure(summary?.total_income)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600, color: COLORS.danger }}>
                  {euroOppure(summary?.total_expenses)}
                </Td>
                <Td
                  data-testid="saldo-contabile-totale"
                  align="right"
                  mono
                  style={{
                    fontWeight: 600,
                    color: summary?.saldo_totale >= 0 ? COLORS.success : COLORS.danger,
                  }}
                >
                  {euroOppure(summary?.saldo_totale)}
                </Td>
              </tr>
            </tfoot>
          </Table>
        </TableWrap>
        <p style={{ color: COLORS.textMuted, fontSize: 13, margin: '12px 0 0' }}>
          Il saldo non è «riporto + entrate − uscite»: entrate e uscite escludono i versamenti e i
          trasferimenti fra Cassa, Banca e SumUp, che invece il saldo comprende. {summary?.financial_note} I pagamenti di salari e F24 sono già compresi nelle uscite
          bancarie e non vengono sommati una seconda volta.
        </p>
        <p
          data-testid="finanziaria-nota-prima-nota"
          style={{ color: COLORS.textMuted, fontSize: 13, margin: '6px 0 0' }}
        >
          I saldi sono quelli registrati in Prima Nota, non saldi certificati dall'estratto conto.
        </p>
      </PageSection>

      {/* Situazione Debiti/Crediti */}
      <PageSection title="Situazione Debiti/Crediti" icon={<ClipboardList size={16} aria-hidden />} style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: COLORS.dangerLight,
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color={COLORS.danger} />
              Fatture da pagare (debiti vs fornitori)
            </span>
            <span style={{ fontWeight: 700, color: COLORS.danger, fontFamily: FONT.mono }}>
              {euroOppure(summary?.payables)}
            </span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: COLORS.successLight,
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color={COLORS.success} />
              Fatture da incassare (crediti vs clienti)
            </span>
            {summary?.receivables_available === false ? (
              <span style={{ fontWeight: 600, color: COLORS.textMuted, textAlign: 'right' }}>
                Non disponibile
                <small style={{ display: 'block', fontWeight: 400 }}>
                  {summary?.receivables_note}
                </small>
              </span>
            ) : (
              <span style={{ fontWeight: 700, color: COLORS.success, fontFamily: FONT.mono }}>
                {euroOppure(summary?.receivables)}
              </span>
            )}
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background:
                summary?.vat_balance == null
                  ? COLORS.warningLight
                  : summary.vat_balance > 0 ? COLORS.dangerLight : COLORS.successLight,
              borderRadius: 8,
            }}
          >
            <span>
              Stima documentale IVA{' '}
              {summary?.vat_balance == null
                ? `(${summary?.vat_status || 'non calcolabile'})`
                : summary.vat_balance > 0 ? 'a debito' : 'a credito'}
            </span>
            <span
              data-testid="finanziaria-iva-saldo"
              style={{
                fontWeight: 700,
                fontFamily: summary?.vat_balance == null ? undefined : FONT.mono,
                color:
                  summary?.vat_balance == null
                    ? COLORS.textMuted
                    : summary.vat_balance > 0 ? COLORS.danger : COLORS.success,
              }}
            >
              {summary?.vat_balance == null
                ? DATO_NON_DISPONIBILE
                : formatEuro(Math.abs(summary.vat_balance))}
            </span>
          </div>
        </div>
      </PageSection>

      {/* Info */}
      <PageSection
        title="Come vengono calcolati i dati"
        icon={<Info size={18} />}
        style={{ marginTop: 20 }}
      >
        <ul style={{ paddingLeft: 20, lineHeight: 2, margin: 0, color: COLORS.gray[600], fontSize: 13 }}>
          <li>
            <strong>Entrate/Uscite:</strong> somma dei movimenti Prima Nota Cassa + Banca,
            esclusi i trasferimenti interni
          </li>
          <li>
            <strong>Disponibilità contabile:</strong> saldo Cassa + saldo Banca, inclusi i riporti
            iniziali; non coincide necessariamente con la variazione dell'anno
          </li>
          <li>
            <strong>IVA Debito:</strong> Estratta dai file XML dei Corrispettivi giornalieri
            (vendite)
          </li>
          <li>
            <strong>IVA Credito:</strong> Estratta dai file XML delle Fatture (acquisti fornitori)
          </li>
          <li>
            <strong>Stima IVA:</strong> IVA a debito - IVA detraibile classificata. Non certifica
            la liquidazione del commercialista né il pagamento F24
          </li>
          <li>
            <strong>Fatture da pagare:</strong> Fatture con stato diverso da "Pagata"
          </li>
          <li>
            <strong>Crediti clienti:</strong> non sono esposti finché non esiste una fonte canonica
            delle fatture attive
          </li>
        </ul>
      </PageSection>
    </PageLayout>
  );
}
