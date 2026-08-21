import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AnnoProvider, AnnoSelector, useAnnoGlobale } from './AnnoContext';

function CurrentYear() {
  const { anno } = useAnnoGlobale();
  return <span data-testid="anno-corrente">{anno}</span>;
}

describe('AnnoContext globale', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('mantiene il filtro di consultazione salvato dall utente', () => {
    localStorage.setItem('annoGlobale', '2025');
    render(<AnnoProvider><CurrentYear /></AnnoProvider>);

    expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2025');
    expect(localStorage.getItem('annoGlobale')).toBe('2025');
  });

  it('il selettore cambia soltanto l anno di consultazione locale', () => {
    localStorage.setItem('annoGlobale', '2026');
    render(<AnnoProvider><AnnoSelector /><CurrentYear /></AnnoProvider>);
    expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2026');

    fireEvent.change(screen.getByTestId('anno-globale-selector'), { target: { value: '2025' } });

    expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2025');
    expect(localStorage.getItem('annoGlobale')).toBe('2025');
  });
});
