import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./pages/Overview";
import { Transactions } from "./pages/Transactions";
import { SavingsTips } from "./pages/SavingsTips";
import { Settings } from "./pages/Settings";
import { Subscriptions } from "./pages/Subscriptions";
import Reports from "./pages/Reports";
import { AskTransactions } from "./pages/AskTransactions";
import { RecategorizationProvider } from "./components/RecategorizationStatus";
import { EnrichmentProvider } from "./components/EnrichmentStatus";
import { SectionLayout } from "./components/SectionLayout";
import { SpendingAnalysis } from "./pages/SpendingAnalysis";
import { AuthProvider, hostedMode, SignInScreen, useAuth } from "./auth";
import { useEffect, useRef, useState } from "react";
import { acceptAIConsent, deleteAccount, getAccountDeletionStatus, getAIConsent } from "./api/client";

export default function App() {
  return (
    <AuthProvider>
      <Application />
    </AuthProvider>
  );
}

function Application() {
  const { session, loading, signOut } = useAuth();
  const ownerId = session?.user.id;
  const [consent, setConsent] = useState<boolean | null>(hostedMode ? null : true);
  const [showConsentPrompt, setShowConsentPrompt] = useState(hostedMode);
  const [consentError, setConsentError] = useState("");
  const [consentSaving, setConsentSaving] = useState(false);
  const consentSubmissionStarted = useRef(false);
  const [deletionPending, setDeletionPending] = useState(false);
  const [deletionError, setDeletionError] = useState("");
  useEffect(() => {
    if (!hostedMode || !ownerId) return;
    let active = true;
    consentSubmissionStarted.current = false;
    setConsent(null);
    setShowConsentPrompt(true);
    setDeletionPending(false);
    setDeletionError("");
    getAIConsent().then((result) => {
      if (active && !consentSubmissionStarted.current) {
        setConsent(result.accepted);
        setShowConsentPrompt(!result.accepted);
      }
    }).catch((error: unknown) => {
      if (!active || consentSubmissionStarted.current) return;
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 410) {
        void getAccountDeletionStatus().then((result) => setDeletionPending(result.status === "deleting"))
          .catch(() => setConsentError("Could not check your account status. Try again."));
      } else setConsentError("Could not check your AI privacy preference. Try again.");
    });
    return () => { active = false; };
  }, [ownerId]);
  if (hostedMode && loading) return <main className="auth-screen"><p>Checking your session…</p></main>;
  if (hostedMode && !session) return <SignInScreen />;
  if (hostedMode && deletionPending) return <main className="auth-screen"><section className="auth-card">
    <p className="auth-eyebrow">ACCOUNT CLOSURE</p><h1>Deletion is in progress</h1>
    <p>Your finance data has been removed. The sign-in provider could not finish closing your account, so this session can only retry that final step.</p>
    {deletionError && <p role="alert">{deletionError}</p>}
    <button onClick={() => { setDeletionError(""); void deleteAccount().then(() => void signOut()).catch(() => setDeletionError("Account closure still could not finish. Please retry.")); }}>Retry account closure</button>
    <button type="button" onClick={() => void signOut()} style={{ background: "#eef1ef", color: "#25352f" }}>Sign out</button>
  </section></main>;
  if (hostedMode && showConsentPrompt) return <main className="auth-screen"><section className="auth-card">
    <p className="auth-eyebrow">PRIVACY CHOICE</p><h1>Before using AI</h1>
    <p>When you use an AI feature, the app sends the transaction details needed for that request to the model provider configured by the service. The app records the feature, model, time, and request count to enforce your allowance; it does not save prompts or transaction text in its AI usage log. Provider handling is subject to that provider’s terms.</p>
    {consentError && <p role="alert">{consentError}</p>}
    {consentError && <button type="button" onClick={() => { setConsentError(""); void getAIConsent().then((result) => { setConsent(result.accepted); setShowConsentPrompt(!result.accepted); }).catch(() => setConsentError("Could not check your AI privacy preference. Try again.")); }}>Retry</button>}
    <button disabled={consentSaving} onClick={() => {
      consentSubmissionStarted.current = true;
      setConsentSaving(true);
      setConsentError("");
      void acceptAIConsent().then(() => {
        setConsent(true);
        setShowConsentPrompt(false);
      }).catch(() => {
        setConsentError("Could not save your choice. Please try again.");
      }).finally(() => setConsentSaving(false));
    }}>{consentSaving ? "Saving your choice…" : "I understand and agree"}</button>
    <button type="button" disabled={consent !== false} onClick={() => setShowConsentPrompt(false)} style={{ background: "#eef1ef", color: "#25352f" }}>Continue without AI</button>
    <button type="button" onClick={() => void signOut()} style={{ background: "#eef1ef", color: "#25352f" }}>Sign out</button>
  </section></main>;
  return <BrowserRouter>
      <div className="app-shell">
        <Sidebar />
        <main className="app-main">
          {hostedMode && consent === false && <div className="ai-consent-banner">AI features are off until you agree to the data-use notice. <button onClick={() => { setConsentError(""); setShowConsentPrompt(true); }}>Review AI privacy choice</button></div>}
          {hostedMode && <button className="sign-out-button" onClick={() => void signOut()}>Sign out</button>}
          <RecategorizationProvider><EnrichmentProvider>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route element={<SectionLayout section="transactions" />}>
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/ask" element={<AskTransactions />} />
            </Route>
            <Route element={<SectionLayout section="spending" />}>
              <Route path="/spending" element={<SpendingAnalysis />} />
              <Route path="/categories" element={<Navigate to="/spending" replace />} />
              <Route path="/insights" element={<Navigate to="/spending" replace />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/savings" element={<SavingsTips />} />
              <Route path="/subscriptions" element={<Subscriptions />} />
            </Route>
            <Route path="/settings" element={<Settings />} />
          </Routes>
          </EnrichmentProvider></RecategorizationProvider>
        </main>
      </div>
    </BrowserRouter>;
}
