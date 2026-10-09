import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import { AuthProvider, useAuth } from './AuthContext';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  setAuthToken: token => localStorage.setItem('auth_token', token),
  clearAuthToken: () => localStorage.removeItem('auth_token'),
  getAuthToken: () => localStorage.getItem('auth_token'),
}));

function Probe() {
  const { logout, role, isAdmin, canWrite } = useAuth();
  const [errore, setErrore] = useState(false);
  return (
    <div>
      <span data-testid="role">{role}</span>
      <span data-testid="admin">{String(isAdmin)}</span>
      <span data-testid="write">{String(canWrite)}</span>
      <span data-testid="errore">{String(errore)}</span>
      <button onClick={() => logout().catch(() => setErrore(true))}>Logout</button>
    </div>
  );
}

describe('Sessione frontend fail-closed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.setItem('auth_token', 'token-sintetico');
  });

  it('non cancella il token se la revoca server-side fallisce', async () => {
    api.get.mockResolvedValue({ data: { user: { role: 'admin', email: 'test@example.invalid' } } });
    api.post.mockRejectedValue({ response: { status: 503 } });
    render(<AuthProvider><Probe /></AuthProvider>);

    await screen.findByText('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    await waitFor(() => expect(screen.getByTestId('errore')).toHaveTextContent('true'));
    expect(localStorage.getItem('auth_token')).toBe('token-sintetico');
  });

  it('cancella il token solo dopo logout confermato', async () => {
    localStorage.setItem('admin_token', 'token-menu');
    localStorage.setItem('pt_token', 'token-hr');
    localStorage.setItem('lotti_token', 'token-lotti');
    api.get.mockResolvedValue({ data: { user: { role: 'admin', email: 'test@example.invalid' } } });
    api.post.mockResolvedValue({ data: { ok: true } });
    render(<AuthProvider><Probe /></AuthProvider>);

    await screen.findByText('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    await waitFor(() => expect(localStorage.getItem('auth_token')).toBeNull());
    expect(localStorage.getItem('admin_token')).toBeNull();
    expect(localStorage.getItem('pt_token')).toBeNull();
    expect(localStorage.getItem('lotti_token')).toBeNull();
  });

  it('un ruolo sconosciuto non ottiene privilegi nel frontend', async () => {
    api.get.mockResolvedValue({ data: { user: { role: 'responsabile' } } });
    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByTestId('role')).toHaveTextContent('non_autorizzato');
    expect(screen.getByTestId('admin')).toHaveTextContent('false');
    expect(screen.getByTestId('write')).toHaveTextContent('false');
  });

  it('un ricaricamento entro 120 s riusa la verifica, un token diverso no', async () => {
    api.get.mockResolvedValue({ data: { user: { role: 'operatore', email: 'test@example.invalid' } } });
    const primo = render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByTestId('role')).toHaveTextContent('operatore');
    expect(api.get).toHaveBeenCalledTimes(1);
    primo.unmount();

    const secondo = render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByTestId('role')).toHaveTextContent('operatore');
    expect(api.get).toHaveBeenCalledTimes(1);
    secondo.unmount();

    localStorage.setItem('auth_token', 'altro-token-sintetico');
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });
});
