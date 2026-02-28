import { NavLink } from 'react-router-dom';

const Nav = () => {
  return (
    <header className="top-nav">
      <div className="brand">MarketLab</div>
      <nav>
        <NavLink to="/">Home</NavLink>
        <NavLink to="/signals">Signals</NavLink>
        <NavLink to="/degen">Degen Scanner</NavLink>
        <NavLink to="/paper">Paper Trading</NavLink>
        <NavLink to="/correlations">Correlations</NavLink>
        <NavLink to="/datasets">Datasets</NavLink>
        <NavLink to="/backtests">Backtests</NavLink>
      </nav>
    </header>
  );
};

export default Nav;
