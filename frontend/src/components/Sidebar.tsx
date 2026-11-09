import { NavLink, useLocation } from "react-router-dom";

const links = [
  { to: "/", label: "Overview", icon: "M3 11 12 4l9 7v9h-6v-6H9v6H3z" },
  { to: "/transactions", label: "Transactions", icon: "M4 7h16M4 12h16M4 17h16" },
  { to: "/spending", label: "Spending", icon: "M4 18 9 12l4 3 7-9M16 6h4v4" },
  { to: "/settings", label: "Settings & data", icon: "M4 7h16M4 17h16M8 4v6m8 4v6" },
];

export function Sidebar() {
  const { pathname } = useLocation();
  return (
    <aside className="app-sidebar">
      <div className="app-brand"><span className="app-brand-mark" aria-hidden="true">f.</span><span><strong>Finance</strong><small>YOUR MONEY, CLEARER</small></span></div>
      <div className="app-nav-caption">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
      {links.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) => `app-nav-link${isActive || (to === "/transactions" && pathname === "/ask") || (to === "/spending" && ["/categories", "/insights", "/reports", "/savings", "/subscriptions"].includes(pathname)) ? " is-active" : ""}`}
        >
          <svg className="app-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icon} /></svg>
          <span>{label}</span>
        </NavLink>
      ))}
      </nav>
      <div className="app-sidebar-foot"><span className="app-sidebar-dot" /> Your personal workspace</div>
    </aside>
  );
}
