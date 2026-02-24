/**
 * Componente flottante per mostrare lo stato degli upload in corso.
 * Visibile da qualsiasi pagina, posizionato in basso a destra.
 */
import React, { useState } from 'react';
import { useUpload } from '../contexts/UploadContext';

export function UploadStatusBar() {
  const { 
    uploads, 
    activeUploads, 
    completedUploads, 
    errorUploads,
    removeUpload, 
    clearCompleted,
    hasActiveUploads 
  } = useUpload();
  
  const [expanded, setExpanded] = useState(false);
  const [minimized, setMinimized] = useState(false);

  // Non mostrare se non ci sono upload
  if (uploads.length === 0) return null;

  // Versione minimizzata - solo badge
  if (minimized) {
    return (
      <button
        onClick={() => setMinimized(false)}
        style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          width: 56,
          height: 56,
          borderRadius: '50%',
          background: hasActiveUploads ? '#1535a8' : completedUploads.length > 0 ? '#10b981' : '#ef4444',
          border: 'none',
          boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 20,
          zIndex: 9999,
          animation: hasActiveUploads ? 'pulse 2s infinite' : 'none'
        }}
      >
        {hasActiveUploads ? '⏳' : completedUploads.length > 0 ? '✓' : '!'}
        <span style={{
          position: 'absolute',
          top: -4,
          right: -4,
          background: '#ef4444',
          color: 'white',
          borderRadius: '50%',
          width: 20,
          height: 20,
          fontSize: 11,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          {uploads.length}
        </span>
      </button>
    );
  }

  return (
    <div style={{
      position: 'fixed',
      bottom: 20,
      right: 20,
      width: expanded ? 380 : 320,
      background: 'white',
      borderRadius: 12,
      boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
      zIndex: 9999,
      overflow: 'hidden',
      transition: 'width 0.2s'
    }}>
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
      `}</style>

      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: hasActiveUploads ? '#1535a8' : '#1e293b',
        color: 'white',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>
            {hasActiveUploads ? '⏳' : '📤'}
          </span>
          <span style={{ fontWeight: 600, fontSize: 14 }}>
            {hasActiveUploads 
              ? `Upload in corso (${activeUploads.length})`
              : `Upload completati (${uploads.length})`
            }
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              borderRadius: 4,
              padding: '4px 8px',
              color: 'white',
              cursor: 'pointer',
              fontSize: 12
            }}
          >
            {expanded ? '▼' : '▲'}
          </button>
          <button
            onClick={() => setMinimized(true)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              borderRadius: 4,
              padding: '4px 8px',
              color: 'white',
              cursor: 'pointer',
              fontSize: 12
            }}
          >
            −
          </button>
        </div>
      </div>

      {/* Lista upload */}
      <div style={{ 
        maxHeight: expanded ? 400 : 200, 
        overflowY: 'auto',
        transition: 'max-height 0.2s'
      }}>
        {uploads.map(upload => (
          <div key={upload.id} style={{
            padding: '12px 16px',
            borderBottom: '1px solid #f1f5f9',
            background: upload.status === 'error' ? '#fef2f2' : 'white'
          }}>
            {/* File info */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ 
                  fontWeight: 600, 
                  fontSize: 13, 
                  color: '#1e293b',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }}>
                  {upload.fileName}
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                  {upload.fileType} • {getStatusText(upload.status)}
                </div>
              </div>
              
              {/* Status icon e azioni */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 8 }}>
                <span style={{ fontSize: 16 }}>{getStatusIcon(upload.status)}</span>
                {(upload.status === 'completed' || upload.status === 'error') && (
                  <button
                    onClick={() => removeUpload(upload.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      fontSize: 14,
                      color: '#94a3b8',
                      padding: 4
                    }}
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Progress bar */}
            {(upload.status === 'uploading' || upload.status === 'pending') && (
              <div style={{
                height: 6,
                background: '#dce8f4',
                borderRadius: 3,
                overflow: 'hidden'
              }}>
                <div style={{
                  height: '100%',
                  width: `${upload.progress}%`,
                  background: 'linear-gradient(45deg, #1535a8 25%, #60a5fa 25%, #60a5fa 50%, #1535a8 50%, #1535a8 75%, #60a5fa 75%)',
                  backgroundSize: '40px 40px',
                  animation: 'progress-stripe 1s linear infinite',
                  transition: 'width 0.3s'
                }} />
              </div>
            )}

            {/* Error message */}
            {upload.status === 'error' && upload.error && (
              <div style={{ 
                fontSize: 11, 
                color: '#dc2626', 
                marginTop: 4,
                padding: '4px 8px',
                background: '#fee2e2',
                borderRadius: 4
              }}>
                {upload.error}
              </div>
            )}

            {/* Success result summary */}
            {upload.status === 'completed' && upload.result && (
              <div style={{ 
                fontSize: 11, 
                color: '#059669', 
                marginTop: 4,
                padding: '4px 8px',
                background: '#d1fae5',
                borderRadius: 4
              }}>
                {getResultSummary(upload.result)}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer con azioni */}
      {(completedUploads.length > 0 || errorUploads.length > 0) && (
        <div style={{
          padding: '8px 16px',
          background: '#f8fafc',
          borderTop: '1px solid #dce8f4',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            {completedUploads.length} completati, {errorUploads.length} errori
          </span>
          <button
            onClick={clearCompleted}
            style={{
              background: 'none',
              border: 'none',
              color: '#1535a8',
              fontSize: 12,
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            Pulisci completati
          </button>
        </div>
      )}
    </div>
  );
}

// Helper functions
function getStatusIcon(status) {
  switch (status) {
    case 'pending': return '⏸️';
    case 'uploading': return '⏳';
    case 'processing': return '⚙️';
    case 'completed': return '✅';
    case 'error': return '❌';
    default: return '📄';
  }
}

function getStatusText(status) {
  switch (status) {
    case 'pending': return 'In coda';
    case 'uploading': return 'Caricamento...';
    case 'processing': return 'Elaborazione...';
    case 'completed': return 'Completato';
    case 'error': return 'Errore';
    default: return status;
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
