import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { Button, Badge, Card } from './ds';
import { COLORS } from '../lib/utils';

/**
 * In Admin mostriamo soltanto la configurazione tecnica dell'integrazione.
 * Vendite, accrediti e commissioni sono dati operativi e vivono nella
 * sezione SumUp di Prima Nota, dove sono collegati alle relative prove.
 */
export default function PannelloSumUp() {
  const navigate = useNavigate();
  const [stato, setStato] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .get('/api/sumup/stato')
      .then(({ data }) => {
        if (active) setStato(data || null);
      })
      .catch(() => {
        if (active) {
          setStato({
            connessione_ok: false,
            messaggio: 'Stato della connessione non disponibile.',
          });
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card
      title="SumUp - collegamento tecnico"
      actions={
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate('/prima-nota#sezione=sumup')}
        >
          Apri Prima Nota SumUp
        </Button>
      }
    >
      <p style={{ color: COLORS.textSubtle, fontSize: 13, marginTop: 0 }}>
        Qui verifichi soltanto che l'integrazione sia configurata. Vendite,
        accrediti e commissioni sono consultabili in Prima Nota SumUp.
      </p>

      {loading ? (
        <div style={{ fontSize: 13, color: COLORS.textSubtle }}>
          Verifica collegamento in corso...
        </div>
      ) : (
        <div data-testid="sumup-connection-status">
          <Badge variant={stato?.connessione_ok ? 'success' : 'danger'}>
            {stato?.connessione_ok ? 'Collegato' : 'Non collegato'}
          </Badge>
          <div style={{ fontSize: 13, marginTop: 8 }}>
            {stato?.esercente && (
              <div>
                Esercente: <b>{stato.esercente}</b>
              </div>
            )}
            <div>
              Chiave: {stato?.chiave_visibile || '-'} - Merchant:{' '}
              {stato?.merchant_code || '-'}
            </div>
            {stato?.messaggio && (
              <div
                style={{
                  marginTop: 4,
                  color: stato.connessione_ok ? COLORS.success : COLORS.danger,
                }}
              >
                {stato.messaggio}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
