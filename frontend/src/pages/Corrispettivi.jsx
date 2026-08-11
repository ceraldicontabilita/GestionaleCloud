import React, { useState, useEffect, useRef } from 'react';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import api from '../api';
import {
  formatDateIT,
  formatDateGGMM,
  formatEuro,
  COLORS,
  BORDER_RADIUS,
  useIsMobile,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  PageLayout,
  PageSection,
  PageGrid,
  PageLoading,
  PageEmpty,
  PageError,
} from '../components/PageLayout';
import {
  Button,
  StatCard,
  TableWrap,
  Table,
  Th,
  Td,
  RowActions,
  RowActionButton,
  ListaAdattiva,
} from '../components/ds';
import {
  Receipt,
  Banknote,
  CreditCard,
  Percent,
  RefreshCw,
  X,
} from 'lucide-react';

const asNumber = value => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value !== 'string') return 0;
  const parsed = Number(value.trim().replace(/\./g, '').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
};
const ivaRows = item => Array.isArray(item?.riepilogo_iva) ? item.riepilogo_iva : [];
const imponibileItem = item => item?.totale_imponibile != null
  ? asNumber(item.totale_imponibile)
  : ivaRows(item).reduce((sum, row) => sum + asNumber(row.ammontare ?? row.imponibile), 0);
const ivaItem = item => item?.totale_iva != null
  ? asNumber(item.totale_iva)
  : ivaRows(item).reduce((sum, row) => sum + asNumber(row.imposta), 0);
const totaleItem = item => item?.totale != null
  ? asNumber(item.totale)
  : imponibileItem(item) + ivaItem(item);
const sourceValue = (item, ...keys) => keys.map(key => item?.[key]).find(Boolean) || null;

/**
 * PAGINA CORRISPETTIVI
 * Mostra i corrispettivi dalla collection corrispettivi
 * I corrispettivi vengono importati tramite XML dal registratore telematico
 */
