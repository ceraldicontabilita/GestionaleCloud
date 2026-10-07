import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { MenuOperazioni } from './MenuOperazioni';

const apri = voci => render(<MemoryRouter><MenuOperazioni voci={voci} /></MemoryRouter>);

describe('MenuOperazioni', () => {
  it('tiene le operazioni chiuse dietro un solo bottone e le esegue al clic', () => {
    const riprocessa = vi.fn();
    apri([
      { id: 'op-riprocessa', label: 'Riprocessa collegamenti', onClick: riprocessa },
      { separatore: true },
      { id: 'op-svuota', label: 'Svuota', onClick: vi.fn(), pericolosa: true },
    ]);
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(screen.getByTestId('menu-operazioni-btn'));
    expect(screen.getByRole('menu')).toBeTruthy();
    expect(screen.getAllByRole('menuitem').map(v => v.textContent)).toEqual(['Riprocessa collegamenti', 'Svuota']);
    fireEvent.click(screen.getByTestId('op-riprocessa'));
    expect(riprocessa).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('non esegue una voce disabilitata e si chiude con Esc', () => {
    const mai = vi.fn();
    apri([{ id: 'op-stampa', label: 'Stampa', onClick: mai, disabled: true }]);
    fireEvent.click(screen.getByTestId('menu-operazioni-btn'));
    fireEvent.click(screen.getByTestId('op-stampa'));
    expect(mai).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('una voce con `to` e’ un link interno', () => {
    apri([{ id: 'op-learning', label: 'Dashboard Learning', to: '/learning-machine' }]);
    fireEvent.click(screen.getByTestId('menu-operazioni-btn'));
    expect(screen.getByTestId('op-learning').getAttribute('href')).toBe('/learning-machine');
  });

  it('senza voci non disegna niente', () => {
    const { container } = apri([]);
    expect(container.innerHTML).toBe('');
  });
});
