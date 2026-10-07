import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api', () => ({ default: { get: vi.fn() } }));

import api from '../../api';
import Scadenzario from './Scadenzario';

const RISPOSTA = {
  voci: [
    {
      chiave: 'sezione_erario|1001|2024|2', codice: '1001', periodo: '02/2024', scadenza: '2024-03-18',
      stato: 'RAVVEDUTO', stato_label: 'Pagato in ritardo, ravveduto', pagato_cents: 170711, ultimo_pagamento: '2024-03-22',
      pagamenti: [{ data: '2024-03-22', protocollo: '24032212345678901/000001', importo_cents: 170711, giorni_ritardo: 4, motivazione: 'pagato il 22/03/2024' }],
      dichiarato_770: [{ rigo: 'ST5', ritenute_operate_cents: 170664, importo_versato_cents: 170711, data_versamento: '2024-03-22', ravvedimento: true, fonte: { anno_imposta: 2024 } }],
      confronto_770: { importo: 'COINCIDE', differenza_cents: 0, ravvedimento_dichiarato: true, ravvedimento_coerente: true },
    },
    {
      chiave: 'sezione_erario|1040|2023|9', codice: '1040', periodo: '09/2023', scadenza: '2023-10-16',
      stato: 'DICHIARATO_770_SENZA_QUIETANZA', stato_label: 'Dichiarato nel 770, quietanza non in archivio',
      pagato_cents: 0, ultimo_pagamento: null, pagamenti: [],
      motivazione: 'dichiarato nel 770 (18161244457 - 0000003, rigo ST5): nessuna quietanza in archivio per questo codice e periodo',
      dichiarato_770: [{ rigo: 'ST5', ritenute_operate_cents: 118000, importo_versato_cents: 160414, data_versamento: '2023-12-18', ravvedimento: true, fonte: { anno_imposta: 2023 } }],
      confronto_770: { importo: 'QUIETANZA_MANCANTE', differenza_cents: -160414, ravvedimento_dichiarato: true, ravvedimento_coerente: null },
    },
  ],
  per_stato: [{ id: 'DICHIARATO_770_SENZA_QUIETANZA', label: 'Dichiarato nel 770, quietanza non in archivio', n: 1 }],
  anni: [2024, 2023],
};

describe('Scadenzario con il quadro ST del 770', () => {
  it('mostra la riga del 770 accanto alla voce e l attesa senza quietanza', async () => {
    api.get.mockResolvedValue({ data: RISPOSTA });
    render(<Scadenzario anno="" stato="" imposta={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('scadenzario')).toBeTruthy());
    const righe = screen.getAllByTestId('dichiarato-770');
    expect(righe).toHaveLength(2);
    expect(righe[0].textContent).toContain('770 2024 rigo ST5');
    expect(righe[0].textContent).toContain('ravvedimento (X)');
    expect(righe[0].textContent).toContain('coincide con le quietanze');
    expect(righe[1].textContent).toContain('quietanza non in archivio');
    expect(screen.getByText('Dichiarato nel 770, quietanza non in archivio', { selector: 'span, div, strong, [class]' })).toBeTruthy();
    // la voce senza pagamenti si apre e mostra la motivazione
    screen.getByTestId('scad-sezione_erario|1040|2023|9').click();
    await waitFor(() => expect(screen.getByText(/nessuna quietanza in archivio per questo codice e periodo/)).toBeTruthy());
  });
});
