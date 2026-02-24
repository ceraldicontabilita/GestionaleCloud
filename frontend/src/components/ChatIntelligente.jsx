/**
 * ChatIntelligente - Chat widget per interrogare il gestionale in linguaggio naturale
 * Usa AI per interpretare le domande e fornire risposte basate sui dati reali.
 */
import React, { useState, useRef, useEffect } from 'react';
import api from '../api';

export default function ChatIntelligente() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      type: 'assistant',
      text: '👋 Ciao! Sono il tuo assistente contabile AI. Puoi chiedermi informazioni su fatture, F24, stipendi, fornitori, bilanci e molto altro. Prova a farmi una domanda!',
      timestamp: new Date().toISOString()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [useAi, setUseAi] = useState(true);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');
    
    // Aggiungi messaggio utente
    setMessages(prev => [...prev, {
      type: 'user',
      text: question,
      timestamp: new Date().toISOString()
    }]);
    
    setIsLoading(true);
    
    try {
      const response = await api.post('/api/chat/ask', {
        question,
        use_ai: useAi
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
      
      setMessages(prev => [...prev, {
        type: 'assistant',
        text: responseText,
        timestamp: data.timestamp || new Date().toISOString(),
        queryType: data.query_type,
        dataCount: data.data_count
      }]);
      
    } catch (error) {
      console.error('Errore chat:', error);
      setMessages(prev => [...prev, {
        type: 'assistant',
        text: `❌ Errore: ${error.response?.data?.detail || error.message || 'Si è verificato un errore'}`,
        timestamp: new Date().toISOString(),
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
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
    'Panoramica generale del sistema'
  ];

  const handleSuggestion = (suggestion) => {
    setInput(suggestion);
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        data-testid="chat-toggle"
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          width: 60,
          height: 60,
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
          border: 'none',
          color: 'white',
          fontSize: 28,
          cursor: 'pointer',
          boxShadow: '0 4px 20px rgba(99, 102, 241, 0.4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'transform 0.2s, box-shadow 0.2s',
          zIndex: 1000
        }}
        onMouseEnter={(e) => {
          e.target.style.transform = 'scale(1.1)';
          e.target.style.boxShadow = '0 6px 24px rgba(99, 102, 241, 0.5)';
        }}
        onMouseLeave={(e) => {
          e.target.style.transform = 'scale(1)';
          e.target.style.boxShadow = '0 4px 20px rgba(99, 102, 241, 0.4)';
        }}
      >
        🤖
      </button>
    );
  }

  return (
    <div
      data-testid="chat-widget"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: 400,
        height: 550,
        background: 'white',
        borderRadius: 16,
        boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        zIndex: 1000
      }}
    >
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
        padding: '16px 20px',
        color: 'white',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>🤖 Assistente AI</div>
          <div style={{ fontSize: 12, opacity: 0.9 }}>Interroga il gestionale</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={useAi}
              onChange={(e) => setUseAi(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            AI
          </label>
          <button
            onClick={() => setIsOpen(false)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              color: 'white',
              width: 32,
              height: 32,
              borderRadius: '50%',
              cursor: 'pointer',
              fontSize: 18,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: 16,
        background: '#f8fafc'
      }}>
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              marginBottom: 12,
              display: 'flex',
              justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start'
            }}
          >
            <div style={{
              maxWidth: '85%',
              padding: '12px 16px',
              borderRadius: msg.type === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
              background: msg.type === 'user' 
                ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' 
                : msg.isError ? '#fee2e2' : 'white',
              color: msg.type === 'user' ? 'white' : msg.isError ? '#dc2626' : '#1e293b',
              boxShadow: msg.type === 'user' ? 'none' : '0 1px 3px rgba(0,0,0,0.1)',
              fontSize: 14,
              lineHeight: 1.5,
              whiteSpace: 'pre-wrap'
            }}>
              {msg.text}
              {msg.queryType && (
                <div style={{ 
                  marginTop: 8, 
                  paddingTop: 8, 
                  borderTop: '1px solid rgba(0,0,0,0.1)',
                  fontSize: 11,
                  color: '#64748b'
                }}>
                  Query: {msg.queryType}
                </div>
              )}
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
            <div style={{
              padding: '12px 16px',
              borderRadius: '16px 16px 16px 4px',
              background: 'white',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              fontSize: 14
            }}>
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
        <div style={{ 
          padding: '8px 16px',
          borderTop: '1px solid #dce8f4',
          background: '#f1f5f9'
        }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>💡 Suggerimenti:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {suggestedQuestions.slice(0, 3).map((q, i) => (
              <button
                key={i}
                onClick={() => handleSuggestion(q)}
                style={{
                  padding: '6px 10px',
                  fontSize: 11,
                  background: 'white',
                  border: '1px solid #dce8f4',
                  borderRadius: 16,
                  cursor: 'pointer',
                  color: '#475569'
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{
        padding: 16,
        borderTop: '1px solid #dce8f4',
        display: 'flex',
        gap: 8
      }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Scrivi una domanda..."
          disabled={isLoading}
          data-testid="chat-input"
          style={{
            flex: 1,
            padding: '12px 16px',
            border: '1px solid #dce8f4',
            borderRadius: 24,
            fontSize: 14,
            outline: 'none',
            transition: 'border-color 0.2s'
          }}
          onFocus={(e) => e.target.style.borderColor = '#6366f1'}
          onBlur={(e) => e.target.style.borderColor = '#dce8f4'}
        />
        <button
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          data-testid="chat-send"
          style={{
            padding: '12px 20px',
            background: isLoading || !input.trim() ? '#94a3b8' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            border: 'none',
            borderRadius: 24,
            color: 'white',
            fontWeight: 600,
            cursor: isLoading || !input.trim() ? 'not-allowed' : 'pointer',
            fontSize: 14
          }}
        >
          {isLoading ? '⏳' : '➤'}
        </button>
      </div>
    </div>
  );
}
