import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, Info, LoaderCircle } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api';
import { Badge, Button, Card, PageHeader } from '../components/ds';
import { COLORS, formatDateIT } from '../lib/utils';

const PAGE_SIZE = 50;

const labelFiltro = params => {
  if (params.get('id')) return 'Caso selezionato';
  if (params.get('severita')) return `Severità: ${params.get('severita')}`;
  if (params.get('modulo')) return `Modulo: ${params.get('modulo')}`;
  return 'Tutti gli alert aperti';
};

export default function Alerts() {
  const [searchParams] = useSearchParams();
  const [alerts, setAlerts] = useState([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/api/alerts/lista', {
        params: {
          stato: 'aperto',
          severita: searchParams.get('severita') || undefined,
          modulo: searchParams.get('modulo') || undefined,
          alert_id: searchParams.get('id') || undefined,
          offset,
          limit: PAGE_SIZE,
        },
      });
      const rows = response.data?.alerts || [];
      setAlerts(previous => offset ? [...previous, ...rows] : rows);
      setTotal(response.data?.stats?.totale_filtrato ?? rows.length);
      setHasMore(Boolean(response.data?.pagination?.has_more));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Elenco alert non disponibile');
    } finally {
      setLoading(false);
    }
  }, [searchParams]);

  useEffect(() => { load(0); }, [load]);

  return (
    <div style={{ padding: 24 }}>
      <PageHeader title="Alert operativi" subtitle="Apri i casi reali e verifica quale prova o azione manca." />
      <Card style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div><strong>{labelFiltro(searchParams)}</strong> · {total} casi</div>
          {(searchParams.get('severita') || searchParams.get('modulo') || searchParams.get('id')) && <Link to="/dashboard/alerts">Rimuovi filtro</Link>}
        </div>
      </Card>

      {error && <div role="alert" style={{ marginTop: 16, color: COLORS.danger }}>{error}</div>}
      {!loading && !error && alerts.length === 0 && <Card style={{ marginTop: 16, padding: 24 }}>Nessun caso aperto per questo filtro.</Card>}
      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {alerts.map((alert, index) => {
          const detail = alert.dettaglio || alert.messaggio || 'Il sistema non ha fornito ulteriori dettagli.';
          const severity = alert.severita || (alert.priorita === 'alta' ? 'critical' : 'warning');
          return (
            <Card key={alert.id || `${alert.codice}-${index}`} style={{ padding: 18, borderLeft: `4px solid ${severity === 'critical' ? COLORS.danger : COLORS.warning}` }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                {severity === 'critical' ? <AlertTriangle color={COLORS.danger} size={20} /> : <Info color={COLORS.warning} size={20} />}
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <strong>{alert.titolo || alert.codice || 'Alert da verificare'}</strong>
                    <Badge variant={severity === 'critical' ? 'danger' : 'warning'}>{severity}</Badge>
                    {alert.modulo && <Badge variant="info">{alert.modulo}</Badge>}
                  </div>
                  <p style={{ margin: '8px 0', color: COLORS.textMuted }}>{detail}</p>
                  <small>{alert.created_at ? formatDateIT(alert.created_at) : 'Data non disponibile'}</small>
                  <div style={{ marginTop: 12 }}>
                    {alert.link ? (
                      <Link to={alert.link} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 700 }}><ExternalLink size={15} /> Apri il caso e verifica</Link>
                    ) : (
                      <span style={{ color: COLORS.textMuted, fontSize: 12 }}>Nessuna azione automatica consentita: verificare la fonte indicata nel dettaglio.</span>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      {loading && <div style={{ padding: 24, textAlign: 'center' }}><LoaderCircle className="is-spinning" /> Caricamento…</div>}
      {hasMore && !loading && <Button style={{ marginTop: 16 }} variant="secondary" onClick={() => load(alerts.length)}>Mostra altri casi</Button>}
    </div>
  );
}
