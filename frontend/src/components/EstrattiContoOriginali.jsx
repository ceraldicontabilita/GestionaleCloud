import React, { useEffect, useState } from 'react';
import api from '../api';
import { Card, ListaAdattiva } from './ds';
import { VisoreOriginale } from './ApriOriginale';
import { urlOriginale } from '../lib/vista';
import { COLORS } from '../lib/utils';

// Gli estratti conto caricati (banca e carta Nexi), con il file originale da
// rivedere e scaricare. Prima l'import teneva solo i movimenti: il file
// caricato non si poteva piu' riavere.
const formatoData = valore => {
  if (!valore) return '—';
  const d = new Date(valore);
  return Number.isNaN(d.getTime()) ? String(valore) : d.toLocaleDateString('it-IT');
};

const euro = valore => (valore == null
  ? '—'
  : `€ ${Number(valore).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

export default function EstrattiContoOriginali() {
  const [estratti, setEstratti] = useState([]);
  const [errore, setErrore] = useState(null);
  const [aperto, setAperto] = useState(null);

  useEffect(() => {
    api.get('/api/estratto-conto-movimenti/originali')
      .then(r => setEstratti(r.data?.estratti || []))
      .catch(e => setErrore(e.response?.data?.detail || 'Elenco degli estratti non disponibile'));
  }, []);

  return (
    <Card title="Estratti conto caricati">
      <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
        Il file originale di ogni estratto importato, banca e carta Nexi: si apre e si scarica così
        come è stato caricato.
      </p>
      {errore && <div role="status" style={{ color: COLORS.danger, fontSize: 13 }}>{errore}</div>}
      {!errore && estratti.length === 0 && (
        <div style={{ fontSize: 13, color: COLORS.textMuted }}>Nessun estratto conto caricato.</div>
      )}
      {estratti.length > 0 && (
        <ListaAdattiva
          testId="estratti-originali"
          dati={estratti}
          pageSize={20}
          colonne={[
            { key: 'nome', label: 'File', ruoloCard: 'titolo' },
            { key: 'fonte', label: 'Fonte', ruoloCard: 'sottotitolo',
              render: v => (v.tipo === 'nexi' ? 'Carta Nexi' : 'Banca') },
            { key: 'data', label: 'Data', ruoloCard: 'dettaglio', render: v => formatoData(v.data) },
            { key: 'totale', label: 'Addebito', ruoloCard: 'dettaglio', mono: true,
              render: v => (v.tipo === 'nexi' ? euro(v.totale) : '—') },
            { key: 'apri', label: '', ruoloCard: 'azioni',
              render: v => (
                <button
                  type="button"
                  data-testid={`estratto-originale-${v.id}`}
                  onClick={() => setAperto(v)}
                  aria-label={`Vedi e scarica ${v.nome}`}
                  style={{
                    minHeight: 40, padding: '4px 12px', border: `1px solid ${COLORS.primary}`,
                    borderRadius: 6, background: COLORS.card, color: COLORS.primary,
                    fontWeight: 700, fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Vedi / Scarica
                </button>
              ) },
          ]}
        />
      )}
      {aperto && (
        <VisoreOriginale
          title={aperto.nome || 'Estratto conto'}
          subtitle={aperto.tipo === 'nexi' ? `Carta Nexi · ${aperto.periodo || ''}` : 'Banca'}
          url={urlOriginale({ tipo: 'estratto', id: aperto.id })}
          documentType="estratto_conto"
          onClose={() => setAperto(null)}
          testIdPrefix="estratto-originale-viewer"
        />
      )}
    </Card>
  );
}
