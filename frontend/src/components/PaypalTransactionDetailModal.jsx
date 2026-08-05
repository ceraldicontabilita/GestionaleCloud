import React, { useState, useEffect } from 'react';
import {
  X,
  FileText,
  User,
  CreditCard,
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
import { toast } from 'sonner';
import api from '../api';
import { Button, Badge } from './ds';
import DocumentViewerModal from './DocumentViewerModal';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';

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
export default function PaypalTransactionDetailModal({
  open,
  onClose,
  transactionId,
  onOpenInvoice,
}) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [gmailLoading, setGmailLoading] = useState(false);
  const [associandoId, setAssociandoId] = useState(null);
  const [refreshSerial, setRefreshSerial] = useState(0);
  const [pdfViewer, setPdfViewer] = useState(null); // {title, src(blob)} — viewer canonico §8
  const [gmailData, setGmailData] = useState(null);

  useEffect(() => {
    if (!open || !transactionId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setData(null);
      setGmailData(null);
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
  }, [open, transactionId, refreshSerial]);

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
  // Se il job automatico ha già cercato su Gmail, mostra subito i risultati
  const gmailShown =
    gmailData ||
    (tx?.gmail_candidati?.length
      ? { ok: true, risultati: tx.gmail_candidati, auto: true }
      : null);

  const fmtEuro = (n) => {
    if (n === undefined || n === null || Number.isNaN(Number(n))) return '—';
    return new Intl.NumberFormat('it-IT', {
      style: 'currency', currency: 'EUR'
    }).format(Math.abs(Number(n)));
  };
  const fmtDate = (d) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleDateString('it-IT').replaceAll('/', '-');
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
        toast.error('PDF non disponibile');
        return;
      }
      // base64 → blob → URL → nuova tab
      const byteChars = atob(b64);
      const bytes = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      // Viewer canonico §8 (niente nuova scheda); l'URL blob viene revocato alla chiusura.
      setPdfViewer({ title: `📄 Verbale ${verbale?.numero_verbale || ''}`, src: url });
    } catch (e) {
      toast.error('Errore apertura PDF: ' + (e?.response?.data?.detail || e?.message));
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
    // Uso 'invoice_id' esplicito così la pagina Archivio può fare scroll
    // + highlight. Il param 'id' è supportato come alias per retrocompat.
    navigate(`/fatture?invoice_id=${encodeURIComponent(fId)}`);
    onClose?.();
  };

  const handleMapFornitore = () => {
    // Rimanda alla sezione mapping, l'utente mapperà lì
    navigate('/riconciliazione/paypal?tab=mapping');
    onClose?.();
  };

  const handleManualInvoiceSearch = () => {
    const search = tx.nome_controparte || tx.payer_name || email_controparte || '';
    const invoiceId = tx?.fattura_id || tx?.invoice_id || '';

    if (invoiceId) {
      navigate(`/fatture?invoice_id=${encodeURIComponent(invoiceId)}`);
    } else if (search) {
      navigate(`/fatture#search=${encodeURIComponent(search)}`);
    } else {
      navigate('/fatture');
    }

    onClose?.();
  };

  const handleAssociaFattura = async (fattura) => {
    if (!fattura?.associabile || !fattura?.id) return;
    setAssociandoId(fattura.id);
    try {
      await api.post(
        `/api/paypal-statements/transazione/${encodeURIComponent(
          tx.transaction_id || transactionId
        )}/associa`,
        { fattura_id: fattura.id }
      );
      toast.success(
        `Fattura ${fattura.invoice_number || fattura.numero_fattura || ''} associata con controlli superati`
      );
      setRefreshSerial(value => value + 1);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : detail?.messaggio || e?.message || 'Associazione non riuscita'
      );
    } finally {
      setAssociandoId(null);
    }
  };

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(15,39,68,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.lg,
          width: '100%', maxWidth: 720, maxHeight: '90vh',
          display: 'flex', flexDirection: 'column',
          boxShadow: SHADOWS.modal,
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px',
          background: COLORS.primary, color: '#fff',
        }}>
          <CreditCard size={18} />
          <div style={{ fontSize: 15, fontWeight: 600, flex: 1 }}>
            Dettaglio Transazione PayPal
          </div>
          <Button
            variant="ghost"
            onClick={onClose}
            aria-label="Chiudi"
            style={{ color: '#fff', padding: 4, width: 28, height: 28 }}
          >
            <X size={20} />
          </Button>
        </div>

        {/* Body */}
        <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: COLORS.textMuted, padding: 30 }}>
              <Loader2 size={18} className="animate-spin" />
              Caricamento dettagli…
            </div>
          )}

          {error && (
            <div style={{
              background: COLORS.dangerLight, border: `1px solid ${COLORS.danger}`, color: COLORS.danger,
              padding: 12, borderRadius: BORDER_RADIUS.sm, fontSize: 13,
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
                  <span style={{ fontWeight: 700, color: (tx.lordo ?? tx.amount ?? 0) < 0 ? COLORS.danger : COLORS.success }}>
                    {fmtEuro(tx.lordo ?? tx.amount)}
                  </span>
                } />
                <Row icon={<User size={12} />} label="Controparte" value={tx.nome_controparte || tx.payer_name || '—'} />
                <Row icon={<Mail size={12} />} label="Email" value={tx.email_controparte || tx.payer_email || '—'} />
                <Row label="Tipo" value={translateTipo(tx.tipo || tx.type)} />
                <Row label="Stato" value={translateStato(tx.status || tx.stato)} />
                <Row label="Descrizione" value={tx.descrizione || tx.subject || '—'} />
                {tx.paypal_account_id && (
                  <Row icon={<Hash size={12} />} label="Account PayPal controparte" value={<code style={{ fontSize: 11 }}>{tx.paypal_account_id}</code>} />
                )}
                {tx.invoice_id_fornitore && (
                  <Row icon={<Receipt size={12} />} label="Rif. fattura PayPal (invoice_id)" value={<strong>{tx.invoice_id_fornitore}</strong>} />
                )}
                {tx.transaction_subject && (
                  <Row label="Oggetto transazione" value={tx.transaction_subject} />
                )}
                {tx.custom_field && (
                  <Row label="Campo personalizzato" value={tx.custom_field} />
                )}
                <Row label="Riconciliato in banca" value={
                  tx.riconciliato_banca
                    ? <Badge variant="success">Sì</Badge>
                    : <Badge variant="neutral">No</Badge>
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
                      ? <Badge variant="success">Pagato</Badge>
                      : <Badge variant="warning">{verbale.stato || 'Da pagare'}</Badge>
                  } />
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                    {data.has_pdf_verbale && (
                      <Button variant="primary" size="sm" onClick={handleOpenVerbalePdf} iconLeft={<Download size={13} />}>
                        Apri PDF verbale
                      </Button>
                    )}
                    <Button variant="secondary" size="sm" onClick={handleGoToVerbale} iconLeft={<ExternalLink size={13} />}>
                      Vai alla scheda verbale
                    </Button>
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
                      marginTop: 10, padding: 10, borderRadius: BORDER_RADIUS.sm,
                      background: trattenuta.stato === 'applicata' ? COLORS.successLight : COLORS.warningLight,
                      border: `1px solid ${trattenuta.stato === 'applicata' ? COLORS.success : COLORS.warning}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600 }}>
                        <Receipt size={13} />
                        Trattenuta in busta paga
                      </div>
                      <div style={{ fontSize: 12, color: COLORS.gray[600], marginTop: 6 }}>
                        Importo: <strong>{fmtEuro(trattenuta.importo)}</strong>
                        {trattenuta.mese && trattenuta.anno && (
                          <> · Mese {trattenuta.mese}/{trattenuta.anno}</>
                        )}
                        {trattenuta.stato && <> · Stato: <em>{trattenuta.stato}</em></>}
                      </div>
                    </div>
                  ) : verbale && (
                    <div style={{
                      marginTop: 10, padding: 10, borderRadius: BORDER_RADIUS.sm,
                      background: COLORS.dangerLight, border: `1px solid ${COLORS.danger}`,
                      fontSize: 12, color: COLORS.danger,
                    }}>
                      <AlertCircle size={13} style={{ verticalAlign: 'text-bottom', marginRight: 4 }} />
                      Questa transazione è collegata al dipendente ma non c'è ancora una trattenuta in busta paga.
                    </div>
                  )}

                  <div style={{ marginTop: 10 }}>
                    <Button variant="secondary" size="sm" onClick={handleGoToDipendente} iconLeft={<ExternalLink size={13} />}>
                      Scheda dipendente
                    </Button>
                  </div>
                </Section>
              )}

              {/* ============ SEZIONE 4 - FORNITORE / FATTURE ============ */}
              <Section icon={<Link2 size={14} />} title="Fornitore e fatture">
                {mapping ? (
                  <>
                    <Row label="Fornitore mappato" value={
                      <strong>{mapping.fornitore_nome || mapping.fornitore_ragione_sociale || '—'}</strong>
                    } />
                    <Row label="P.IVA / CF" value={<code>{mapping.fornitore_piva || '—'}</code>} />
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: COLORS.warning, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <AlertCircle size={13} style={{ verticalAlign: 'text-bottom' }} />
                    Account PayPal non mappato a un fornitore.
                    <Badge variant="warning" onClick={handleMapFornitore} style={{ cursor: 'pointer' }}>
                      Mappa fornitore
                    </Badge>
                  </div>
                )}

                {fatture.length > 0 ? (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.3 }}>
                      Fatture verificate di questo fornitore ({fatture.length})
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textSubtle, fontStyle: 'italic', marginBottom: 8 }}>
                      Sono mostrate solo fatture con identità fornitore verificata. Il collegamento è disponibile
                      soltanto se coincidono sia il numero fattura sia l'importo al centesimo ({fmtEuro(tx.lordo ?? tx.amount)}).
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {fatture.map((f) => {
                        const importoFattura = Math.abs(Number(f.total_amount ?? f.importo_totale ?? 0));
                        const importoTx = Math.abs(Number(tx.lordo ?? tx.amount ?? 0));
                        const matchRiferimento = f.match === 'riferimento_e_fornitore';
                        const matchImporto = Boolean(f.associabile) && (
                          matchRiferimento ||
                          (importoTx > 0 && Math.abs(importoFattura - importoTx) < 0.06)
                        );
                        return (
                          <div
                            key={f.id}
                            onClick={() => handleGoToFattura(f.id)}
                            style={{
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              padding: '8px 10px',
                              background: matchImporto ? COLORS.accentSoft : COLORS.bgAlt,
                              borderRadius: BORDER_RADIUS.sm,
                              cursor: 'pointer', fontSize: 12,
                              border: `1px solid ${matchImporto ? COLORS.accent : COLORS.border}`,
                              transition: 'background 120ms',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.background = matchImporto ? '#fde68a' : COLORS.gray[100]; }}
                            onMouseLeave={e => { e.currentTarget.style.background = matchImporto ? COLORS.accentSoft : COLORS.bgAlt; }}
                            title="Clicca per aprire la fattura"
                          >
                            <span>
                              <strong>{f.invoice_number || f.numero_fattura}</strong>
                              <span style={{ color: COLORS.textMuted, marginLeft: 8 }}>
                                {fmtDate(f.invoice_date || f.data_fattura)}
                              </span>
                              {matchRiferimento ? (
                                <span style={{ marginLeft: 8, fontSize: 10, color: COLORS.success, fontWeight: 700 }}>
                                  ✓ numero e fornitore verificati
                                </span>
                              ) : matchImporto && (
                                <span style={{ marginLeft: 8, fontSize: 10, color: COLORS.accent, fontWeight: 700 }}>
                                  ★ fornitore e importo verificati
                                </span>
                              )}
                              {f.match_evidenze?.length > 0 && (
                                <span style={{ display: 'block', marginTop: 2, fontSize: 9, color: COLORS.textSubtle }}>
                                  Evidenze: {f.match_evidenze.join(', ')}
                                </span>
                              )}
                            </span>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                              {fmtEuro(importoFattura)}
                              <Badge
                                variant="primary"
                                onClick={e => {
                                  e.stopPropagation();
                                  if (onOpenInvoice) {
                                    onOpenInvoice({
                                      id: f.id,
                                      numero: f.numero_fattura || f.numero || f.fornitore,
                                    });
                                    return;
                                  }
                                  window.open(
                                    f.view_url || `/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`,
                                    '_blank'
                                  );
                                }}
                                title="Apri la fattura (funziona anche se è di un altro anno)"
                                style={{ background: COLORS.primary, color: '#fff', cursor: 'pointer' }}
                              >
                                Vedi
                              </Badge>
                              {f.associabile && (
                                <Button
                                  size="sm"
                                  variant="primary"
                                  disabled={associandoId === f.id}
                                  onClick={e => {
                                    e.stopPropagation();
                                    handleAssociaFattura(f);
                                  }}
                                >
                                  {associandoId === f.id ? 'Associo…' : 'Associa'}
                                </Button>
                              )}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div>
                    <EmptyMsg text="Nessuna fattura trovata automaticamente." />
                    <div style={{ marginTop: 6, fontSize: 11, color: COLORS.textSubtle }}>
                      Il sistema ha cercato per P.IVA del fornitore mappato, per parole nel nome controparte
                      {email_controparte ? `, e per email ${email_controparte}` : ''}.
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleManualInvoiceSearch}
                        iconLeft={<ExternalLink size={13} />}
                      >
                        Cerca fattura manualmente
                      </Button>
                    </div>
                  </div>
                )}
              </Section>

              {/* Ricerca su GMAIL: fatture esterne che non passano dallo SDI
                  (SaaS, fornitori esteri: Spotify, MongoDB, OpenAI...) */}
              <Section icon={<Mail size={15} />} title="Cerca su Gmail (fatture esterne)">
                <div style={{ fontSize: 11, color: COLORS.textSubtle, fontStyle: 'italic', marginBottom: 8 }}>
                  Se la fattura non è nel gestionale potrebbe essere una ricevuta esterna che non
                  passa dal Sistema di Interscambio: cerco su Gmail per importo
                  ({fmtEuro(tx.lordo ?? tx.amount)}) e controparte intorno alla data della transazione.
                </div>
                {!gmailShown && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={async () => {
                      setGmailLoading(true);
                      try {
                        const r = await api.get(
                          `/api/paypal-statements/transazione/${encodeURIComponent(
                            tx.transaction_id || transactionId
                          )}/cerca-gmail`
                        );
                        setGmailData(r.data);
                      } catch (e2) {
                        setGmailData({
                          ok: false,
                          risultati: [],
                          errore: e2?.response?.data?.detail || e2?.message || 'Errore ricerca Gmail',
                        });
                      } finally {
                        setGmailLoading(false);
                      }
                    }}
                    iconLeft={gmailLoading ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />}
                  >
                    {gmailLoading ? 'Ricerca in corso…' : 'Cerca su Gmail'}
                  </Button>
                )}
                {gmailShown && !gmailShown.ok && (
                  <div style={{ fontSize: 12, color: COLORS.danger }}>
                    {gmailShown.errore || 'Ricerca non riuscita'}
                  </div>
                )}
                {gmailShown && gmailShown.ok && gmailShown.risultati.length === 0 && (
                  <EmptyMsg text="Nessuna email trovata per importo/controparte in quel periodo." />
                )}
                {gmailShown && gmailShown.ok && gmailShown.risultati.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {gmailShown.risultati.map((m, i) => (
                      <a
                        key={m.message_id || i}
                        href={m.gmail_link || 'https://mail.google.com'}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          padding: '8px 10px', background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.sm,
                          border: `1px solid ${COLORS.border}`, fontSize: 12, textDecoration: 'none',
                          color: COLORS.text, gap: 8,
                        }}
                        title="Apri il messaggio in Gmail"
                      >
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <strong>{m.subject || '(senza oggetto)'}</strong>
                          <span style={{ color: COLORS.textMuted, marginLeft: 8 }}>{m.from}</span>
                        </span>
                        <span style={{ whiteSpace: 'nowrap', color: COLORS.textMuted, fontSize: 11 }}>
                          {m.has_attachment ? '📎 ' : ''}
                          {m.date ? m.date.slice(0, 22) : ''}
                          <ExternalLink size={11} style={{ marginLeft: 6, verticalAlign: 'middle' }} />
                        </span>
                      </a>
                    ))}
                  </div>
                )}
              </Section>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 18px',
          background: COLORS.bgAlt,
          borderTop: `1px solid ${COLORS.border}`,
          display: 'flex', justifyContent: 'flex-end',
        }}>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Chiudi
          </Button>
        </div>
      </div>

      {pdfViewer && (
        <DocumentViewerModal
          title={pdfViewer.title}
          src={pdfViewer.src}
          documentType="verbale"
          onClose={() => {
            URL.revokeObjectURL(pdfViewer.src);
            setPdfViewer(null);
          }}
        />
      )}
    </div>
  );
}

// ---------- sub-components ----------

function Section({ icon, title, children }) {
  return (
    <div style={{
      border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.lg,
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '8px 12px', background: COLORS.bgAlt,
        borderBottom: `1px solid ${COLORS.border}`,
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 12, fontWeight: 600, color: COLORS.primary,
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
      borderBottom: `1px dashed ${COLORS.gray[100]}`,
    }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: COLORS.textMuted, fontSize: 12 }}>
        {icon}
        {label}
      </span>
      <span style={{ color: COLORS.primary, textAlign: 'right', maxWidth: '60%', wordBreak: 'break-word' }}>
        {value}
      </span>
    </div>
  );
}

function EmptyMsg({ text }) {
  return (
    <div style={{ padding: '6px 4px', fontSize: 12, color: COLORS.textSubtle, fontStyle: 'italic' }}>
      {text}
    </div>
  );
}
