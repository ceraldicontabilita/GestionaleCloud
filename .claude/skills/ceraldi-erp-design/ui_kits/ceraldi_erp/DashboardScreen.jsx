/* Dashboard — KPI overview + recent invoices + system alerts. */
function DashboardScreen() {
  const C = window.CeraldiERPDesignSystem_9a014a;
  const Icon = window.Icon;
  const { PageHeader, StatCard, Card, Badge, Button } = C;

  const recent = [
    { n: '24/0118', forn: 'ABC Forniture Srl', data: '12/06/2026', imp: '€ 2.480,00', stato: ['warning', 'In scadenza'] },
    { n: '24/0117', forn: 'TIM S.p.A.', data: '10/06/2026', imp: '€ 312,90', stato: ['success', 'Pagata'] },
    { n: 'NC 24/09', forn: 'Metro Italia', data: '08/06/2026', imp: '− € 540,00', stato: ['info', 'Nota credito'] },
    { n: '24/0116', forn: 'Enel Energia', data: '05/06/2026', imp: '€ 1.105,40', stato: ['danger', 'Insoluta'] },
    { n: '24/0115', forn: 'Sammontana S.p.A.', data: '03/06/2026', imp: '€ 4.920,00', stato: ['success', 'Pagata'] },
  ];

  const alerts = [
    { sev: 'danger', t: 'Fattura insoluta oltre 30gg', d: 'Enel Energia — € 1.105,40', m: 'Fatture' },
    { sev: 'warning', t: 'Partita aperta in scadenza', d: 'ABC Forniture Srl — scade 18/06', m: 'Scadenziario' },
    { sev: 'warning', t: 'Movimento banca non riconciliato', d: 'BPM — € 2.480,00 del 12/06', m: 'Riconciliazione' },
    { sev: 'info', t: 'Cedolino importato', d: '3 nuovi cedolini da Studio Ferrantini', m: 'HR' },
  ];

  const mono = { fontFamily: 'var(--font-mono)', textAlign: 'right', whiteSpace: 'nowrap' };

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Panoramica contabile · Anno 2026"
        icon={<Icon name="layout-dashboard" size={20} color="var(--c-primary)" />}
        actions={<>
          <Button variant="secondary" size="sm" iconLeft={<Icon name="refresh-cw" size={15} />}>Aggiorna</Button>
          <Button size="sm" iconLeft={<Icon name="download" size={15} />}>Esporta</Button>
        </>}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12, margin: '16px 0' }}>
        <StatCard icon={<Icon name="trending-up" size={18} />} label="Ricavi (Corrispettivi)" value="€ 612.480" subtext="+8,2% vs 2025" accent="success" />
        <StatCard icon={<Icon name="file-text" size={18} />} label="Costi (Fatture)" value="€ 438.910" subtext="3.856 fatture" accent="primary" />
        <StatCard icon={<Icon name="wallet" size={18} />} label="Saldo Banca BPM" value="€ 84.205" subtext="al 27/06/2026" accent="info" />
        <StatCard icon={<Icon name="triangle-alert" size={18} />} label="Insoluti" value="€ 12.640" subtext="7 partite aperte" accent="danger" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, alignItems: 'start' }}>
        <Card title="Ultime Fatture Ricevute" icon={<Icon name="file-text" size={16} color="var(--c-primary)" />}
          actions={<Button variant="ghost" size="sm" iconRight={<Icon name="arrow-right" size={14} />}>Tutte</Button>}
          bodyStyle={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={th()}>Numero</th><th style={th()}>Fornitore</th>
                  <th style={th()}>Data</th><th style={{ ...th(), textAlign: 'right' }}>Importo</th>
                  <th style={{ ...th(), textAlign: 'center' }}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r, i) => (
                  <tr key={i} style={{ borderTop: '1px solid var(--gray-100)' }}>
                    <td style={td()}><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.n}</span></td>
                    <td style={td()}>{r.forn}</td>
                    <td style={{ ...td(), color: 'var(--c-text-muted)' }}>{r.data}</td>
                    <td style={{ ...td(), ...mono, fontWeight: 700, color: r.imp.startsWith('−') ? 'var(--c-danger)' : 'var(--c-text)' }}>{r.imp}</td>
                    <td style={{ ...td(), textAlign: 'center' }}><Badge variant={r.stato[0]}>{r.stato[1]}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Alert di Sistema" icon={<Icon name="bell" size={16} color="var(--c-primary)" />}
          actions={<Badge variant="danger">5 aperti</Badge>} bodyStyle={{ padding: 0 }}>
          <div>
            {alerts.map((a, i) => {
              const dot = { danger: 'var(--c-danger)', warning: 'var(--c-warning)', info: 'var(--c-info)' }[a.sev];
              return (
                <div key={i} style={{ display: 'flex', gap: 10, padding: '12px 16px', borderTop: i ? '1px solid var(--gray-100)' : 'none' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 999, background: dot, marginTop: 5, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--c-text)' }}>{a.t}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--c-text-muted)', marginTop: 1 }}>{a.d}</div>
                    <div style={{ fontSize: 10, color: 'var(--c-text-subtle)', marginTop: 3, textTransform: 'uppercase', letterSpacing: 0.4 }}>{a.m}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );

  function th() {
    return { padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--c-text-muted)', background: 'var(--c-bg-alt)', borderBottom: '1px solid var(--c-border)', whiteSpace: 'nowrap' };
  }
  function td() {
    return { padding: '10px 14px', color: 'var(--c-text)', fontSize: 13, verticalAlign: 'middle' };
  }
}

window.DashboardScreen = DashboardScreen;
