import { NavLink } from 'react-router-dom';

const Nav = () => {
  return (
    <header className="top-nav">
      <div className="brand">Market Research Dashboard</div>
      <nav>
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/datasets">Datasets</NavLink>
        <NavLink to="/correlations">Correlations</NavLink>
        <NavLink to="/backtests">Backtests</NavLink>
        <NavLink to="/degen">Degen Scanner</NavLink>
        <NavLink to="/paper">Paper Trading</NavLink>
      </nav>
      <a href="/api/runs" className="api-link" target="_blank" rel="noreferrer">
        API
      </a>
    </header>
  );
};

export default Nav;
