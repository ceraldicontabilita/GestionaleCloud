import React, { useState, useEffect, useRef } from 'react'
import { X, ExternalLink, Loader, FileText, AlertCircle } from 'lucide-react'
import { colors, shadow, s } from '../lib/utils'

/**
 * VisFattura — Drawer laterale che mostra l'HTML della fattura
 * generato dal foglio stile AssoSoftware (XSL) o dal fallback.
 *
 * Uso: <VisFattura fatturaId={id} onClose={() => setId(null)} />
 */
export default function VisFattura({ fatturaId, onClose }) {
  const [html, setHtml]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const iframeRef             = useRef(null)

  useEffect(() => {
    if (!fatturaId) return
    setLoading(true)
    setError(null)
    setHtml(null)
    fetch(`/api/fatture/${fatturaId}/html`)
      .then(r => {
        if (!r.ok) throw new Error(`Errore ${r.status}`)
        return r.text()
      })
      .then(h => setHtml(h))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [fatturaId])

  /* Chiudi con Escape */
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  if (!fatturaId) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(30,27,75,0.45)',
          backdropFilter: 'blur(2px)',
          transition: 'opacity .2s',
        }}
      />

      {/* Drawer */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 1001,
        width: 'min(960px, 92vw)',
        background: colors.card,
        boxShadow: '-8px 0 40px rgba(93,41,199,0.15)',
        display: 'flex', flexDirection: 'column',
        animation: 'slideIn .22s ease',
      }}>
        <style>{`
          @keyframes slideIn { from { transform: translateX(60px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        `}</style>

        {/* Topbar drawer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 24px',
          borderBottom: `1px solid ${colors.border}`,
          background: colors.card,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: colors.primaryBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <FileText size={18} color={colors.primary} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: colors.text }}>
                Visualizza Fattura
              </div>
              <div style={{ fontSize: 11, color: colors.textLight }}>
                Foglio stile AssoSoftware — FatturaPA
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Apri in nuova tab */}
            <a
              href={`/api/fatture/${fatturaId}/html`}
              target="_blank" rel="noreferrer"
              style={{
                ...s.btn, ...s.btnGhost, ...s.btnSmall,
                textDecoration: 'none', fontSize: 12,
              }}
            >
              <ExternalLink size={13} />
              Apri in nuova tab
            </a>
            <button
              onClick={onClose}
              style={{
                width: 32, height: 32, borderRadius: 8,
                border: `1px solid ${colors.border}`,
                background: 'transparent', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: colors.textMuted,
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Contenuto */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {loading && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12,
              background: colors.card,
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                border: `3px solid ${colors.primaryBg}`,
                borderTopColor: colors.primary,
                animation: 'spin .8s linear infinite',
              }} />
              <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
              <div style={{ fontSize: 13, color: colors.textMuted }}>Generazione anteprima...</div>
            </div>
          )}

          {error && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12,
            }}>
              <AlertCircle size={36} color={colors.danger} />
              <div style={{ fontSize: 14, fontWeight: 600, color: colors.text }}>
                Impossibile caricare la fattura
              </div>
              <div style={{ fontSize: 13, color: colors.textMuted }}>{error}</div>
            </div>
          )}

          {html && !loading && (
            <iframe
              ref={iframeRef}
              srcDoc={html}
              style={{
                width: '100%', height: '100%',
                border: 'none',
                background: '#f0f4fa',
              }}
              title="Anteprima fattura"
              sandbox="allow-same-origin"
            />
          )}
        </div>
      </div>
    </>
  )
}
