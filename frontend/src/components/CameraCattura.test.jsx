/**
 * Scatto live: mai una scelta da galleria, solo il flusso getUserMedia →
 * video → canvas → blob. jsdom non implementa la fotocamera né il canvas
 * 2D: qui si sostituiscono con stub minimi per provare il comportamento,
 * non il rendering reale del frame.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import CameraCattura from './CameraCattura';

function finaStream() {
  const track = { stop: vi.fn() };
  return { getTracks: () => [track], _track: track };
}

describe('CameraCattura', () => {
  let stream;

  beforeEach(() => {
    stream = finaStream();
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) }, configurable: true,
    });
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { value: 640, configurable: true });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { value: 480, configurable: true });
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({ drawImage: vi.fn() });
    HTMLCanvasElement.prototype.toBlob = vi.fn(function toBlob(cb) {
      cb(new Blob(['jpeg'], { type: 'image/jpeg' }));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('chiede la fotocamera posteriore, mai un file da galleria', async () => {
    render(<CameraCattura onCattura={vi.fn()} onChiudi={vi.fn()} />);
    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: { ideal: 'environment' } }, audio: false,
    }));
    expect(screen.queryByRole('button', { name: /file|carica|upload/i })).not.toBeInTheDocument();
  });

  it('«Scatta» consegna un blob JPEG e ferma lo stream', async () => {
    const onCattura = vi.fn();
    render(<CameraCattura onCattura={onCattura} onChiudi={vi.fn()} />);

    const scatta = await screen.findByTestId('camera-scatta');
    await waitFor(() => expect(scatta).toBeEnabled());
    fireEvent.click(scatta);

    await waitFor(() => expect(onCattura).toHaveBeenCalledTimes(1));
    const blob = onCattura.mock.calls[0][0];
    expect(blob.type).toBe('image/jpeg');
    expect(stream._track.stop).toHaveBeenCalled();
  });

  it('«Annulla» chiude senza scattare e ferma lo stream', async () => {
    const onChiudi = vi.fn();
    render(<CameraCattura onCattura={vi.fn()} onChiudi={onChiudi} />);

    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /annulla/i }));

    expect(onChiudi).toHaveBeenCalledTimes(1);
    expect(stream._track.stop).toHaveBeenCalled();
  });

  it('un permesso negato mostra un messaggio chiaro, non un file input', async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValueOnce(
      Object.assign(new Error('nope'), { name: 'NotAllowedError' })
    );
    render(<CameraCattura onCattura={vi.fn()} onChiudi={vi.fn()} />);

    expect(await screen.findByText(/fotocamera negata/i)).toBeInTheDocument();
  });
});
