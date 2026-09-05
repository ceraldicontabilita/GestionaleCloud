// Unica UI PIN per le quattro app. React e le icone vengono forniti dall'app:
// CRA Menu usa React 19, ERP/HR React 18; nessuna seconda copia del runtime.
export function createPinModal(React, { LockKeyhole, Delete, X }) {
  const h = React.createElement;
  const { useEffect, useRef, useState } = React;
  return function PinModal({
    title = 'Accesso', subtitle = 'Inserisci il tuo PIN',
    color = '#5b7a6b', maxLength = 12, onVerify, onCancel,
  }) {
    const [pin, setPin] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const [choices, setChoices] = useState([]);
    const pending = useRef(false);
    const mounted = useRef(false);
    const panel = useRef(null);
    const field = useRef(null);
    const verifyRef = useRef(onVerify);
    const cancelRef = useRef(onCancel);
    verifyRef.current = onVerify;
    cancelRef.current = onCancel;

    useEffect(() => {
      mounted.current = true;
      const previous = document.activeElement;
      const overflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      field.current?.focus();
      return () => {
        mounted.current = false;
        document.body.style.overflow = overflow;
        if (previous?.isConnected) previous.focus();
      };
    }, []);

    const cancel = () => {
      if (!pending.current && cancelRef.current) {
        setPin('');
        cancelRef.current();
      }
    };
    const submit = async (identity = null) => {
      if (pending.current || !/^[0-9]{4,12}$/.test(pin)) return;
      pending.current = true;
      setBusy(true);
      setError('');
      try {
        const result = await verifyRef.current(pin, identity);
        if (mounted.current) {
          const next = result?.choices || [];
          setChoices(next);
          if (!next.length) setPin('');
        }
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : 'Accesso non riuscito');
          setPin('');
          setChoices([]);
        }
      } finally {
        pending.current = false;
        if (mounted.current) {
          setBusy(false);
          // Attende l'aggiornamento dei controlli disabilitati senza timer.
        }
      }
    };

    useEffect(() => {
      if (!busy) {
        const target = choices.length
          ? panel.current?.querySelector('[data-pin-choice]') : field.current;
        target?.focus();
      }
    }, [busy, choices]);

    const change = value => {
      if (pending.current) return;
      setPin(value.replace(/[^0-9]/g, '').slice(0, maxLength));
      setError('');
    };
    const keyDown = event => {
      if (event.key === 'Escape') { event.preventDefault(); cancel(); }
      if (event.key !== 'Tab') return;
      const controls = [...panel.current.querySelectorAll('button:not(:disabled),input:not(:disabled)')];
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || !controls.includes(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !controls.includes(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    const button = {
      minHeight: 52, border: '1px solid #e6e0d4', borderRadius: 12,
      background: '#f7f4ec', color: '#2a3329', font: 'inherit',
      fontSize: 22, fontWeight: 600, cursor: busy ? 'wait' : 'pointer',
      touchAction: 'manipulation', display: 'grid', placeItems: 'center', outlineColor: color,
    };
    return h('div', {
      style: { position: 'fixed', inset: 0, zIndex: 10000, padding: 16,
        background: 'rgba(42,51,41,.55)', display: 'grid', placeItems: 'center', overflowY: 'auto' },
      onClick: event => { if (event.target === event.currentTarget) cancel(); },
    }, h('section', {
      ref: panel, role: 'dialog', 'aria-modal': true, 'aria-label': title,
      'aria-busy': busy, onKeyDown: keyDown,
      style: { position: 'relative', width: '100%', maxWidth: 360, boxSizing: 'border-box',
        padding: '28px 24px', borderRadius: 24, border: '1px solid #e6e0d4',
        background: '#fffefb', color: '#2a3329', boxShadow: '0 24px 70px rgba(42,51,41,.3)' },
    },
    onCancel && h('button', { type: 'button', onClick: cancel, disabled: busy,
      'aria-label': 'Chiudi', style: { ...button, position: 'absolute', right: 8, top: 8, minWidth: 44, minHeight: 44, border: 0, background: 'transparent' } }, h(X, { size: 20 })),
    h('header', { style: { textAlign: 'center', marginBottom: 20 } },
      h(LockKeyhole, { size: 30, color, 'aria-hidden': true }),
      h('h2', { style: { margin: '12px 0 6px', fontSize: 21, fontFamily: 'inherit', color: '#2a3329' } }, title),
      h('p', { style: { margin: 0, color: '#6b7669', fontSize: 13 } }, choices.length ? 'Chi sta operando?' : subtitle)),
    error && h('p', { role: 'alert', 'data-testid': 'pin-error', style: { padding: 10, borderRadius: 8, color: '#8f3829', background: '#fbe6e2', fontSize: 14 } }, error),
    choices.length ? h('div', { style: { display: 'grid', gap: 10 } },
      ...choices.map(choice => h('button', { key: choice.id, type: 'button', 'data-pin-choice': true,
        disabled: busy, onClick: () => submit(choice.id), style: { ...button, background: color, color: '#fff', fontSize: 16 } }, choice.name)),
      h('button', { type: 'button', disabled: busy, style: { ...button, fontSize: 14 },
        onClick: () => { setChoices([]); setPin(''); setError(''); } }, 'Torna al PIN'))
    : h('form', { onSubmit: event => { event.preventDefault(); submit(); } },
      h('label', { style: { display: 'block', fontSize: 13, marginBottom: 6 } }, 'PIN',
        h('input', { ref: field, type: 'password', inputMode: 'numeric', autoComplete: 'current-password',
          'aria-label': 'PIN', value: pin, disabled: busy, maxLength,
          onChange: event => change(event.target.value),
          style: { width: '100%', boxSizing: 'border-box', height: 48, textAlign: 'center', fontSize: 24,
            letterSpacing: 6, background: '#fffefb', color: '#2a3329', outlineColor: color, border: '1px solid #e6e0d4', borderRadius: 10, marginTop: 6 } })),
      h('div', { 'data-testid': 'pin-keypad', style: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginTop: 14 } },
        ...['1','2','3','4','5','6','7','8','9','C','0','delete'].map(key => h('button', {
          key, type: 'button', disabled: busy, style: button,
          'aria-label': key === 'delete' ? 'Cancella ultima cifra' : key === 'C' ? 'Cancella PIN' : key,
          'data-testid': `pin-key-${key === 'delete' ? 'backspace' : key}`,
          onClick: () => { change(key === 'delete' ? pin.slice(0, -1) : key === 'C' ? '' : pin + key); field.current?.focus(); },
        }, key === 'delete' ? h(Delete, { size: 22 }) : key))),
      h('button', { type: 'submit', disabled: busy || pin.length < 4, 'data-testid': 'pin-key-submit',
        style: { ...button, width: '100%', marginTop: 16, background: color, color: '#fff', fontSize: 16, opacity: busy || pin.length < 4 ? .55 : 1 } }, busy ? 'Verifica…' : 'Accedi')),
    h('div', { role: 'status', 'aria-live': 'polite', style: { minHeight: 18, marginTop: 8, textAlign: 'center', fontSize: 12, color: '#6b7669' } }, busy ? 'Accesso in corso' : '')
    ));
  };
}
