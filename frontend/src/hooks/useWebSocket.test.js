import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('WebSocket authentication transport', () => {
  it('non inserisce il JWT nella query string registrata dai proxy', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/hooks/useWebSocket.js'), 'utf8');
    expect(source).not.toContain('notifications?token=');
    expect(source).not.toContain('encodeURIComponent(token)');
    expect(source).toContain('/api/ws/notifications`');
  });
});
