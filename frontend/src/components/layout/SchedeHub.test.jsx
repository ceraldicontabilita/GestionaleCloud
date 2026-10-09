import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

let ruolo = { isAdmin: true };
vi.mock('../../contexts/AuthContext.jsx', () => ({ useAuth: () => ruolo }));

import SchedeHub from './SchedeHub';

function Dove() {
  const { pathname } = useLocation();
  return <output data-testid="dove">{pathname}</output>;
}

const apri = percorso => render(
  <MemoryRouter initialEntries={[percorso]}>
    <SchedeHub />
    <Routes><Route path="*" element={<Dove />} /></Routes>
  </MemoryRouter>,
);

describe('SchedeHub', () => {
  it('mostra tutte le schede del hub e accende quella aperta', () => {
    ruolo = { isAdmin: true };
    apri('/riconciliazione/assegni');
    const schede = screen.getAllByRole('tab');
    expect(schede.map(s => s.textContent)).toContain('Riepilogo');
    expect(schede.map(s => s.textContent)).toContain('Regole banca');
    expect(screen.getByRole('tab', { name: 'Assegni' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: 'Riepilogo' }).getAttribute('aria-selected')).toBe('false');
  });

  it('cliccando una scheda si va al suo indirizzo', () => {
    ruolo = { isAdmin: true };
    apri('/fatture');
    fireEvent.click(screen.getByRole('tab', { name: 'Corrispettivi' }));
    expect(screen.getByTestId('dove').textContent).toBe('/fatture/corrispettivi');
  });

  it('non disegna niente fuori da un hub o con una scheda sola', () => {
    ruolo = { isAdmin: true };
    apri('/fornitori');
    expect(screen.queryByTestId('schede-hub')).toBeNull();
  });

  it('nasconde le schede riservate a chi non è amministratore', () => {
    ruolo = { isAdmin: false };
    apri('/scadenze');
    expect(screen.queryByRole('tab', { name: 'Situazione fiscale' })).toBeNull();
    expect(screen.getByRole('tab', { name: 'F24' })).toBeTruthy();
  });
});