export default function Corrispettivi() {
  const isMobile = useIsMobile();
  const { anno: selectedYear } = useAnnoGlobale();
  const [corrispettivi, setCorrispettivi] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const dettaglioRef = useRef(null);

  // Deep link: item selezionato sincronizzato con hash (#selected=2026-04-08)
  const [hs, setHs] = useHashState({ selected: '' });
  const selectedItem = corrispettivi.find(c => c.data === hs.selected) || null;

  useEffect(() => {
    if (selectedItem && dettaglioRef.current) {
      dettaglioRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [selectedItem]);

  useEffect(() => {
    loadCorrispettivi();
  }, [selectedYear]);

  async function loadCorrispettivi() {
    try {
      setLoading(true);
      setErr('');
      const r = await api.get(`/api/corrispettivi?anno=${selectedYear}&limit=2500`);
      const data = r.data || [];
      const corrispettiviArray = Array.isArray(data) ? data : [];
      corrispettiviArray.sort((a, b) => (b.data || '').localeCompare(a.data || ''));
      setCorrispettivi(corrispettiviArray);
    } catch (e) {
      console.error('Error loading corrispettivi:', e);
      setErr('Errore caricamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  const openDetail = item => {
    setHs('selected', item.data || '');
    requestAnimationFrame(() => {
      dettaglioRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const totaleGiornaliero = corrispettivi.reduce((sum, c) => sum + totaleItem(c), 0);
  const totaleCassa = corrispettivi.reduce((sum, c) => sum + asNumber(c.pagato_contanti), 0);
  const totaleElettronico = corrispettivi.reduce((sum, c) => sum + asNumber(c.pagato_elettronico), 0);
  const totaleIVA = corrispettivi.reduce((sum, c) => sum + ivaItem(c), 0);
  const totaleImponibile = corrispettivi.reduce((sum, c) => sum + imponibileItem(c), 0);

  return (
    <PageLayout
      title="Corrispettivi Elettronici"
      icon="🧾"
      subtitle={`Corrispettivi giornalieri dal registratore telematico - Anno ${selectedYear}`}
      actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <Button
            variant="secondary"
            onClick={loadCorrispettivi}
            disabled={loading}
            iconLeft={<RefreshCw size={16} />}
            data-testid="corrispettivi-refresh-btn"
          >
            Aggiorna
          </Button>
        </div>
      }
    >
      {err && (
        <PageError
          message={err}
          onRetry={() => {
            setErr('');
            loadCorrispettivi();
          }}
        />
      )}

      {loading ? (
        <PageLoading message="Caricamento corrispettivi..." />
      ) : (
        <>
          {/* KPI Cards */}
          {corrispettivi.length > 0 && (
            <PageGrid cols={4} gap={16}>
              <StatCard
                icon={<Receipt size={18} />}
                label="Totale Corrispettivi"
                value={formatEuro(totaleGiornaliero)}
                accent="primary"
              />
              <StatCard
                icon={<Banknote size={18} />}
                label="Pagato Cassa"
                value={formatEuro(totaleCassa)}
                accent="success"
              />
              <StatCard
                icon={<CreditCard size={18} />}
                label="Pagato POS"
                value={formatEuro(totaleElettronico)}
                accent="info"
              />
              <StatCard
                icon={<Percent size={18} />}
                label="IVA 10%"
                value={formatEuro(totaleIVA)}
                subtext={`Imponibile: ${formatEuro(totaleImponibile)}`}
                accent="warning"
              />
            </PageGrid>
          )}

          {/* Dettaglio selezionato */}
          {selectedItem && (
            <div ref={dettaglioRef} style={{ scrollMarginTop: 100 }}>
            <PageSection
              title={`Dettaglio Corrispettivo ${formatDateIT(selectedItem.data)}`}
              icon="📋"
              style={{ marginTop: 20 }}
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setHs('selected', '')}
                iconLeft={<X size={20} color={COLORS.textMuted} />}
                aria-label="Chiudi dettaglio corrispettivo"
                style={{ position: 'absolute', top: 16, right: 16, padding: 4 }}
              />

              <PageGrid cols={3} gap={20}>
                <div>
                  <h4
                    style={{
                      margin: '0 0 12px 0',
                      fontSize: 13,
                      color: COLORS.textMuted,
                      fontWeight: 600,
                    }}
                  >
                    Dati Generali
                  </h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div>
                      📅 Data: <strong>{formatDateIT(selectedItem.data)}</strong>
                    </div>
                    <div>🔢 Matricola RT: {selectedItem.matricola_rt || '-'}</div>
                    <div>🏢 P.IVA: {selectedItem.partita_iva || '-'}</div>
                    <div>📄 N° Documenti: {selectedItem.numero_documenti || '-'}</div>
                  </div>
                </div>
                <div>
                  <h4
                    style={{
                      margin: '0 0 12px 0',
                      fontSize: 13,
                      color: COLORS.textMuted,
                      fontWeight: 600,
                    }}
                  >
                    Pagamenti
                  </h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div style={{ color: COLORS.success }}>
                      💵 Cassa: {formatEuro(selectedItem.pagato_contanti)}
                    </div>
                    <div style={{ color: COLORS.info }}>
                      💳 Elettronico: {formatEuro(selectedItem.pagato_elettronico)}
                    </div>
                    <div style={{ fontWeight: 700, marginTop: 8, fontSize: 15 }}>
                      Totale: {formatEuro(totaleItem(selectedItem))}
                    </div>
                  </div>
                </div>
                <div>
                  <h4
                    style={{
                      margin: '0 0 12px 0',
                      fontSize: 13,
                      color: COLORS.textMuted,
                      fontWeight: 600,
                    }}
                  >
                    IVA
                  </h4>
                  <div style={{ fontSize: 13, lineHeight: 2 }}>
                    <div>Imponibile: {formatEuro(imponibileItem(selectedItem))}</div>
                    <div>Imposta: {formatEuro(ivaItem(selectedItem))}</div>
                  </div>
                </div>
              </PageGrid>

              <div style={{ marginTop: 18, padding: 12, background: COLORS.background, borderRadius: BORDER_RADIUS.sm, fontSize: 12.5, lineHeight: 1.8 }}>
                <strong>Provenienza documento</strong>
                <div>File: {sourceValue(selectedItem, 'filename', 'nome_file', 'source_filename') || 'non disponibile'}</div>
                <div>SHA-256: {sourceValue(selectedItem, 'sha256', 'pdf_hash', 'file_hash') || 'non disponibile'}</div>
                <div>Parser: {sourceValue(selectedItem, 'parser_version', 'versione_parser') || 'non disponibile'}</div>
                <div>Stato fonte: {sourceValue(selectedItem, 'source_status', 'stato_documento', 'source') || 'non disponibile'}</div>
              </div>

              {selectedItem.riepilogo_iva && selectedItem.riepilogo_iva.length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <h4
                    style={{
                      margin: '0 0 12px 0',
                      fontSize: 13,
                      color: COLORS.textMuted,
                      fontWeight: 600,
                    }}
                  >
                    Riepilogo per Aliquota IVA
                  </h4>
                  <TableWrap>
                    <Table>
                      <thead>
                        <tr>
                          <Th>Aliquota</Th>
                          <Th align="right">Imponibile</Th>
                          <Th align="right">Imposta</Th>
                          <Th align="right">Totale</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedItem.riepilogo_iva.map((r, i) => (
                          <tr key={i}>
                            <Td>
                              {r.aliquota_iva}% {r.natura && `(${r.natura})`}
                            </Td>
                            <Td align="right" mono>{formatEuro(r.ammontare)}</Td>
                            <Td align="right" mono>{formatEuro(r.imposta)}</Td>
                            <Td align="right" mono>{formatEuro(asNumber(r.ammontare ?? r.imponibile) + asNumber(r.imposta))}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </TableWrap>
                </div>
              )}
            </PageSection>
            </div>
          )}

          {/* Lista Corrispettivi */}
          <PageSection
            title={`Elenco Corrispettivi (${corrispettivi.length})`}
            icon="📋"
            style={{ marginTop: 20, padding: 0 }}
            actions={<CopyLinkButton />}
          >
            {corrispettivi.length === 0 ? (
              <div style={{ padding: 40 }}>
                <PageEmpty icon="🧾" message="Nessun corrispettivo registrato per questo anno" />
                <div style={{ textAlign: 'center', marginTop: 16 }}>
                  <span style={{ color: COLORS.textMuted, fontSize: 14 }}>
                    I documenti vengono acquisiti esclusivamente dalla pagina Documenti.
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ padding: isMobile ? '0 10px 10px' : 0 }}>
                <ListaAdattiva
                  testId="corrispettivi-table"
                  dati={corrispettivi}
                  pageSize={50}
                  chiave={(c, i) => c.id || i}
                  colonne={[
                    {
                      key: 'data',
                      label: 'Data',
                      ruoloCard: 'titolo',
                      // Su mobile solo giorno/mese: l'anno è nel selettore
                      // globale e la data intera andava a capo su 3 righe
                      render: c =>
                        (isMobile ? formatDateGGMM(c.data) : formatDateIT(c.data)) || '-',
                      tdStyle: { fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap' },
                    },
                    {
                      // La matricola RT è quasi sempre identica su ogni riga:
                      // su mobile è omessa (resta nel dettaglio 👁), su
                      // desktop resta come colonna secondaria.
                      key: 'matricola_rt',
                      label: 'Matricola RT',
                      ruoloCard: 'omesso',
                      render: c => c.matricola_rt || '-',
                      tdStyle: { fontSize: 13, color: COLORS.textMuted },
                    },
                    {
                      key: 'pagato_contanti',
                      label: '💵 Cassa',
                      align: 'right',
                      mono: true,
                      ruoloCard: 'dettaglio',
                      iconaCard: '💵',
                      render: c => (
                        <span style={{ color: COLORS.success, fontWeight: 500 }}>
                          {formatEuro(c.pagato_contanti)}
                        </span>
                      ),
                    },
                    {
                      key: 'pagato_elettronico',
                      label: '💳 POS',
                      align: 'right',
                      mono: true,
                      ruoloCard: 'dettaglio',
                      iconaCard: '💳',
                      render: c => (
                        <span style={{ color: COLORS.info, fontWeight: 500 }}>
                          {formatEuro(c.pagato_elettronico)}
                        </span>
                      ),
                    },
                    {
                      key: 'totale',
                      label: 'Totale',
                      align: 'right',
                      mono: true,
                      ruoloCard: 'importo',
                      render: c => formatEuro(totaleItem(c)),
                      tdStyle: { fontWeight: 700 },
                    },
                    {
                      key: 'totale_iva',
                      label: 'IVA',
                      align: 'right',
                      mono: true,
                      ruoloCard: 'dettaglio',
                      iconaCard: null,
                      render: c => (
                        <span style={{ color: COLORS.warning, fontWeight: 500 }}>
                          {formatEuro(ivaItem(c))}
                        </span>
                      ),
                    },
                    {
                      key: 'azioni',
                      label: 'Azioni',
                      align: 'center',
                      ruoloCard: 'azioni',
                      render: c => (
                        <RowActions style={{ justifyContent: isMobile ? 'flex-end' : 'center' }}>
                          <RowActionButton
                            variant="info"
                            onClick={() => openDetail(c)}
                            title="Vedi dettaglio"
                            aria-label={`Vedi corrispettivo ${c.data || ''}`}
                            style={{ width: 'auto', minWidth: 60, padding: '0 10px', fontWeight: 700 }}
                          >
                            {hs.selected === c.data ? 'Aperto' : 'Vedi'}
                          </RowActionButton>
                        </RowActions>
                      ),
                    },
                  ]}
                />
              </div>
            )}
          </PageSection>
        </>
      )}
    </PageLayout>
  );
}
