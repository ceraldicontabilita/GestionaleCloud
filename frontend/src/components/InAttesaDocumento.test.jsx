import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import InAttesaDocumento from './InAttesaDocumento';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const risposta = {
  data: {
    totale: 1,
    effetto_sul_saldo: -1119.48,
    gia_collegati_da_allineare: 2,
    movimenti: [{
      id: 'ec-leasys', data: '2026-08-07', tipo: 'uscita', importo: 1119.48,
      descrizione: 'ADDEBITO RIB LEASYS ITALIA SPA',
      strumento_bancario: { codice: 'riba', label: 'RiBa' },
      motivo_sospensione: 'Importo al centesimo, ma 2 fatture sono candidate',
      candidati: [
        { id: 'fatt-1', numero: '0000202611306589', fornitore: 'Leasys Italia S.p.A', importo: 1119.48, data: '2026-08-07' },
        { id: 'fatt-2', numero: '0000202610458640', fornitore: 'Leasys Italia S.p.A', importo: 1119.48, data: '2026-07-07' },
      ],
    }],
  },
};

describe('Coda operativa Prima Nota Banca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(risposta);
    api.post.mockResolvedValue({ data: { success: true } });
  });

  it('Agganciali apre direttamente le operazioni esatte e mostra il motivo del dubbio', async () => {
    render(<InAttesaDocumento anno={2026} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agganciali' }));

    expect(await screen.findByLabelText('Operazioni da agganciare')).toBeInTheDocument();
    expect(screen.getByText(/ADDEBITO RIB LEASYS/)).toBeInTheDocument();
    expect(screen.getByText(/Importo al centesimo, ma 2 fatture/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Collega questa fattura' })).toHaveLength(2);
  });

  it('collega il candidato scelto al movimento reale e aggiorna la pagina', async () => {
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<InAttesaDocumento anno={2026} onRicarica={onRicarica} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agganciali' }));
    fireEvent.click((await screen.findAllByRole('button', { name: 'Collega questa fattura' }))[0]);

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/operazioni-da-confermare/smart/riconcilia-manuale',
      {
        movimento_id: 'ec-leasys',
        tipo: 'fattura',
        associazioni: [{ id: 'fatt-1' }],
        note: 'Collegamento dalla coda Prima Nota Banca',
      },
    ));
    expect(onRicarica).toHaveBeenCalledWith({ silent: true });
  });

  it('con coda vuota non dichiara una copertura completa dell estratto conto', async () => {
    api.get.mockResolvedValue({
      data: { totale: 0, effetto_sul_saldo: 0, movimenti: [] },
    });

    render(<InAttesaDocumento anno={2026} />);

    expect(await screen.findByText('Nessun movimento presente nella coda documenti da collegare.'))
      .toBeInTheDocument();
    expect(screen.queryByText(/copre tutto l'estratto conto/i)).not.toBeInTheDocument();
  });

  it('rende navigabili anche i movimenti oltre i primi cento', async () => {
    const movimenti = Array.from({ length: 101 }, (_, indice) => ({
      id: `ec-${indice}`,
      data: '2026-08-07',
      tipo: 'uscita',
      importo: indice + 1,
      descrizione: indice === 100 ? 'MOVIMENTO CENTOUNO' : `Movimento ${indice + 1}`,
      motivo_sospensione: 'Documento ancora da individuare',
      candidati: [],
    }));
    api.get.mockResolvedValue({
      data: { totale: movimenti.length, effetto_sul_saldo: -5151, movimenti },
    });

    render(<InAttesaDocumento anno={2026} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agganciali' }));

    expect(screen.queryByText('MOVIMENTO CENTOUNO')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mostra altri 1 movimenti' }));
    expect(screen.getByText('MOVIMENTO CENTOUNO')).toBeInTheDocument();
  });
});
