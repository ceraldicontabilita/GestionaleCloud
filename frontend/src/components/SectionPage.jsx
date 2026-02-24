import React, { useState, Suspense } from 'react';

const SectionLoading = () => (
  <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #2563eb',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    Caricamento...
  </div>
);

export function SectionPage({ title, subtitle, icon, sections, defaultOpen, actions }) {
  // Active section - starts with defaultOpen or first section
  const [activeSection, setActiveSection] = useState(() => {
    if (defaultOpen) return defaultOpen;
    if (sections.length > 0) return sections[0].id;
    return null;
  });

  const activeContent = sections.find(s => s.id === activeSection);

  return (
    <div data-testid="section-page" style={{ minHeight: '100vh', background: '#f8fafc' }}>
      {/* Header - Solo titolo, senza tab duplicati */}
      <div style={{
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        padding: '16px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16
      }}>
        <div>
          <h1 data-testid="section-page-title" style={{
            fontSize: 20,
            fontWeight: 700,
            color: '#0f172a',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            margin: 0
          }}>
            {icon && <span style={{ color: '#3b82f6' }}>{icon}</span>}
            {title}
          </h1>
          {subtitle && (
            <p style={{ fontSize: 12, color: '#64748b', margin: '4px 0 0' }}>{subtitle}</p>
          )}
        </div>
        {actions && <div style={{ display: 'flex', gap: 8 }}>{actions}</div>}
      </div>

      {/* Content - Render diretto senza tab (i tab sono già nella topnav) */}
      <div style={{ padding: '16px 24px' }}>
        {activeContent && (
          <Suspense fallback={<SectionLoading />}>
            <div 
              data-testid={`section-content-${activeSection}`}
              style={{ 
                background: 'white', 
                borderRadius: 10, 
                border: '1px solid #e2e8f0',
                minHeight: 200 
              }}
            >
              {activeContent.component}
            </div>
          </Suspense>
        )}
      </div>
    </div>
  );
}
