import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw, XCircle } from 'lucide-react';

import api from '../../api';
import { Badge, Button, Card, StatCard } from '../ds';
import { COLORS, BORDER_RADIUS } from '../../lib/utils';
import { queryPeriodo } from '../../lib/periodoCommercialista';

const META = {
  dato_esistente: { label: 'DATO ESISTENTE', variant: 'success', Icon: CheckCircle2 },
  dato_incompleto: { label: 'DATO INCOMPLETO', variant: 'warning', Icon: AlertTriangle },
  dato_mancante: { label: 'DATO MANCANTE', variant: 'danger', Icon: XCircle },
};

const dataOra = valore => valore
  ? new Date(valore).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
  : '—';

export default function ChecklistDocumenti({ periodo }) {
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState('');
  const [filtro, setFiltro] = useState('tutti');

  const aggiorna = useCallback(async ({ silenzioso = false } = {}) => {
    if (!periodo?.valido) return;
    if (!silenzioso) setLoading(true);
    setErrore('');
    try {
      const rotta = `${periodo.anno}/${periodo.meseRotta}${queryPeriodo(periodo)}`;
      const response = await api.get(`/api/commercialista/checklist-documenti/${rotta}`);
      setDati(response.data);
    } catch (e) {
      setErrore(e.response?.data?.detail || 'Checklist non disponibile. Gli altri dati della pagina restano utilizzabili.');
    } finally {
      if (!silenzioso) setLoading(false);
    }
  }, [periodo]);

  useEffect(() => {
    aggiorna();
    const timer = window.setInterval(() => aggiorna({ silenzioso: true }), 60_000);
    return () => window.clearInterval(timer);
  }, [aggiorna]);

  const items = useMemo(() => {
    const elenco = dati?.items || [];
    return filtro === 'tutti' ? elenco : elenco.filter(item => item.stato === filtro);
  }, [dati, filtro]);

  if (!periodo?.valido) return null;

  return (
    <Card
      title="Cosa esiste già e cosa chiedere al commercialista"
      icon={<CheckCircle2 size={16} aria-hidden="true" />}
      style={{ marginBottom: 20 }}
    >
      <div data-testid="checklist-documenti-commercialista">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, color: COLORS.text, fontWeight: 700 }}>
              Prima controlliamo Gestionale e Drive. Si richiede soltanto ciò che manca o è incompleto.
            </p>
            <p style={{ margin: '4px 0 0', color: COLORS.textMuted, fontSize: 13 }}>
              Aggiornamento automatico ogni minuto · Ultimo controllo: {dataOra(dati?.aggiornato_il)}
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => aggiorna()}
            disabled={loading}
            iconLeft={<RefreshCw size={15} aria-hidden="true" />}
            data-testid="aggiorna-checklist-documenti"
          >
            {loading ? 'Controllo…' : 'Aggiorna ora'}
          </Button>
        </div>

        {errore && (
          <div role="alert" style={{ marginTop: 12, padding: 10, borderRadius: BORDER_RADIUS.md, background: COLORS.dangerLight, color: COLORS.danger }}>
            {errore}
          </div>
        )}

        {dati && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, margin: '16px 0' }}>
              <StatCard label="Dati esistenti" value={dati.riepilogo?.dato_esistente || 0} accent="success" />
              <StatCard label="Dati incompleti" value={dati.riepilogo?.dato_incompleto || 0} accent="warning" />
              <StatCard label="Dati mancanti" value={dati.riepilogo?.dato_mancante || 0} accent="danger" />
            </div>

            <div role="group" aria-label="Filtra checklist documenti" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              {[
                ['tutti', 'Tutti'],
                ['dato_esistente', 'Esistenti'],
                ['dato_incompleto', 'Incompleti'],
                ['dato_mancante', 'Mancanti'],
              ].map(([value, label]) => (
                <Button key={value} size="sm" variant={filtro === value ? 'primary' : 'secondary'} onClick={() => setFiltro(value)}>
                  {label}
                </Button>
              ))}
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              {items.map(item => {
                const meta = META[item.stato] || META.dato_mancante;
                const Icon = meta.Icon;
                return (
                  <article
                    key={item.key}
                    data-testid={`checklist-${item.key}`}
                    style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: 14, background: COLORS.card }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                      <div style={{ flex: '1 1 420px', minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <Icon size={17} color={COLORS[meta.variant] || COLORS.textMuted} aria-hidden="true" />
                          <strong>{item.richiesto}</strong>
                          <Badge variant={meta.variant} style={{ textTransform: 'none' }}>{meta.label}</Badge>
                        </div>
                        <div style={{ marginTop: 7, color: COLORS.text, fontSize: 14 }}>{item.domanda}</div>
                        <div style={{ marginTop: 5, color: COLORS.textMuted, fontSize: 13 }}>{item.risposta}</div>
                        {item.nota && <div style={{ marginTop: 5, color: COLORS.warning, fontSize: 12 }}>{item.nota}</div>}
                        {item.parti && (
                          <div style={{ marginTop: 5, fontSize: 12, color: COLORS.textMuted }}>
                            Parti documentali rilevate: {item.parti.presenti}/{item.parti.totali}
                          </div>
                        )}
                      </div>
                      {item.route && (
                        <a href={item.route} style={{ color: COLORS.primary, fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          Apri fonte <ExternalLink size={13} aria-hidden="true" />
                        </a>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                      {(item.fonti || []).length ? item.fonti.map((fonte, index) => (
                        <span key={`${fonte.etichetta}-${index}`} style={{ background: COLORS.gray[100], color: COLORS.text, borderRadius: 999, padding: '4px 8px', fontSize: 12 }}>
                          {fonte.etichetta}: <b>{fonte.conteggio}</b>
                        </span>
                      )) : (
                        <span style={{ color: COLORS.textMuted, fontSize: 12 }}>Nessuna fonte trovata nel periodo selezionato.</span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
