import { useState, useEffect } from 'react';

const STORAGE_KEY = 'ml_auth_ok';

export default function AuthGate({ children }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved === '1') setAuthenticated(true);
    setLoading(false);
  }, []);

  const handleLogin = () => {
    const expected = import.meta.env.VITE_SITE_PASSWORD || 'marketlab2026';
    if (password === expected) {
      sessionStorage.setItem(STORAGE_KEY, '1');
      setAuthenticated(true);
      setError('');
    } else {
      setError('Password incorrecto');
    }
  };

  if (loading) return null;

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0e17]">
        <div className="bg-[#111827] border border-[#1e293b] rounded-2xl p-12 w-96 text-center">
          <h1 className="text-3xl font-bold mb-1 bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500 bg-clip-text text-transparent">
            MarketLab
          </h1>
          <p className="text-gray-500 text-sm mb-8">
            Crypto Market Intelligence
          </p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
            placeholder="Password"
            autoFocus
            className="w-full px-4 py-3 bg-[#0a0e17] border border-[#1e293b] rounded-lg text-gray-200 text-sm font-mono outline-none focus:border-blue-500 mb-4"
          />
          {error && (
            <p className="text-red-400 text-sm mb-3">{error}</p>
          )}
          <button
            onClick={handleLogin}
            className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-white text-sm font-semibold transition-colors"
          >
            Entrar
          </button>
        </div>
      </div>
    );
  }

  return children;
}
