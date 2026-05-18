import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./pages/Overview";
import { Transactions } from "./pages/Transactions";
import { Categories } from "./pages/Categories";
import { Subscriptions } from "./pages/Subscriptions";
import { SavingsTips } from "./pages/SavingsTips";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif" }}>
        <Sidebar />
        <main style={{ flex: 1, padding: 32, background: "#f8f8ff", overflowY: "auto" }}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/subscriptions" element={<Subscriptions />} />
            <Route path="/savings" element={<SavingsTips />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
