import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HubTabs } from '../ds/HubTabs';
import { schedeDi } from '../../navigation.config';
import { useAuth } from '../../contexts/AuthContext.jsx';

/**
 * Le schede del hub in cui ci si trova, in cima a ogni pagina: TUTTE visibili,
 * a capo quando non ci stanno, lette dalla mappa di navigazione unica
 * (`schedeDi`). La colonna a sinistra mostra solo i hub; qui si sceglie la
 * pagina dentro il hub. Nessun hub disegna piu' una propria riga di schede.
 *
 * Non si disegna niente se la pagina non sta in un hub o il hub ha una sola
 * scheda visibile per il ruolo.
 */
const slug = label => label.toLowerCase().replace(/\s+/g, '-');

export default function SchedeHub() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const trovate = schedeDi(pathname, isAdmin);
  if (!trovate) return null;

  const tabs = trovate.schede.map(s => ({ id: slug(s.label), label: s.label, to: s.to }));
  return (
    <div data-testid="schede-hub" data-hub={slug(trovate.hub.label)}>
      <HubTabs
        testIdPrefix="scheda"
        tabs={tabs}
        activeId={slug(trovate.attiva.label)}
        onSelect={tab => navigate(tab.to)}
      />
    </div>
  );
}
