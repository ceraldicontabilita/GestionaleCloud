import React from 'react';
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SupplierModal } from './Fornitori';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
afterEach(cleanup);

describe('metodo pagamento in anagrafica', () => {
  it('mostra Da impostare e salva gli altri dati senza inventare Banca', () => {
    const save = vi.fn();
    render(<SupplierModal isOpen onClose={() => {}} onSave={save} saving={false}
      supplier={{ id: 's1', ragione_sociale: 'Fornitore prova', metodo_pagamento: '', email: 'prima@example.test' }} />);
    expect(screen.getByDisplayValue('Da impostare').value).toBe('');
    fireEvent.change(screen.getByDisplayValue('prima@example.test'), { target: { value: 'dopo@example.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salva' }));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ metodo_pagamento: '', email: 'dopo@example.test' }));
  });
  it('il valore legacy visualizzato coincide con quello salvato', () => {
    const save = vi.fn();
    render(<SupplierModal isOpen onClose={() => {}} onSave={save} saving={false}
      supplier={{ id: 's1', ragione_sociale: 'Fornitore prova', metodo_pagamento: 'bonifico' }} />);
    expect(screen.getByDisplayValue('Banca').value).toBe('banca');
    fireEvent.click(screen.getByRole('button', { name: 'Salva' }));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ metodo_pagamento: 'banca' }));
  });
});
