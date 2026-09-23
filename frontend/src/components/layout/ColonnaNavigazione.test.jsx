import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

let ruolo = { isAdmin: true };
vi.mock('../../contexts/AuthContext.jsx', () => ({ useAuth: () => ruolo }));

import ColonnaNavigazione from './ColonnaNavigazione';

const apri = percorso => render(
  <MemoryRouter initialEntries={[percorso]}>
    <ColonnaNavigazione />
  </MemoryRouter>,
);

describe('ColonnaNavigazione', () => {
  it('mostra tutti i gruppi con il loro titolo, senza menu a tendina', () => {
    ruolo = { isAdmin: true };
    const { container } = apri('/');
    for (const titolo of ['SI ENTRA', 'I DOCUMENTI', 'IL REGISTRO', 'LE PROVE', 'LA SINTESI', 'I CONTROLLI', 'IMPOSTAZIONI']) {
      expect(screen.getByText(titolo)).toBeTruthy();
    }
    expect(container.querySelector('select')).toBeNull();
  });

  it('accende una sola voce, quella della pagina aperta', () => {
    ruolo = { isAdmin: true };
    const { container } = apri('/contabilita/controllo');
    const attive = container.querySelectorAll('[aria-current="page"]');
    expect(attive).toHaveLength(1);
    expect(attive[0].textContent).toBe('Controllo mensile');
  });

  it('non mostra le voci riservate a chi non è amministratore', () => {
    ruolo = { isAdmin: false };
    apri('/');
    expect(screen.queryByText('Utenti')).toBeNull();
    expect(screen.queryByText('Situazione fiscale')).toBeNull();
    expect(screen.getByText('Fatture')).toBeTruthy();
  });
});
