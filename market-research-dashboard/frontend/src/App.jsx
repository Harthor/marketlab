import React, { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import AuthGate from './components/AuthGate';
import Nav from './components/Nav';
import BacktestsPage from './pages/BacktestsPage';
import CorrelationsPage from './pages/CorrelationsPage';
import DatasetsPage from './pages/DatasetsPage';
import DegenScannerPage from './pages/DegenScannerPage';
import PaperTradingPage from './pages/PaperTradingPage';

const DashboardApp = lazy(() => import('./features/dashboard/DashboardApp'));

const App = () => {
  const location = useLocation();
  const isDashboard = location.pathname === '/';

  return (
    <AuthGate>
      <div className={isDashboard ? '' : 'app-shell'}>
        {!isDashboard && <Nav />}
        {isDashboard ? (
          <Suspense fallback={<div style={{ minHeight: '100vh', background: '#0B1120' }} />}>
            <Routes>
              <Route path="/" element={<DashboardApp />} />
            </Routes>
          </Suspense>
        ) : (
          <main>
            <Routes>
              <Route path="/datasets" element={<DatasetsPage />} />
              <Route path="/correlations" element={<CorrelationsPage />} />
              <Route path="/backtests" element={<BacktestsPage />} />
              <Route path="/degen" element={<DegenScannerPage />} />
              <Route path="/paper" element={<PaperTradingPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        )}
      </div>
    </AuthGate>
  );
};

export default App;
