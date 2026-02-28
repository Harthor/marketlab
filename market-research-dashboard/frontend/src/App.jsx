import React, { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AuthGate from './components/AuthGate';
import Nav from './components/Nav';
import HomePage from './pages/HomePage';
import BacktestsPage from './pages/BacktestsPage';
import CorrelationsPage from './pages/CorrelationsPage';
import DatasetsPage from './pages/DatasetsPage';
import DegenScannerPage from './pages/DegenScannerPage';
import PaperTradingPage from './pages/PaperTradingPage';

const DashboardApp = lazy(() => import('./features/dashboard/DashboardApp'));

const App = () => {
  return (
    <AuthGate>
      <div className="app-shell">
        <Nav />
        <main>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route
              path="/signals"
              element={
                <Suspense fallback={<div style={{ minHeight: '100vh', background: '#0B1120' }} />}>
                  <DashboardApp />
                </Suspense>
              }
            />
            <Route path="/datasets" element={<DatasetsPage />} />
            <Route path="/correlations" element={<CorrelationsPage />} />
            <Route path="/backtests" element={<BacktestsPage />} />
            <Route path="/degen" element={<DegenScannerPage />} />
            <Route path="/paper" element={<PaperTradingPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </AuthGate>
  );
};

export default App;
