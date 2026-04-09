export default function App() {
  const url = import.meta.env.VITE_TRACCIABILITA_URL || 'https://food-cost-calc-14.preview.emergentagent.com'
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0f0f0f' }}>
      <a
        href={url}
        style={{
          display: 'inline-block',
          padding: '20px 48px',
          background: '#5D29C7',
          color: '#fff',
          textDecoration: 'none',
          borderRadius: '12px',
          fontSize: '22px',
          fontWeight: '700',
          letterSpacing: '0.5px',
          fontFamily: 'Plus Jakarta Sans, sans-serif',
        }}
      >
        Tracciabilità
      </a>
    </div>
  )
}
