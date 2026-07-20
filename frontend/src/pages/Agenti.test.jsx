import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import AgentiPage from './Agenti';

const conferma = vi.fn(async () => true);

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ isAdmin: true }) }));
vi.mock('../components/ui/ConfirmDialog', () => ({ useConfirm: () => conferma }));

const DECISIONE = {
  decision_id: 'decisione-test-1',
  timestamp: '2026-07-20T10:00:00+00:00',
  agent: 'AgenteTest',
  objective: 'Verificare una proposta sintetica',
  explanation: 'Nessun dato reale',
  recommended_action: { type: 'payment', description: 'Controllare il pagamento' },
  confidence: 0.8,
  financial_impact: 50,
  risk_level: 'high',
  autonomy_level: 'L3',
  execution_status: 'pending_approval',
  policy_reasons: ['azione_con_approvazione_umana_obbligatoria'],
  version: 3,
  occurrence_count: 4,
  versioni_storiche: 2,
  input_sources: [{ type: 'typed_service', service: 'tesoreria_snapshot' }],
  rule_ids: ['TREASURY-OVERDUE-001', 'HUMAN-APPROVAL-001'],
  approver_role: 'admin',
};

const CASH_FLOW = {
  versione_regole: 'CF13W-001',
  liquidita_iniziale: 3000,
  qualita_dati: { copertura_percentuale: 80, record_esclusi: 2 },
  scenari: [{
    nome: 'base', fattore_entrate: 1, fattore_uscite: 1,
    saldo_minimo: 2500, saldo_finale: 2800,
    settimane: [{ settimana: 1, dal: '2026-07-20', al: '2026-07-26', entrate: 500, uscite: 200, saldo_finale: 3300 }],
  }],
};

function rispostaGet(url) {
  if (url.includes('/cash-flow-13-settimane')) return Promise.resolve({ data: CASH_FLOW });
  if (url.includes('/automazioni/stato')) return Promise.resolve({ data: { sospese: false, modalita: 'shadow' } });
  if (url.includes('/stato')) return Promise.resolve({ data: { agenti: [] } });
  if (url.includes('/segnalazioni')) return Promise.resolve({ data: { segnalazioni: [] } });
  if (url.includes('/decisioni')) return Promise.resolve({ data: { decisioni: [DECISIONE] } });
  return Promise.resolve({ data: {} });
}

describe('Agenti AI supervisionati', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, '', '/');
    api.get.mockImplementation(rispostaGet);
    api.post.mockResolvedValue({ data: { status: 'ok' } });
  });

  it('mostra la decisione e chiarisce che approvare non significa eseguire', async () => {
    render(<AgentiPage />);
    fireEvent.click(await screen.findByTestId('tab-agenti-decisioni'));

    expect(await screen.findByText('Verificare una proposta sintetica')).toBeInTheDocument();
    expect(screen.getByText('Versione 3')).toBeInTheDocument();
    expect(screen.getByText('4 rilevazioni')).toBeInTheDocument();
    expect(screen.getByText('2 versioni precedenti')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Fonti, regole e approvazione'));
    expect(screen.getByText(/Servizio verificato: tesoreria_snapshot/)).toBeInTheDocument();
    expect(screen.getByText(/TREASURY-OVERDUE-001/)).toBeInTheDocument();
    expect(screen.getByText(/Ruolo approvatore:/)).toBeInTheDocument();
    expect(screen.getByText("L'approvazione non esegue l'azione.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approva proposta' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/agenti/decisioni/decisione-test-1/approva',
      {},
    ));
  });

  it('ferma le automazioni soltanto dopo conferma', async () => {
    render(<AgentiPage />);
    fireEvent.click(await screen.findByTestId('btn-stop-automazioni'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/agenti/automazioni/ferma'));
    expect(conferma).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Ferma tutte le automazioni AI',
      variant: 'danger',
    }));
  });

  it('mostra il cash flow con copertura e senza azioni di pagamento', async () => {
    render(<AgentiPage />);
    fireEvent.click(await screen.findByTestId('tab-agenti-cash-flow'));

    expect(await screen.findByText('Scenario base')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText(/non prepara né esegue pagamenti/i)).toBeInTheDocument();
  });
});
