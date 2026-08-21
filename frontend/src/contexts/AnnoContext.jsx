import React, { createContext, useCallback, useContext, useState, useEffect } from 'react';

const AnnoContext = createContext();
const STORAGE_KEY = 'annoGlobale';

function normalizeYear(value) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  const currentYear = new Date().getFullYear();
  return Number.isFinite(parsed) && parsed >= 2018 && parsed <= currentYear + 5
    ? parsed
    : currentYear;
}

export function AnnoProvider({ children }) {
  const [anno, setAnnoState] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return normalizeYear(saved);
  });

  const setAnno = useCallback(value => {
    const nuovoAnno = normalizeYear(
      typeof value === 'function' ? value(anno) : value,
    );
    setAnnoState(nuovoAnno);
    localStorage.setItem(STORAGE_KEY, String(nuovoAnno));
  }, [anno]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(normalizeYear(anno)));
  }, [anno]);

  useEffect(() => {
    const handleStorage = event => {
      if (event.key !== STORAGE_KEY) return;
      setAnnoState(normalizeYear(event.newValue));
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  return (
    <AnnoContext.Provider value={{ anno, setAnno }}>
      {children}
    </AnnoContext.Provider>
  );
}

export function useAnnoGlobale() {
  const context = useContext(AnnoContext);
  if (!context) {
    throw new Error('useAnnoGlobale must be used within AnnoProvider');
  }
  return context;
}

// Componente selettore da usare nell'header
export function AnnoSelector({ style = {} }) {
  const { anno, setAnno } = useAnnoGlobale();
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: currentYear - 2018 + 2 }, (_, index) => 2018 + index);

  return (
    <select
      value={anno}
      onChange={e => setAnno(normalizeYear(e.target.value))}
      style={{
        padding: '6px 12px',
        borderRadius: 6,
        border: '1px solid #e2e8f0',
        background: '#f8fafc',
        fontSize: 13,
        fontWeight: 600,
        cursor: 'pointer',
        color: '#334155',
        ...style
      }}
      data-testid="anno-globale-selector"
      title="Anno di riferimento per tutti i dati"
    >
      {years.map(y => (
        <option key={y} value={y}>{y}</option>
      ))}
    </select>
  );
}
