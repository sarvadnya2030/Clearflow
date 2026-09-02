import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './app.css';

class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, fontFamily: 'monospace', color: '#f85149', background: '#0d1117', minHeight: '100vh' }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>⚠ ClearFlow UI Error</div>
          <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 16 }}>{this.state.error.message}</div>
          <button onClick={() => this.setState({ error: null })} style={{ background: '#21262d', color: '#e6edf3', border: '1px solid #30363d', padding: '6px 16px', borderRadius: 6, cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
