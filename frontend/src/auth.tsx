import { createContext, useContext, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const hostedMode = import.meta.env.VITE_APP_MODE === "hosted" || Boolean(url || anonKey);

// A memory adapter avoids putting the Supabase bearer/refresh tokens in
// localStorage. Users sign in again after a full browser refresh.
const memory = new Map<string, string>();
const memoryStorage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => { memory.set(key, value); },
  removeItem: (key: string) => { memory.delete(key); },
};

export const supabase: SupabaseClient | null = hostedMode && url && anonKey
  ? createClient(url!, anonKey!, { auth: { flowType: "implicit", storage: memoryStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

type AuthValue = { session: Session | null; loading: boolean; signOut: () => Promise<void> };
const AuthContext = createContext<AuthValue>({ session: null, loading: false, signOut: async () => undefined });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(hostedMode);
  useEffect(() => {
    if (!supabase) { setLoading(false); return; }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) { setSession(data.session); setLoading(false); }
    }).catch(() => { if (active) setLoading(false); });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);
  const value = useMemo<AuthValue>(() => ({
    session, loading,
    signOut: async () => { if (supabase) await supabase.auth.signOut(); },
  }), [session, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function SignInScreen() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setMessage("");
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { shouldCreateUser: false, emailRedirectTo: window.location.origin },
    });
    setMessage(error ? error.message : "Check your email for a secure sign-in link.");
    setBusy(false);
  };
  if (!supabase) return <main className="auth-screen"><section className="auth-card"><h1>Sign-in is not configured</h1><p>Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY for this hosted build.</p></section></main>;
  return <main className="auth-screen">
    <form className="auth-card" onSubmit={submit}>
      <p className="auth-eyebrow">PERSONAL FINANCE</p>
      <h1>Welcome back</h1>
      <p>Enter the email address attached to your invitation. We’ll send a one-time secure sign-in link.</p>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <button disabled={busy}>{busy ? "Sending link…" : "Email me a sign-in link"}</button>
      {message && <p role="status">{message}</p>}
      <small>Beta access is invite-only. Contact the app owner if you need an invitation.</small>
    </form>
  </main>;
}
