import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { SpendingRangePicker } from "./SpendingRangePicker";

const sections = {
  transactions: [{ to: "/transactions", label: "Browse transactions" }, { to: "/ask", label: "Ask your transactions" }],
  spending: [{ to: "/spending", label: "Analysis" }, { to: "/reports", label: "Monthly report" }, { to: "/savings", label: "Opportunities" }, { to: "/subscriptions", label: "Bills & subscriptions" }],
};

export function SectionLayout({ section }: { section: keyof typeof sections }) {
  const [days, setDays] = useState(90);
  const [customRange, setCustomRange] = useState<{ from: string; to: string } | null>(null);
  const { pathname } = useLocation();
  return <div className="workspace-section">
    <nav className="workspace-section-nav" aria-label={`${section === "spending" ? "Spending" : "Transactions"} views`}>
      {sections[section].map((item) => <NavLink key={item.to} to={item.to} className={({ isActive }) => `workspace-section-link${isActive ? " is-active" : ""}`}>{item.label}</NavLink>)}
    </nav>
    {section === "spending" && ["/spending", "/savings"].includes(pathname) && <SpendingRangePicker days={days} setDays={setDays} customRange={customRange} setCustomRange={setCustomRange} />}
    {section === "spending" && <p className="workspace-section-note">{pathname === "/reports" ? "Monthly reports use the calendar month selected below." : pathname === "/subscriptions" ? "Review and manage fixed and variable automatic charges." : pathname === "/savings" ? "The selected date range is used to generate savings opportunities." : "The selected date range applies to category and merchant activity. Alerts, year-over-year comparisons, and averages use the periods shown in their sections."}</p>}
    <Outlet context={{ days, setDays, customRange, setCustomRange }} />
  </div>;
}
