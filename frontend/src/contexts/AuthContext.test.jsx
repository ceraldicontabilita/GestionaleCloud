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
    api.get.mockResolvedValue({ data: { user: { role: 'admin', email: 'test@example.invalid' } } });
    api.post.mockResolvedValue({ data: { ok: true } });
    render(<AuthProvider><Probe /></AuthProvider>);

    await screen.findByText('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    await waitFor(() => expect(localStorage.getItem('auth_token')).toBeNull());
  });

  it('un ruolo sconosciuto non ottiene privilegi nel frontend', async () => {
    api.get.mockResolvedValue({ data: { user: { role: 'responsabile' } } });
    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByTestId('role')).toHaveTextContent('non_autorizzato');
    expect(screen.getByTestId('admin')).toHaveTextContent('false');
    expect(screen.getByTestId('write')).toHaveTextContent('false');
  });
});
