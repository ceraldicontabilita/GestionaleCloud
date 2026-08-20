import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Badge, Button, Card, StatCard } from '../components/ds';

const AREAS = [
  ['tutti', 'Tutti'],
  ['verbali', 'Verbali e PagoPA'],
  ['tributi_locali', 'TARI e tributi locali'],
  ['riscossione', 'Riscossione AdeR'],
  ['personale', 'Dimissioni e cessazioni'],
];

const AREA_LABELS = Object.fromEntries(AREAS);

const dateFor = item => {
  const metadata = item.parsed_metadata || {};
  return metadata.data_trasmissione || metadata.data_decorrenza_recesso ||
    item.document_date_display || item.acquired_at || null;
};

const identityFor = item => {
  const metadata = item.parsed_metadata || {};
  if (item.administrative_area === 'personale') {
    return [metadata.lavoratore_cognome, metadata.lavoratore_nome].filter(Boolean).join(' ') ||
      metadata.lavoratore_cf || 'Lavoratore da identificare';
  }
  if (item.administrative_area === 'tributi_locali') {
    return metadata.protocollo || metadata.codice_contribuente || 'Posizione TARI da verificare';
  }
  if (item.administrative_area === 'riscossione') {
    return (metadata.numeri_cartella || []).join(', ') || 'Atto AdeR da verificare';
  }
  return metadata.numero_verbale || metadata.codice_avviso || item.category_label || 'Verbale';
};

export default function AttiAmministrativi() {
  const { anno } = useAnnoGlobale();
  const [selectedYear, setSelectedYear] = useState('');
  const [area, setArea] = useState('tutti');
  const [search, setSearch] = useState('');
  const [payload, setPayload] = useState({ items: [], counts: {}, total: 0, requires_review: 0 });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 500 };
      if (area !== 'tutti') params.area = area;
      if (selectedYear) params.anno = selectedYear;
      if (search.trim()) params.search = search.trim();
      const response = await api.get('/api/documenti/amministrativi', { params });
      setPayload(response.data || { items: [], counts: {}, total: 0, requires_review: 0 });
    } catch (error) {
      setPayload({ items: [], counts: {}, total: 0, requires_review: 0 });
      toast.error('Atti amministrativi non disponibili', {
        description: error.response?.data?.detail || error.message,
      });
    } finally {
      setLoading(false);
    }
  }, [area, search, selectedYear]);

  useEffect(() => { load(); }, [load]);

  const openDocument = async item => {
    try {
      const response = await api.get(`/api/documenti/documento/${encodeURIComponent(item.id)}/download`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      toast.error('Documento non disponibile', { description: error.response?.data?.detail || error.message });
    }
  };

  const selectedAreaLabel = useMemo(() => AREA_LABELS[area], [area]);
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 16 }}>
        <StatCard label="Atti trovati" value={payload.total || 0} accent="primary" />
        <StatCard label="Verbali/PagoPA" value={payload.counts?.verbali || 0} accent="danger" />
        <StatCard label="TARI" value={payload.counts?.tributi_locali || 0} accent="warning" />
        <StatCard label="AdeR" value={payload.counts?.riscossione || 0} accent="primary" />
        <StatCard label="Dimissioni" value={payload.counts?.personale || 0} accent="accent" />
        <StatCard label="Da verificare" value={payload.requires_review || 0} accent="warning" />
      </div>

      <Card bodyStyle={{ padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'end' }}>
          <label>Area<br /><select value={area} onChange={event => setArea(event.target.value)} style={{ padding: 9 }}>
            {AREAS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <label>Anno<br /><select value={selectedYear} onChange={event => setSelectedYear(event.target.value)} style={{ padding: 9 }}>
            <option value="">Tutti</option>
            {[anno, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
              .filter((value, index, values) => value && values.indexOf(value) === index)
              .map(value => <option key={value} value={value}>{value}</option>)}
          </select></label>
          <label style={{ flex: '1 1 260px' }}>Cerca riferimento, CF, protocollo o file<br />
            <input value={search} onChange={event => setSearch(event.target.value)} style={{ padding: 9, width: '100%' }} placeholder="es. codice fiscale, verbale, contribuente" />
          </label>
          <Button variant="secondary" onClick={load} disabled={loading}>Aggiorna</Button>
        </div>
      </Card>

      <Card bodyStyle={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>{selectedAreaLabel} · {selectedYear || 'tutti gli anni'}</h3>
        <p style={{ color: '#475569' }}>
          Gli avvisi indicano un'obbligazione; PEC e moduli provano la trasmissione. Nessuno di questi documenti prova da solo il pagamento o chiude automaticamente un rapporto di lavoro.
        </p>
        {loading && <p>Caricamento…</p>}
        {!loading && payload.items.length === 0 && <p>Nessun atto importato per i filtri selezionati. Carica lo ZIP da “Carica documenti”.</p>}
        {payload.items.map(item => {
          const metadata = item.parsed_metadata || {};
          return <article key={item.id} style={{ padding: '14px 0', borderTop: '1px solid #e2e8f0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <div>
                <strong>{identityFor(item)}</strong>{' '}
                <Badge variant={metadata.requires_review ? 'warning' : 'info'}>{item.category_label || item.category}</Badge>
                {metadata.requires_review && <Badge variant="warning" style={{ marginLeft: 6 }}>Da verificare</Badge>}
                <div style={{ color: '#475569', marginTop: 5 }}>{item.filename}</div>
              </div>
              <Button size="sm" variant="secondary" onClick={() => openDocument(item)}>Apri PDF</Button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 8, marginTop: 10 }}>
              <span><small>Area</small><br /><strong>{AREA_LABELS[item.administrative_area] || item.administrative_area}</strong></span>
              <span><small>Data</small><br /><strong>{dateFor(item) || 'Non estratta'}</strong></span>
              <span><small>Provenienza</small><br /><strong>{item.source_context?.archive_path || item.source_label}</strong></span>
              <span><small>Stato documentale</small><br /><strong>{item.status || 'Da verificare'}</strong></span>
            </div>
            {item.administrative_area === 'personale' && <div style={{ marginTop: 8, color: '#334155' }}>
              CF {metadata.lavoratore_cf || 'non estratto'} · decorrenza {metadata.data_decorrenza_recesso || 'non estratta'} · modulo {metadata.codice_modulo || 'non estratto'}
            </div>}
            {item.administrative_area === 'tributi_locali' && <div style={{ marginTop: 8, color: '#334155' }}>
              Anno tributo {metadata.anno_tributo || 'da verificare'} · fase {metadata.fase || 'da verificare'} · contribuente {metadata.codice_contribuente || 'non estratto'}
            </div>}
          </article>;
        })}
      </Card>
    </div>
  );
}
