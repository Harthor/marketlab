import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Nav from './components/Nav';
import BacktestsPage from './pages/BacktestsPage';
import CorrelationsPage from './pages/CorrelationsPage';
import DatasetsPage from './pages/DatasetsPage';

const App = () => {
  return (
    <div className="app-shell">
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<DatasetsPage />} />
          <Route path="/correlations" element={<CorrelationsPage />} />
          <Route path="/backtests" element={<BacktestsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;
