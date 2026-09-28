import React, { useCallback, useEffect, useRef, useState } from 'react';
import { COLORS, BORDER_RADIUS } from '../lib/utils';
import { Button } from './ds';

/**
 * Scatto da fotocamera live (getUserMedia), mai una scelta di file: le mani
 * sporche di chi lavora al banco non aprono una galleria, scattano e basta.
 * `onCattura(blob)` riceve un JPEG pronto per l'upload; `onChiudi()` chiude
 * senza scattare. Lo stream si ferma sempre, sia allo scatto sia alla chiusura.
 */
export default function CameraCattura({ onCattura, onChiudi }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [errore, setErrore] = useState('');
  const [pronta, setPronta] = useState(false);

  useEffect(() => {
    let annullato = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }, audio: false,
        });
        if (annullato) { stream.getTracks().forEach(t => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setPronta(true);
      } catch (e) {
        setErrore(
          e?.name === 'NotAllowedError'
            ? 'Fotocamera negata: consenti l\'accesso nelle impostazioni del browser.'
            : 'Fotocamera non disponibile su questo dispositivo.'
        );
      }
    })();
    return () => {
      annullato = true;
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  const chiudi = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    onChiudi();
  }, [onChiudi]);

  const scatta = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      streamRef.current?.getTracks().forEach(t => t.stop());
      if (blob) onCattura(blob);
    }, 'image/jpeg', 0.92);
  }, [onCattura]);

  return (
    <div
      role="dialog"
      aria-label="Scatta foto"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(20, 20, 19, 0.92)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', zIndex: 2000, padding: 16,
      }}
    >
      {errore ? (
        <div style={{
          background: COLORS.card, color: COLORS.text, borderRadius: BORDER_RADIUS.lg,
          padding: 24, maxWidth: 360, textAlign: 'center', display: 'grid', gap: 14,
        }}>
          <p style={{ margin: 0 }}>{errore}</p>
          <Button variant="secondary" onClick={chiudi}>Chiudi</Button>
        </div>
      ) : (
        <>
          <video
            ref={videoRef}
            playsInline
            muted
            data-testid="camera-video"
            style={{
              width: '100%', maxWidth: 520, maxHeight: '70vh', borderRadius: BORDER_RADIUS.lg,
              background: '#000', objectFit: 'cover',
            }}
          />
          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <Button variant="secondary" onClick={chiudi}>Annulla</Button>
            <Button variant="primary" onClick={scatta} disabled={!pronta} data-testid="camera-scatta">
              📷 Scatta
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
