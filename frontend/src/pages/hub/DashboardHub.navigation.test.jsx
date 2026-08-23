import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import DashboardHub from './DashboardHub';

vi.mock('../Dashboard.jsx', () => ({ default: () => <div>Dashboard principale</div> }));
vi.mock('../Alerts.jsx', () => ({ default: () => <div>Elenco alert operativi</div> }));

describe('Navigazione Dashboard e alert', () => {
  it('riusa l hub Dashboard per mostrare la lista alert', () => {
    render(<MemoryRouter initialEntries={['/dashboard/alerts']}><DashboardHub /></MemoryRouter>);
    expect(screen.getByText('Elenco alert operativi')).toBeInTheDocument();
    expect(screen.queryByText('Dashboard principale')).not.toBeInTheDocument();
  });

  it('mantiene la Dashboard sulle altre route', async () => {
    render(<MemoryRouter initialEntries={['/dashboard']}><DashboardHub /></MemoryRouter>);
    expect(await screen.findByText('Dashboard principale')).toBeInTheDocument();
  });
});
