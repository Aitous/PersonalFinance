import { Categories } from "./Categories";
import { Insights } from "./Insights";

const links = [
  { href: "#spending-categories", label: "Categories" },
  { href: "#spending-merchants", label: "Merchants" },
  { href: "#spending-trends", label: "Trends & alerts" },
];

export function SpendingAnalysis() {
  return <div className="spending-analysis-page">
    <header className="spending-analysis-header">
      <div>
        <span className="section-kicker">SPENDING ANALYSIS</span>
        <h1>Where your money goes</h1>
        <p>Explore category totals, merchant activity, and spending patterns in one place.</p>
      </div>
      <nav aria-label="Jump to spending analysis section" className="spending-analysis-jumps">
        {links.map((link) => <a key={link.href} href={link.href}>{link.label}<span aria-hidden="true"> ↓</span></a>)}
      </nav>
    </header>
    <Categories />
    <Insights />
  </div>;
}
