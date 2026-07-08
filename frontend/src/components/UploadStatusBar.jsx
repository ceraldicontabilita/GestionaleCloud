/**
 * Componente flottante per mostrare lo stato degli upload in corso.
 * Visibile da qualsiasi pagina, posizionato in basso a destra.
 */
import React, { useState } from 'react';
import { useUpload } from '../contexts/UploadContext';
import { Button } from './ds';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../lib/utils';

export function UploadStatusBar() {
  const {
    uploads,
    activeUploads,
    completedUploads,
    errorUploads,
    removeUpload,
    clearCompleted,
    hasActiveUploads,
  } = useUpload();

  const [expanded, setExpanded] = useState(false);
  const [minimized, setMinimized] = useState(false);

  // Non mostrare se non ci sono upload
  if (uploads.length === 0) return null;

  // Versione minimizzata - solo badge
  if (minimized) {
    return (
      <>
        <style>{`
          @media (max-width: 768px) {
            .upload-status-fixed { bottom: 84px !important; }
          }
        `}</style>
        <Button
          variant={hasActiveUploads ? 'info' : completedUploads.length > 0 ? 'success' : 'danger'}
          onClick={() => setMinimized(false)}
          className="upload-status-fixed"
          style={{
            position: 'fixed',
            bottom: 20,
            right: 20,
            width: 56,
            height: 56,
            padding: 0,
            borderRadius: BORDER_RADIUS.full,
            boxShadow: SHADOWS.lg,
            fontSize: 20,
            zIndex: 9999,
            animation: hasActiveUploads ? 'pulse 2s infinite' : 'none',
          }}
        >
          {hasActiveUploads ? '⏳' : completedUploads.length > 0 ? '✓' : '!'}
          <span
            style={{
              position: 'absolute',
              top: -4,
              right: -4,
              background: COLORS.danger,
              color: 'white',
              borderRadius: BORDER_RADIUS.full,
              width: 20,
              height: 20,
              fontSize: 11,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {uploads.length}
          </span>
        </Button>
      </>
    );
  }

  return (
    <div
      className="upload-status-fixed"
      style={{
        position: 'fixed',
        bottom: 20,
        right: 20,
        width: expanded ? 380 : 320,
        background: COLORS.card,
        borderRadius: BORDER_RADIUS.lg,
        boxShadow: SHADOWS.xl,
        zIndex: 9999,
        overflow: 'hidden',
        transition: 'width 0.2s',
      }}
    >
      {/* CSS animazione */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.05); }
        }
        @keyframes progress-stripe {
          0% { background-position: 0 0; }
          100% { background-position: 40px 0; }
        }
        @media (max-width: 768px) {
          .upload-status-fixed { bottom: 84px !important; }
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          background: hasActiveUploads ? COLORS.info : COLORS.gray[800],
          color: 'white',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>{hasActiveUploads ? '⏳' : '📤'}</span>
          <span style={{ fontWeight: 600, fontSize: 14 }}>
            {hasActiveUploads
              ? `Upload in corso (${activeUploads.length})`
              : `Upload completati (${uploads.length})`}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            variant="ghost"
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              borderRadius: BORDER_RADIUS.sm,
              padding: '4px 8px',
              color: 'white',
              fontSize: 12,
            }}
          >
            {expanded ? '▼' : '▲'}
          </Button>
          <Button
            variant="ghost"
            onClick={() => setMinimized(true)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              borderRadius: BORDER_RADIUS.sm,
              padding: '4px 8px',
              color: 'white',
              fontSize: 12,
            }}
          >
            −
          </Button>
        </div>
      </div>

      {/* Lista upload */}
      <div
        style={{
          maxHeight: expanded ? 400 : 200,
          overflowY: 'auto',
          transition: 'max-height 0.2s',
        }}
      >
        {uploads.map(upload => (
          <div
            key={upload.id}
            style={{
              padding: '12px 16px',
              borderBottom: `1px solid ${COLORS.bg}`,
              background: upload.status === 'error' ? COLORS.dangerLight : COLORS.card,
            }}
          >
            {/* File info */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: 8,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: 13,
                    color: COLORS.gray[800],
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {upload.fileName}
                </div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
                  {upload.fileType} • {getStatusText(upload.status)}
                </div>
              </div>

              {/* Status icon e azioni */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 8 }}>
                <span style={{ fontSize: 16 }}>{getStatusIcon(upload.status)}</span>
                {(upload.status === 'completed' || upload.status === 'error') && (
                  <Button
                    variant="ghost"
                    onClick={() => removeUpload(upload.id)}
                    style={{
                      fontSize: 14,
                      color: COLORS.textSubtle,
                      padding: 4,
                    }}
                  >
                    ✕
                  </Button>
                )}
              </div>
            </div>

            {/* Progress bar */}
            {(upload.status === 'uploading' || upload.status === 'pending') && (
              <div
                style={{
                  height: 6,
                  background: COLORS.border,
                  borderRadius: 3,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${upload.progress}%`,
                    background:
                      COLORS.info,
                    backgroundSize: '40px 40px',
                    animation: 'progress-stripe 1s linear infinite',
                    transition: 'width 0.3s',
                  }}
                />
              </div>
            )}

            {/* Error message */}
            {upload.status === 'error' && upload.error && (
              <div
                style={{
                  fontSize: 11,
                  color: COLORS.danger,
                  marginTop: 4,
                  padding: '4px 8px',
                  background: COLORS.dangerLight,
                  borderRadius: BORDER_RADIUS.sm,
                }}
              >
                {upload.error}
              </div>
            )}

            {/* Success result summary */}
            {upload.status === 'completed' && upload.result && (
              <div
                style={{
                  fontSize: 11,
                  color: COLORS.success,
                  marginTop: 4,
                  padding: '4px 8px',
                  background: COLORS.successLight,
                  borderRadius: BORDER_RADIUS.sm,
                }}
              >
                {getResultSummary(upload.result)}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer con azioni */}
      {(completedUploads.length > 0 || errorUploads.length > 0) && (
        <div
          style={{
            padding: '8px 16px',
            background: COLORS.bgAlt,
            borderTop: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 11, color: COLORS.textMuted }}>
            {completedUploads.length} completati, {errorUploads.length} errori
          </span>
          <Button
            variant="ghost"
            onClick={clearCompleted}
            style={{
              color: COLORS.info,
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            Pulisci completati
          </Button>
        </div>
      )}
    </div>
  );
}

// Helper functions
function getStatusIcon(status) {
  switch (status) {
    case 'pending':
      return '⏸️';
    case 'uploading':
      return '⏳';
    case 'processing':
      return '⚙️';
    case 'completed':
      return '✅';
    case 'error':
      return '❌';
    default:
      return '📄';
  }
}

function getStatusText(status) {
  switch (status) {
    case 'pending':
      return 'In coda';
    case 'uploading':
      return 'Caricamento...';
    case 'processing':
      return 'Elaborazione...';
    case 'completed':
      return 'Completato';
    case 'error':
      return 'Errore';
    default:
      return status;
  }
}

function getResultSummary(result) {
  if (result.message) return result.message;
  if (result.imported !== undefined) return `${result.imported} record importati`;
  if (result.count !== undefined) return `${result.count} elementi elaborati`;
  if (result.created !== undefined) return `${result.created} creati`;
  return 'Upload riuscito';
}

export default UploadStatusBar;
