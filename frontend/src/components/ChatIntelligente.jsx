/**
 * ChatIntelligente - Chat widget per interrogare il gestionale in linguaggio naturale
 * Usa AI per interpretare le domande e fornire risposte basate sui dati reali.
 */
import React, { useState, useRef, useEffect } from 'react';
import api from '../api';
import { Button, Input } from './ds';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../lib/utils';

export default function ChatIntelligente() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      type: 'assistant',
      text: '👋 Ciao! Sono il tuo assistente contabile AI. Puoi chiedermi informazioni su fatture, F24, stipendi, fornitori, bilanci e molto altro. Prova a farmi una domanda!',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [useAi, setUseAi] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  const SpeechRecognitionCtor =
    typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
    };
  }, []);

  const toggleListening = () => {
    if (!SpeechRecognitionCtor) return;

    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = 'it-IT';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = event => {
      const testo = event.results?.[0]?.[0]?.transcript;
      if (testo) setInput(testo);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');

    // Aggiungi messaggio utente
    setMessages(prev => [
      ...prev,
      {
        type: 'user',
        text: question,
        timestamp: new Date().toISOString(),
      },
    ]);

    setIsLoading(true);

    try {
      const response = await api.post('/api/chat/ask', {
        question,
        use_ai: useAi,
      });

      const data = response.data;

      // Costruisci la risposta
      let responseText = data.response || 'Non ho trovato dati per la tua richiesta.';

      // Aggiungi info extra se disponibili
      if (data.query_type && data.summary) {
        const summary = data.summary;
        if (summary.count !== undefined) {
          responseText += `\n\n📊 *Dati trovati: ${summary.count}*`;
        }
      }

      setMessages(prev => [
        ...prev,
        {
          type: 'assistant',
          text: responseText,
          timestamp: data.timestamp || new Date().toISOString(),
          queryType: data.query_type,
          dataCount: data.data_count,
          // Risposta strutturata del motore AI (assenti col motore a keyword)
          affidabilita: data.livello_affidabilita,
          fonti: data.documenti_consultati,
          datiMancanti: data.dati_mancanti,
          anomalie: data.anomalie,
          azioniProposte: data.azioni_proposte,
        },
      ]);
    } catch (error) {
      console.error('Errore chat:', error);
      setMessages(prev => [
        ...prev,
        {
          type: 'assistant',
          text: `❌ Errore: ${error.response?.data?.detail || error.message || 'Si è verificato un errore'}`,
          timestamp: new Date().toISOString(),
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestedQuestions = [
    'Quante fatture ho ricevuto nel 2025?',
    'Qual è il totale degli F24 versati?',
    'Dammi il bilancio del 2025',
    'Quanti dipendenti ho?',
    'Panoramica generale del sistema',
  ];

  const handleSuggestion = suggestion => {
    setInput(suggestion);
  };

  if (!isOpen) {
    return (
      <>
        <style>{`
          @media (max-width: 768px) {
            [data-testid="chat-toggle"] { bottom: 84px !important; }
          }
        `}</style>
        <Button
          variant="info"
          onClick={() => setIsOpen(true)}
          data-testid="chat-toggle"
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            width: 60,
            height: 60,
            padding: 0,
            borderRadius: BORDER_RADIUS.full,
            fontSize: 28,
            boxShadow: '0 4px 20px rgba(29,78,216,0.4)',
            transition: 'transform 0.2s, box-shadow 0.2s',
            zIndex: 1000,
          }}
          onMouseEnter={e => {
            e.target.style.transform = 'scale(1.1)';
            e.target.style.boxShadow = '0 6px 24px rgba(29,78,216,0.5)';
          }}
          onMouseLeave={e => {
            e.target.style.transform = 'scale(1)';
            e.target.style.boxShadow = '0 4px 20px rgba(29,78,216,0.4)';
          }}
        >
          🤖
        </Button>
      </>
    );
  }

  return (
    <>
      <style>{`
        @media (max-width: 768px) {
          [data-testid="chat-widget"] {
            bottom: 84px !important;
            left: 8px !important;
            right: 8px !important;
            width: auto !important;
            height: 60vh !important;
          }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.7; transform: scale(1.08); }
        }
      `}</style>
      <div
      data-testid="chat-widget"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: 400,
        height: 550,
        background: COLORS.card,
        borderRadius: BORDER_RADIUS.xl,
        boxShadow: SHADOWS.xl,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        zIndex: 1000,
      }}
    >
      {/* Header */}
      <div
        style={{
          background: COLORS.info,
          padding: '16px 20px',
          color: 'white',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>🤖 Assistente AI</div>
          <div style={{ fontSize: 12, opacity: 0.9 }}>Interroga il gestionale</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={useAi}
              onChange={e => setUseAi(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            AI
          </label>
          <Button
            variant="ghost"
            onClick={() => setIsOpen(false)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              width: 32,
              height: 32,
              padding: 0,
              borderRadius: BORDER_RADIUS.full,
              fontSize: 18,
            }}
          >
            ✕
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: 16,
          background: COLORS.bgAlt,
        }}
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              marginBottom: 12,
              display: 'flex',
              justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div
              style={{
                maxWidth: '85%',
                padding: '12px 16px',
                borderRadius: msg.type === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                background:
                  msg.type === 'user'
                    ? COLORS.info
                    : msg.isError
                      ? COLORS.dangerLight
                      : COLORS.card,
                color: msg.type === 'user' ? 'white' : msg.isError ? COLORS.danger : COLORS.gray[800],
                boxShadow: msg.type === 'user' ? 'none' : SHADOWS.sm,
                fontSize: 14,
                lineHeight: 1.5,
                whiteSpace: 'pre-wrap',
              }}
            >
              {msg.text}
              {/* Metadati strutturati del motore AI: affidabilità, fonti, mancanze */}
              {(msg.affidabilita || (msg.fonti && msg.fonti.length > 0)) && (
                <div
                  style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: `1px solid ${COLORS.border}`,
                    fontSize: 11,
                    color: COLORS.textMuted,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                  }}
                >
                  {msg.affidabilita && (
                    <span>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '1px 8px',
                          borderRadius: 10,
                          fontWeight: 700,
                          background:
                            msg.affidabilita === 'certo'
                              ? COLORS.successLight
                              : msg.affidabilita === 'probabile'
                                ? COLORS.warningLight
                                : COLORS.dangerLight,
                          color:
                            msg.affidabilita === 'certo'
                              ? COLORS.success
                              : msg.affidabilita === 'probabile'
                                ? COLORS.warning
                                : COLORS.danger,
                        }}
                      >
                        {msg.affidabilita}
                      </span>
                    </span>
                  )}
                  {msg.fonti && msg.fonti.length > 0 && (
                    <span>📚 Fonti: {msg.fonti.join(' · ')}</span>
                  )}
                  {msg.datiMancanti && msg.datiMancanti.length > 0 && (
                    <span>❓ Dati mancanti: {msg.datiMancanti.join(' · ')}</span>
                  )}
                  {msg.anomalie && msg.anomalie.length > 0 && (
                    <span>⚠️ Anomalie: {msg.anomalie.join(' · ')}</span>
                  )}
                  {msg.azioniProposte && msg.azioniProposte.length > 0 && (
                    <span>💡 Azioni: {msg.azioniProposte.join(' · ')}</span>
                  )}
                </div>
              )}
              {!msg.affidabilita && msg.queryType && (
                <div
                  style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: `1px solid ${COLORS.border}`,
                    fontSize: 11,
                    color: COLORS.textMuted,
                  }}
                >
                  Query: {msg.queryType}
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
            <div
              style={{
                padding: '12px 16px',
                borderRadius: '16px 16px 16px 4px',
                background: COLORS.card,
                boxShadow: SHADOWS.sm,
                fontSize: 14,
              }}
            >
              <span className="loading-dots">Sto elaborando</span>
              <style>{`
                .loading-dots::after {
                  content: '';
                  animation: dots 1.5s steps(4, end) infinite;
                }
                @keyframes dots {
                  0%, 20% { content: ''; }
                  40% { content: '.'; }
                  60% { content: '..'; }
                  80%, 100% { content: '...'; }
                }
              `}</style>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length === 1 && (
        <div
          style={{
            padding: '8px 16px',
            borderTop: `1px solid ${COLORS.border}`,
            background: COLORS.bg,
          }}
        >
          <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 8 }}>💡 Suggerimenti:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {suggestedQuestions.slice(0, 3).map((q, i) => (
              <Button
                key={i}
                variant="secondary"
                onClick={() => handleSuggestion(q)}
                style={{
                  padding: '6px 10px',
                  fontSize: 11,
                  borderRadius: BORDER_RADIUS.full,
                  color: COLORS.gray[600],
                }}
              >
                {q}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div
        style={{
          padding: 16,
          borderTop: `1px solid ${COLORS.border}`,
          display: 'flex',
          gap: 8,
        }}
      >
        <Input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder={isListening ? 'Ti ascolto...' : 'Scrivi una domanda...'}
          disabled={isLoading}
          error={isListening}
          data-testid="chat-input"
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: 24,
            fontSize: 14,
          }}
        />
        {SpeechRecognitionCtor && (
          <Button
            variant={isListening ? 'danger' : 'secondary'}
            onClick={toggleListening}
            disabled={isLoading}
            data-testid="chat-mic"
            title={isListening ? 'Ferma registrazione' : 'Parla invece di scrivere'}
            style={{
              padding: '12px 16px',
              borderRadius: 24,
              background: isListening ? COLORS.danger : COLORS.bg,
              color: isListening ? 'white' : COLORS.gray[600],
              fontSize: 16,
              animation: isListening ? 'pulse 1.2s infinite' : 'none',
            }}
          >
            🎤
          </Button>
        )}
        <Button
          variant="info"
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          data-testid="chat-send"
          style={{
            padding: '12px 20px',
            borderRadius: 24,
            fontSize: 14,
          }}
        >
          {isLoading ? '⏳' : '➤'}
        </Button>
      </div>
      </div>
    </>
  );
}
