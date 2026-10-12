import React from 'react';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import api from '../api';
import BatchProcessor from './BatchProcessor';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

describe('Elaborazione batch', () => {
  it('aprire la pagina non avvia job o scritture', async () => {
    vi.useFakeTimers();
    const view = render(<MemoryRouter><BatchProcessor /></MemoryRouter>);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(api.post).not.toHaveBeenCalled();
    view.unmount();
    vi.useRealTimers();
  });
});
