import React, { useState, useEffect } from 'react';
import {
  X,
  FileText,
  User,
  CreditCard,
  CheckCircle,
  AlertCircle,
  ExternalLink,
  Download,
  Mail,
  Hash,
  Calendar,
  Euro,
  Loader2,
  Link2,
  Receipt,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

// Traduzione codici PayPal in labels leggibili.
// Fonte: https://developer.paypal.com/api/rest/reference/transactions-search/event-codes/
const PAYPAL_TIPO_LABELS = {
  T0000: 'Pagamento generico',
  T0001: 'Commissione PayPal',
  T0002: 'Pagamento ricorrente',
  T0003: 'Pagamento a fornitore SaaS',
  T0004: 'Rimborso ricevuto',
  T0005: 'Payout di massa',
  T0006: 'Giroconto dal conto bancario',
  T0007: 'Prelievo al conto bancario',
  T0008: 'Donazione',
  T0009: 'Acquisto con carta',
  T0010: 'Trasferimento verso PayPal',
  T0011: 'Pagamento a dipendente',
  T0012: 'Rimborso parziale',
  T0013: 'Ricarica conto',
  T0019: 'Chargeback (storno)',
  T0020: 'Commissione di conversione valuta',
  T1106: 'Regolamento chargeback',
  T1107: 'Rimborso',
  T1108: 'Rimborso completo',
  T0200: 'Ricevuto via carta ospite',
  T1201: 'Chargeback risolto',
};
const PAYPAL_STATO_LABELS = {
  S: 'Successo',
  P: 'In sospeso',
  F: 'Fallita',
  D: 'Negata',
  V: 'Annullata',
  R: 'Rimborsata',
  COMPLETED: 'Completata',
  PENDING: 'In sospeso',
  FAILED: 'Fallita',
  DENIED: 'Negata',
};
const translateTipo = (t) => (t && PAYPAL_TIPO_LABELS[t]) ? `${PAYPAL_TIPO_LABELS[t]} (${t})` : (t || '—');
const translateStato = (s) => (s && PAYPAL_STATO_LABELS[s.toUpperCase?.() || s]) ? PAYPAL_STATO_LABELS[s.toUpperCase?.() || s] : (s || '—');

/**
 * Modale dettaglio transazione PayPal.
 * Apre un overlay al centro dello schermo con 4 sezioni:
 *   1. Dettagli transazione PayPal (id, email, metodo, data, importo, stato)
 *   2. Collegamenti: verbale, fatture, fornitore mappato
 *   3. Dipendente associato + trattenuta in busta paga (se presenti)
 *   4. Azioni: apri PDF, vai al verbale, vai al dipendente, mappa fornitore
 *
 * Richiede l'endpoint GET /api/paypal-statements/transazione/{id}/dettaglio
 * che ritorna tutti i collegamenti già risolti.
 */
export default function PaypalTransactionDetailModal({ open, onClose, transactionId }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !transactionId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        const r = await api.get(`/api/paypal-statements/transazione/${encodeURIComponent(transactionId)}/dettaglio`);
        if (!cancelled) setData(r.data);
      } catch (e) {
        if (!cancelled) {
          setError(e?.response?.data?.detail || e?.message || 'Errore caricamento dettaglio');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, transactionId]);

  // Chiudi con ESC
  useEffect(() => {
    if (!open) return;
    const h = e => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  if (!open) return null;

  const tx = data?.transaction;
  const verbale = data?.verbale;
  const dipendente = data?.dipendente;
  const trattenuta = data?.trattenuta_busta_paga;
  const mapping = data?.mapping_fornitore;
  const fatture = data?.fatture_collegate || [];
  const email_controparte = tx?.email_controparte || tx?.payer_email || '';

  const fmtEuro = (n) => {
    if (n === undefined || n === null || Number.isNaN(Number(n))) return '—';
    return new Intl.NumberFormat('it-IT', {
      style: 'currency', currency: 'EUR'
    }).format(Math.abs(Number(n)));
  };
  const fmtDate = (d) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleDateString('it-IT');
    } catch { return d; }
  };

  const handleOpenVerbalePdf = async () => {
    if (!verbale?.numero_verbale) return;
    try {
      const r = await api.get(
        `/api/verbali-noleggio/pdf/${encodeURIComponent(verbale.numero_verbale)}`
      );
      const b64 = r.data?.content_base64;
      if (!b64) {
        alert('PDF non disponibile');
        return;
      }
      // base64 → blob → URL → nuova tab
      const byteChars = atob(b64);
      const bytes = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      // libero l'URL dopo qualche secondo
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) {
      alert('Errore apertura PDF: ' + (e?.response?.data?.detail || e?.message));
    }
  };

  const handleGoToVerbale = () => {
    if (!verbale?.numero_verbale) return;
    navigate(`/verbali-noleggio/${encodeURIComponent(verbale.numero_verbale)}`);
    onClose?.();
  };

  const handleGoToDipendente = () => {
    if (!dipendente?.id) return;
    navigate(`/dipendenti?id=${encodeURIComponent(dipendente.id)}`);
    onClose?.();
  };

  const handleGoToFattura = (fId) => {
    navigate(`/fatture?id=${encodeURIComponent(fId)}`);
    onClose?.();
  };

  const handleMapFornitore = () => {
    // Rimanda alla sezione mapping, l'utente mapperà lì
    navigate('/riconciliazione/paypal?tab=mapping');
    onClose?.();
  };

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#fff', borderRadius: 12,
          width: '100%', maxWidth: 720, maxHeight: '90vh',
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px',
          background: '#0f2744', color: '#fff',
        }}>
          <CreditCard size={18} />
          <div style={{ fontSize: 15, fontWeight: 600, flex: 1 }}>
            Dettaglio Transazione PayPal
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: '#fff',
              cursor: 'pointer', padding: 4, display: 'flex',
            }}
            aria-label="Chiudi"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#64748b', padding: 30 }}>
              <Loader2 size={18} className="animate-spin" />
              Caricamento dettagli…
            </div>
          )}

          {error && (
            <div style={{
              background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b',
              padding: 12, borderRadius: 8, fontSize: 13,
            }}>
              <AlertCircle size={16} style={{ verticalAlign: 'text-bottom' }} /> {String(error)}
            </div>
          )}

          {!loading && !error && tx && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* ============ SEZIONE 1 - PAYPAL ============ */}
              <Section icon={<CreditCard size={14} />} title="Dettagli PayPal">
                <Row icon={<Hash size={12} />} label="Transaction ID" value={<code style={{ fontSize: 11 }}>{tx.transaction_id || tx.id || '—'}</code>} />
                <Row icon={<Calendar size={12} />} label="Data" value={fmtDate(tx.data || tx.date)} />
                <Row icon={<Euro size={12} />} label="Importo" value={
                  <span style={{ fontWeight: 700, color: (tx.lordo ?? tx.amount ?? 0) < 0 ? '#dc2626' : '#16a34a' }}>
                    {fmtEuro(tx.lordo ?? tx.amount)}
                  </span>
                } />
                <Row icon={<User size={12} />} label="Controparte" value={tx.nome_controparte || tx.payer_name || '—'} />
                <Row icon={<Mail size={12} />} label="Email" value={tx.email_controparte || tx.payer_email || '—'} />
                <Row label="Tipo" value={translateTipo(tx.tipo || tx.type)} />
                <Row label="Stato" value={translateStato(tx.status || tx.stato)} />
                <Row label="Descrizione" value={tx.descrizione || tx.subject || '—'} />
                <Row label="Riconciliato in banca" value={
                  tx.riconciliato_banca
                    ? <Badge color="#16a34a" text="Sì" icon={<CheckCircle size={11} />} />
                    : <Badge color="#94a3b8" text="No" />
                } />
              </Section>

              {/* ============ SEZIONE 2 - VERBALE / COLLEGAMENTI ============ */}
              {verbale ? (
                <Section icon={<FileText size={14} />} title="Verbale collegato">
                  <Row label="Numero verbale" value={<strong>{verbale.numero_verbale || '—'}</strong>} />
                  <Row label="Targa" value={verbale.targa || '—'} />
                  <Row label="Ente emittente" value={verbale.ente || verbale.ente_emittente || '—'} />
                  <Row label="Data verbale" value={fmtDate(verbale.data || verbale.data_verbale)} />
                  <Row label="Importo verbale" value={fmtEuro(verbale.importo)} />
                  <Row label="Stato" value={
                    verbale.stato === 'pagato'
                      ? <Badge color="#16a34a" text="Pagato" icon={<CheckCircle size={11} />} />
                      : <Badge color="#f59e0b" text={verbale.stato || 'Da pagare'} />
                  } />
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                    {data.has_pdf_verbale && (
                      <Button onClick={handleOpenVerbalePdf} icon={<Download size={13} />} text="Apri PDF verbale" />
                    )}
                    <Button onClick={handleGoToVerbale} icon={<ExternalLink size={13} />} text="Vai alla scheda verbale" variant="secondary" />
                  </div>
                </Section>
              ) : (
                <Section icon={<FileText size={14} />} title="Verbale collegato">
                  <EmptyMsg text="Nessun verbale associato a questa transazione." />
                </Section>
              )}

              {/* ============ SEZIONE 3 - DIPENDENTE E CEDOLINO ============ */}
              {dipendente && (
                <Section icon={<User size={14} />} title="Dipendente associato">
                  <Row label="Nome" value={<strong>{`${dipendente.nome || ''} ${dipendente.cognome || ''}`.trim() || '—'}</strong>} />
                  <Row label="Codice Fiscale" value={<code style={{ fontSize: 11 }}>{dipendente.codice_fiscale || '—'}</code>} />
                  <Row label="Ruolo" value={dipendente.ruolo || '—'} />

                  {trattenuta ? (
                    <div style={{
                      marginTop: 10, padding: 10, borderRadius: 8,
                      background: trattenuta.stato === 'applicata' ? '#f0fdf4' : '#fefce8',
                      border: `1px solid ${trattenuta.stato === 'applicata' ? '#86efac' : '#fde68a'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600 }}>
                        <Receipt size={13} />
                        Trattenuta in busta paga
                      </div>
                      <div style={{ fontSize: 12, color: '#475569', marginTop: 6 }}>
                        Importo: <strong>{fmtEuro(trattenuta.importo)}</strong>
                        {trattenuta.mese && trattenuta.anno && (
                          <> · Mese {trattenuta.mese}/{trattenuta.anno}</>
                        )}
                        {trattenuta.stato && <> · Stato: <em>{trattenuta.stato}</em></>}
                      </div>
                    </div>
                  ) : verbale && (
                    <div style={{
                      marginTop: 10, padding: 10, borderRadius: 8,
                      background: '#fef2f2', border: '1px solid #fecaca',
                      fontSize: 12, color: '#991b1b',
                    }}>
                      <AlertCircle size={13} style={{ verticalAlign: 'text-bottom', marginRight: 4 }} />
                      Questa transazione è collegata al dipendente ma non c'è ancora una trattenuta in busta paga.
                    </div>
                  )}

                  <div style={{ marginTop: 10 }}>
                    <Button onClick={handleGoToDipendente} icon={<ExternalLink size={13} />} text="Scheda dipendente" variant="secondary" />
                  </div>
                </Section>
              )}

              {/* ============ SEZIONE 4 - FORNITORE / FATTURE ============ */}
              <Section icon={<Link2 size={14} />} title="Fornitore e fatture">
                {mapping ? (
                  <Row label="Fornitore mappato" value={
                    <strong>{mapping.fornitore_nome || mapping.fornitore_ragione_sociale || '—'}</strong>
                  } />
                ) : (
                  <div style={{ fontSize: 12, color: '#f59e0b', marginBottom: 8 }}>
                    <AlertCircle size={13} style={{ verticalAlign: 'text-bottom', marginRight: 4 }} />
                    Account PayPal non mappato a un fornitore.
                    <button
                      onClick={handleMapFornitore}
                      style={{
                        marginLeft: 8, padding: '3px 8px', fontSize: 11,
                        background: '#fef3c7', border: '1px solid #fcd34d',
                        borderRadius: 4, cursor: 'pointer', color: '#92400e',
                      }}
                    >
                      Mappa fornitore
                    </button>
                  </div>
                )}

                {fatture.length > 0 ? (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.3 }}>
                      Altre fatture di questo fornitore ({fatture.length})
                    </div>
                    <div style={{ fontSize: 11, color: '#94a3b8', fontStyle: 'italic', marginBottom: 8 }}>
                      Sono le fatture di {tx.nome_controparte || tx.payer_name || 'questo fornitore'} nel gestionale.
                      Le fatture con importo uguale a questa transazione (<strong>{fmtEuro(tx.lordo ?? tx.amount)}</strong>) sono evidenziate in oro —
                      potrebbero essere ciò che questo pagamento PayPal ha saldato.
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {fatture.map((f) => {
                        const importoFattura = Math.abs(Number(f.total_amount ?? f.importo_totale ?? 0));
                        const importoTx = Math.abs(Number(tx.lordo ?? tx.amount ?? 0));
                        const matchImporto = importoTx > 0 && Math.abs(importoFattura - importoTx) < 0.02;
                        return (
                          <div
                            key={f.id}
                            onClick={() => handleGoToFattura(f.id)}
                            style={{
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              padding: '8px 10px',
                              background: matchImporto ? '#fef3c7' : '#f8fafc',
                              borderRadius: 6,
                              cursor: 'pointer', fontSize: 12,
                              border: `1px solid ${matchImporto ? '#fcd34d' : '#e2e8f0'}`,
                              transition: 'background 120ms',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.background = matchImporto ? '#fde68a' : '#eef2f7'; }}
                            onMouseLeave={e => { e.currentTarget.style.background = matchImporto ? '#fef3c7' : '#f8fafc'; }}
                            title="Clicca per aprire la fattura"
                          >
                            <span>
                              <strong>{f.invoice_number || f.numero_fattura}</strong>
                              <span style={{ color: '#64748b', marginLeft: 8 }}>
                                {fmtDate(f.invoice_date || f.data_fattura)}
                              </span>
                              {matchImporto && (
                                <span style={{ marginLeft: 8, fontSize: 10, color: '#92400e', fontWeight: 700 }}>
                                  ★ stesso importo
                                </span>
                              )}
                            </span>
                            <span>
                              {fmtEuro(importoFattura)}
                              <ExternalLink size={11} style={{ marginLeft: 6, verticalAlign: 'middle', color: '#64748b' }} />
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div>
                    <EmptyMsg text="Nessuna fattura trovata automaticamente." />
                    <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
                      Il sistema ha cercato per P.IVA del fornitore mappato, per parole nel nome controparte
                      {email_controparte ? `, e per email ${email_controparte}` : ''}.
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Button
                        onClick={() => {
                          // apre la pagina fatture filtrando per la data della transazione e l'importo
                          // così l'utente può trovarla e associarla a mano
                          const q = new URLSearchParams();
                          if (tx.nome_controparte || tx.payer_name) q.set('fornitore', tx.nome_controparte || tx.payer_name);
                          const amt = Math.abs(Number(tx.lordo ?? tx.amount ?? 0));
                          if (amt) q.set('importo', amt.toFixed(2));
                          navigate(`/fatture?${q.toString()}`);
                          onClose?.();
                        }}
                        icon={<ExternalLink size={13} />}
                        text="Cerca fattura manualmente"
                        variant="secondary"
                      />
                    </div>
                  </div>
                )}
              </Section>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 18px',
          background: '#f8fafc',
          borderTop: '1px solid #e2e8f0',
          display: 'flex', justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '7px 14px', fontSize: 13, fontWeight: 500,
              background: '#fff', color: '#475569',
              border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'pointer',
            }}
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- sub-components ----------

function Section({ icon, title, children }) {
  return (
    <div style={{
      border: '1px solid #e2e8f0', borderRadius: 10,
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '8px 12px', background: '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 12, fontWeight: 600, color: '#0f2744',
        textTransform: 'uppercase', letterSpacing: 0.4,
      }}>
        {icon} {title}
      </div>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {children}
      </div>
    </div>
  );
}

function Row({ icon, label, value }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      fontSize: 13, padding: '3px 0', minHeight: 22,
      borderBottom: '1px dashed #f1f5f9',
    }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#64748b', fontSize: 12 }}>
        {icon}
        {label}
      </span>
      <span style={{ color: '#0f2744', textAlign: 'right', maxWidth: '60%', wordBreak: 'break-word' }}>
        {value}
      </span>
    </div>
  );
}

function Badge({ color, text, icon }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
      background: `${color}18`, color,
    }}>
      {icon}{text}
    </span>
  );
}

function Button({ onClick, icon, text, variant = 'primary' }) {
  const styles = {
    primary: { background: '#b8860b', color: '#fff', border: '1px solid #b8860b' },
    secondary: { background: '#fff', color: '#475569', border: '1px solid #cbd5e1' },
  };
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '6px 11px', fontSize: 12, fontWeight: 500,
        borderRadius: 6, cursor: 'pointer',
        ...styles[variant],
      }}
    >
      {icon}{text}
    </button>
  );
}

function EmptyMsg({ text }) {
  return (
    <div style={{ padding: '6px 4px', fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
      {text}
    </div>
  );
}
