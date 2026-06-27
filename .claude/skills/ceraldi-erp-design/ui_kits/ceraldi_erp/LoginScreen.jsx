/* Login screen — internal ERP gate. */
function LoginScreen({ onLogin }) {
  const C = window.CeraldiERPDesignSystem_9a014a;
  const Icon = window.Icon;
  const { Button, Input } = C;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--c-primary)', padding: 20 }}>
      <div style={{ width: 380, background: 'var(--c-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }}>
        <div style={{ background: 'var(--c-primary)', padding: '28px 28px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 46, height: 46, background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 18, color: '#fff', letterSpacing: 0.5 }}>CG</div>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 18 }}>Ceraldi ERP</div>
            <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>Gestionale interno · Ceraldi Group SRL</div>
          </div>
        </div>
        <div style={{ padding: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--c-text)', marginBottom: 14 }}>Accedi al gestionale</div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--c-text-muted)', textTransform: 'uppercase', letterSpacing: 0.4 }}>Email</label>
          <div style={{ margin: '6px 0 14px' }}><Input defaultValue="enzo@ceraldigroup.it" iconLeft={<Icon name="mail" size={15} />} /></div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--c-text-muted)', textTransform: 'uppercase', letterSpacing: 0.4 }}>Password</label>
          <div style={{ margin: '6px 0 20px' }}><Input type="password" defaultValue="••••••••" iconLeft={<Icon name="lock" size={15} />} /></div>
          <Button style={{ width: '100%', padding: '11px 16px', fontSize: 14 }} iconRight={<Icon name="arrow-right" size={16} />} onClick={onLogin}>Entra</Button>
          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 11, color: 'var(--c-text-subtle)' }}>Uso interno · Tutti i diritti riservati</div>
        </div>
      </div>
    </div>
  );
}

window.LoginScreen = LoginScreen;
