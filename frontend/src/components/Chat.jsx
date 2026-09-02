import React, { useState, useRef, useEffect } from 'react';
import { fetchChat } from '../api/clearflow.js';

const SUGGESTIONS = [
  'What rails are available for a EUR payment over €1M?',
  'Explain the FATF grey list and its impact on EDD.',
  'What does a CRITICAL fraud score mean for a payment?',
  'How does the saga compensation flow work on settlement failure?',
];

function Message({ msg }) {
  return (
    <div className={`message ${msg.role}`}>
      <div className="message-role">{msg.role === 'user' ? 'You' : 'ClearFlow AI'}</div>
      <div className="message-content">{msg.content}</div>
      {msg.provider && <div className="message-provider">via {msg.provider}</div>}
    </div>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [paymentId, setPaymentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function send(question) {
    const q = question || input.trim();
    if (!q) return;
    setInput('');
    setError(null);

    const userMsg = { role: 'user', content: q };
    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetchChat({ question: q, paymentId: paymentId || null, history });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res?.answer || 'No response', provider: res?.provider },
      ]);
    } catch (e) {
      setError(e.message === 'UNAUTHORIZED' ? 'Invalid token — sign out and re-enter your JWT.' : e.message);
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="page chat-page">
      <div className="page-header">
        <h1>AI Chat</h1>
        <span className="badge-ai">MCP LLM</span>
      </div>

      <div className="chat-context">
        <label className="context-label">Payment context (optional)</label>
        <input
          className="search-input context-input"
          type="text"
          placeholder="Payment ID to attach as context"
          value={paymentId}
          onChange={(e) => setPaymentId(e.target.value)}
        />
      </div>

      {messages.length === 0 && (
        <div className="suggestions">
          <p className="suggestions-title">Suggested questions</p>
          <div className="suggestions-grid">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="suggestion-chip" onClick={() => send(s)} disabled={loading}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.map((m, i) => (
          <Message key={i} msg={m} />
        ))}
        {loading && (
          <div className="message assistant">
            <div className="message-role">ClearFlow AI</div>
            <div className="message-content typing">
              <span /><span /><span />
            </div>
          </div>
        )}
        {error && <div className="alert-error">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-textarea"
          rows={2}
          placeholder="Ask about payments, fraud, compliance, rails... (Enter to send)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={loading}
        />
        <button className="btn-primary send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
