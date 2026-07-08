import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';
import { PageLayout, PageSection } from '../components/PageLayout';
import { button, formatEuro, badge, COLORS } from '../lib/utils';

export default function DettaglioVerbale() {
  const { numeroVerbale, prefisso, numero } = useParams();
  const navigate = useNavigate();
  const verbaleId = prefisso && numero ? `${prefisso}/${numero}` : numeroVerbale;
  const [verbale, setVerbale] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/api/verbali-noleggio/dettaglio/${verbaleId}`);
        if (alive) setVerbale(res.data || null);
      } catch (e) {
        if (alive) setError(e.response?.data?.detail || e.message || 'Errore caricamento verbale');
      } finally {
        if (alive) setLoading(false);
      }
    }

    load();
    return () => {
      alive = false;
    };
  }, [verbaleId]);

  if (loading) {
    return (
      <PageLayout title="Dettaglio verbale" subtitle={`Caricamento verbale ${verbaleId}`}>
        <div style={{ padding: 32, color: COLORS.textMuted }}>Caricamento...</div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout title="Dettaglio verbale" subtitle={`Verbale ${verbaleId}`}>
        <PageSection title="Errore">
          <div style={{ color: COLORS.danger, marginBottom: 16 }}>{error}</div>
          <button style={button('primary')} onClick={() => navigate(-1)}>
            Torna indietro
          </button>
        </PageSection>
      </PageLayout>
    );
  }

  const pdfCount = verbale?.pdf_disponibili?.length || 0;
  const stato = verbale?.stato_pagamento || verbale?.stato || 'n/d';

  return (
    <PageLayout
      title="Dettaglio verbale"
      subtitle={`Verbale ${verbale?.numero_verbale || verbaleId}`}
      actions={
        <button style={button('secondary')} onClick={() => navigate(-1)}>
          Indietro
        </button>
      }
    >
      <PageSection title="Riepilogo">
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div><strong>Numero</strong><div>{verbale?.numero_verbale || verbaleId}</div></div>
          <div><strong>Fornitore</strong><div>{verbale?.fornitore || '-'}</div></div>
          <div><strong>Targa</strong><div>{verbale?.targa || '-'}</div></div>
          <div><strong>Stato</strong><div><span style={badge(stato === 'pagato' ? 'success' : stato === 'sospeso' ? 'warning' : 'neutral')}>{stato}</span></div></div>
          <div><strong>Importo</strong><div>{formatEuro(verbale?.importo || verbale?.totale || 0)}</div></div>
          <div><strong>PDF disponibili</strong><div>{pdfCount}</div></div>
        </div>
      </PageSection>

      <PageSection title="Note">
        <div style={{ color: COLORS.textMuted, lineHeight: 1.6 }}>
          {verbale?.note || 'Nessuna nota disponibile per questo verbale.'}
        </div>
      </PageSection>

      {pdfCount > 0 && (
        <PageSection title="Documenti PDF">
          <div style={{ display: 'grid', gap: 8 }}>
            {verbale.pdf_disponibili.map((pdf, idx) => (
              <div
                key={pdf.id || idx}
                style={{
                  padding: 12,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 8,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>{pdf.nome || pdf.filename || `PDF ${idx + 1}`}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted }}>{pdf.descrizione || 'Documento associato al verbale'}</div>
                </div>
                {pdf.url ? (
                  <a href={pdf.url} target="_blank" rel="noreferrer" style={button('outline')}>
                    Apri
                  </a>
                ) : (
                  <span style={badge('neutral')}>Disponibile</span>
                )}
              </div>
            ))}
          </div>
        </PageSection>
      )}
    </PageLayout>
  );
}
