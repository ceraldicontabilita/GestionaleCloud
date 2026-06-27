/* Corrispettivi — recreation of pages/Corrispettivi.jsx (KPI + data table). */
function CorrispettiviScreen() {
  const C = window.CeraldiERPDesignSystem_9a014a;
  const Icon = window.Icon;
  const { PageHeader, StatCard, Card, Button } = C;

  const rows = [
    { data: '12/06/2026', rt: 'RT-99AB001234', cassa: '€ 1.840', pos: '€ 2.310', tot: '€ 4.150', iva: '€ 377' },
    { data: '11/06/2026', rt: 'RT-99AB001234', cassa: '€ 1.520', pos: '€ 1.980', tot: '€ 3.500', iva: '€ 318' },
    { data: '10/06/2026', rt: 'RT-99AB001234', cassa: '€ 2.105', pos: '€ 2.640', tot: '€ 4.745', iva: '€ 431' },
    { data: '09/06/2026', rt: 'RT-99AB001234', cassa: '€ 980', pos: '€ 1.420', tot: '€ 2.400', iva: '€ 218' },
    { data: '08/06/2026', rt: 'RT-99AB001234', cassa: '€ 1.760', pos: '€ 2.090', tot: '€ 3.850', iva: '€ 350' },
    { data: '07/06/2026', rt: 'RT-99AB001234', cassa: '€ 2.430', pos: '€ 3.010', tot: '€ 5.440', iva: '€ 495' },
  ];

  const mono = { fontFamily: 'var(--font-mono)', textAlign: 'right', whiteSpace: 'nowrap' };

  return (
    <div>
      <PageHeader
        title="Corrispettivi Elettronici"
        subtitle="Corrispettivi giornalieri dal registratore telematico · Anno 2026"
        icon={<Icon name="receipt" size={20} color="var(--c-primary)" />}
        actions={<>
          <Button variant="success" size="sm" iconLeft={<Icon name="upload" size={15} />}>Importa XML</Button>
          <Button variant="secondary" size="sm" iconLeft={<Icon name="refresh-cw" size={15} />}>Aggiorna</Button>
        </>}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, margin: '16px 0' }}>
        <StatCard icon={<Icon name="receipt" size={18} />} label="Totale Corrispettivi" value="€ 184.920" accent="primary" />
        <StatCard icon={<Icon name="banknote" size={18} />} label="Pagato Cassa" value="€ 96.400" accent="success" />
        <StatCard icon={<Icon name="credit-card" size={18} />} label="Pagato POS" value="€ 88.520" accent="info" />
        <StatCard icon={<Icon name="percent" size={18} />} label="IVA 10%" value="€ 16.811" subtext="Imponibile: € 168.109" accent="accent" />
      </div>

      <Card title="Elenco Corrispettivi (184)" icon={<Icon name="list" size={16} color="var(--c-primary)" />}
        actions={<Button variant="ghost" size="sm" iconLeft={<Icon name="link" size={14} />}>Copia link</Button>}
        bodyStyle={{ padding: 0 }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={th()}>Data</th>
                <th style={th()}>Matricola RT</th>
                <th style={{ ...th(), textAlign: 'right' }}>💵 Cassa</th>
                <th style={{ ...th(), textAlign: 'right' }}>💳 POS</th>
                <th style={{ ...th(), textAlign: 'right' }}>Totale</th>
                <th style={{ ...th(), textAlign: 'right' }}>IVA</th>
                <th style={{ ...th(), textAlign: 'center' }}>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--gray-100)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(15,39,68,0.025)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                  <td style={{ ...td(), fontWeight: 600 }}>{r.data}</td>
                  <td style={{ ...td(), color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.rt}</td>
                  <td style={{ ...td(), ...mono, color: 'var(--c-success)', fontWeight: 500 }}>{r.cassa}</td>
                  <td style={{ ...td(), ...mono, color: 'var(--c-info)', fontWeight: 500 }}>{r.pos}</td>
                  <td style={{ ...td(), ...mono, fontWeight: 700 }}>{r.tot}</td>
                  <td style={{ ...td(), ...mono, color: 'var(--c-accent)', fontWeight: 500 }}>{r.iva}</td>
                  <td style={{ ...td(), textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <button style={iconBtn('var(--c-info-light)', 'var(--c-info)')} title="Dettaglio"><Icon name="eye" size={14} /></button>
                    <button style={iconBtn('var(--c-danger-light)', 'var(--c-danger)')} title="Elimina"><Icon name="trash-2" size={14} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );

  function th() {
    return { padding: '12px 14px', textAlign: 'left', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--c-text-muted)', background: 'var(--c-bg-alt)', borderBottom: '1px solid var(--c-border)', whiteSpace: 'nowrap' };
  }
  function td() {
    return { padding: '12px 14px', color: 'var(--c-text)', fontSize: 13, verticalAlign: 'middle' };
  }
  function iconBtn(bg, color) {
    return { display: 'inline-flex', padding: '6px 10px', background: bg, color, border: 'none', borderRadius: 6, cursor: 'pointer', marginLeft: 6 };
  }
}

window.CorrispettiviScreen = CorrispettiviScreen;
