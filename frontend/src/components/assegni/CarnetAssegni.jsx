import React, { useEffect, useMemo, useState } from 'react';
import api from '../../api';
import { COLORS, formatDateIT } from '../../lib/utils';
import { Badge, Button, ListaAdattiva, Tabs } from '../ds';

// Carnet BPM da 10 assegni, da «…1» a «…0»: li calcola il backend
// (app/services/carnet_assegni.py), qui si mostrano soltanto.
const FILTRI = [
  { key: 'tutti', label: 'Tutti' },
  { key: 'buchi', label: 'Con numeri mancanti' },
  { key: 'completi', label: 'Completi' },
];

const VARIANTE_STATO = {
  incassato: 'success',
  emesso: 'warning',
  assegnato: 'warning',
  parzialmente_assegnato: 'warning',
  annullato: 'danger',
  stornato: 'danger',
  scaduto: 'danger',
};

const coda = (numero) => String(numero || '').slice(-3);

export default function CarnetAssegni() {
  const [carnet, setCarnet] = useState([]);
  const [stato, setStato] = useState('caricamento');
  const [errore, setErrore] = useState('');
  const [filtro, setFiltro] = useState('tutti');

  const carica = async () => {
    setStato('caricamento');
    try {
      const res = await api.get('/api/assegni/carnet');
      setCarnet(res.data?.carnet || []);
      setStato('pronto');
    } catch (err) {
      setErrore(err?.response?.data?.detail || err?.message || 'errore sconosciuto');
      setStato('errore');
    }
  };

  useEffect(() => { carica(); }, []);

  const righe = useMemo(() => carnet.filter((c) => {
    if (filtro === 'buchi') return c.mancanti.length > 0;
    if (filtro === 'completi') return c.mancanti.length === 0;
    return true;
  }), [carnet, filtro]);

  const conBuchi = carnet.filter((c) => c.mancanti.length > 0).length;

  if (stato === 'errore') {
    return (
      <div role="alert" style={{ padding: 16, background: COLORS.dangerLight, color: COLORS.danger }}>
        <strong>Carnet non caricati.</strong> {errore}{' '}
        <Button variant="secondary" size="sm" onClick={carica}>Riprova</Button>
      </div>
    );
  }
  if (stato === 'caricamento') {
    return <div style={{ textAlign: 'center', padding: 40 }}>Caricamento carnet…</div>;
  }

  return (
    <div data-testid="carnet-assegni">
      <p style={{ margin: '0 0 12px', color: COLORS.textMuted }}>
        {carnet.length} carnet da 10 assegni, {conBuchi} con numeri che l'archivio non conosce ancora.
        Un numero mancante è un assegno di cui non abbiamo né la scheda né il movimento in banca.
      </p>
      <Tabs items={FILTRI} value={filtro} onChange={setFiltro} style={{ marginBottom: 12 }} />
      <ListaAdattiva
        testId="carnet-table"
        dati={righe}
        pageSize={200}
        resetKey={filtro}
        chiave={(c) => c.carnet_id}
        colonne={[
          {
            key: 'carnet_id',
            label: 'Carnet',
            ruoloCard: 'titolo',
            mono: true,
            render: (c) => `${c.primo} – ${coda(c.ultimo)}`,
          },
          {
            key: 'in_archivio',
            label: 'In archivio',
            ruoloCard: 'importo',
            align: 'right',
            render: (c) => `${c.in_archivio}/10`,
          },
          {
            key: 'mancanti',
            label: 'Numeri mancanti',
            ruoloCard: 'dettaglio',
            render: (c) => (c.mancanti.length
              ? c.mancanti.map(coda).join(', ')
              : 'nessuno'),
          },
          {
            key: 'stati',
            label: 'Stati',
            ruoloCard: 'dettaglio',
            render: (c) => (
              <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                {Object.entries(c.stati).map(([s, n]) => (
                  <Badge key={s} variant={VARIANTE_STATO[s] || 'neutral'}>{`${s.replace('_', ' ')} ${n}`}</Badge>
                ))}
              </span>
            ),
          },
          {
            key: 'ultima_data',
            label: 'Ultimo uso',
            ruoloCard: 'sottotitolo',
            render: (c) => formatDateIT(c.ultima_data),
          },
        ]}
      />
    </div>
  );
}
