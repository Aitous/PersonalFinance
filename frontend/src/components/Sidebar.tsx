import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Overview", icon: "📊" },
  { to: "/transactions", label: "Transactions", icon: "📋" },
  { to: "/categories", label: "Categories", icon: "🏷️" },
  { to: "/insights", label: "Insights", icon: "⚡" },
  { to: "/subscriptions", label: "Recurring", icon: "🔄" },
  { to: "/savings", label: "Savings Tips", icon: "💡" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

export function Sidebar() {
  return (
    <nav style={{
      width: 200, minHeight: "100vh", background: "#1a1a2e",
      padding: "24px 0", display: "flex", flexDirection: "column",
    }}>
      <div style={{ color: "#fff", fontWeight: 700, fontSize: 18, padding: "0 20px 24px" }}>
        💰 FinanceApp
      </div>
      {links.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 20px", textDecoration: "none",
            color: isActive ? "#fff" : "#8888aa",
            background: isActive ? "rgba(124,106,247,0.2)" : "transparent",
            borderLeft: isActive ? "3px solid #7c6af7" : "3px solid transparent",
            fontSize: 14,
          })}
        >
          <span>{icon}</span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
