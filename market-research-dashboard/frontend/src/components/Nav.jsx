import { NavLink } from 'react-router-dom';

const Nav = () => {
  return (
    <header className="top-nav">
      <div className="brand">Market Research Dashboard</div>
      <nav>
        <NavLink to="/">Datasets</NavLink>
        <NavLink to="/correlations">Correlations</NavLink>
        <NavLink to="/backtests">Backtests</NavLink>
      </nav>
      <a href="/api/runs" className="api-link" target="_blank" rel="noreferrer">
        API
      </a>
    </header>
  );
};

export default Nav;
