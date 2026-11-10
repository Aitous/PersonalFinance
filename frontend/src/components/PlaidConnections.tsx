import { useCallback, useEffect, useState } from "react";
import {
  createPlaidLinkToken, exchangePlaidPublicToken, getPlaidConfig,
  getPlaidItems, removePlaidItem, savePlaidConfig, syncPlaidItem,
} from "../api/client";
import type { PlaidEnvironment, PlaidItem } from "../api/client";
import { hostedMode } from "../auth";

declare global {
  interface Window {
    Plaid?: { create: (config: {
      token: string;
      onSuccess: (publicToken: string) => void;
      onExit: (error: { error_code?: string } | null) => void;
    }) => { open: () => void } };
  }
}

function readableError(error: unknown): string {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof response === "string") return response;
  if (response && typeof response === "object" && "code" in response) return `Plaid error: ${String((response as { code: unknown }).code)}.`;
  return "The Plaid request failed. Check the connection and try again.";
}

export function PlaidConnections() {
  const [environment, setEnvironment] = useState<PlaidEnvironment>(hostedMode ? "production" : "sandbox");
  const [configured, setConfigured] = useState(false);
  const [editingCredentials, setEditingCredentials] = useState(false);
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [items, setItems] = useState<PlaidItem[]>([]);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [config, connections] = await Promise.all([getPlaidConfig(environment), getPlaidItems(environment)]);
    setConfigured(config.configured);
    setItems(connections);
  }, [environment]);

  useEffect(() => { refresh().catch((e) => setError(readableError(e))); }, [refresh]);

  const saveCredentials = async () => {
    setBusy("credentials"); setError(""); setMessage("");
    try {
      const config = await savePlaidConfig(environment, clientId.trim(), secret.trim());
      setConfigured(config.configured); setClientId(""); setSecret("");
      setMessage(`${environment === "sandbox" ? "Sandbox" : "Production"} credentials saved to macOS Keychain.`);
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(""); }
  };

  const connect = async () => {
    setBusy("connect"); setError(""); setMessage("");
    try {
      const { link_token } = await createPlaidLinkToken(environment);
      if (!window.Plaid) throw new Error("Plaid Link has not loaded yet. Refresh the page and try again.");
      window.Plaid.create({
        token: link_token,
        onSuccess: async (publicToken) => {
          setBusy("exchange");
          try {
            await exchangePlaidPublicToken(environment, publicToken);
            await refresh(); setMessage(`${environment === "sandbox" ? "Sandbox test" : "Production"} connection added.`);
          } catch (e) { setError(readableError(e)); }
          finally { setBusy(""); }
        },
        onExit: (exitError) => {
          if (exitError?.error_code) setError(`Plaid Link closed (${exitError.error_code}).`);
          setBusy("");
        },
      }).open();
    } catch (e) { setError(readableError(e)); setBusy(""); }
  };

  const sync = async (item: PlaidItem) => {
    setBusy(item.item_id); setError(""); setMessage("");
    try {
      const result = await syncPlaidItem(environment, item.item_id);
      await refresh();
      const imported = result.transaction_counts?.imported ?? 0;
      setMessage(environment === "production"
        ? `${item.institution_name} synced. ${imported} new transaction${imported === 1 ? "" : "s"} added to spending.${result.enrichment_job_id ? " Enrichment is queued; follow its progress in the status banner above." : ""}`
        : `${item.institution_name} Sandbox sync completed.`);
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(""); }
  };

  const remove = async (item: PlaidItem) => {
    if (!isSandbox && !window.confirm(`Disconnect ${item.institution_name}? Imported transactions will stay in your spending history.`)) return;
    setBusy(item.item_id); setError(""); setMessage("");
    try {
      await removePlaidItem(environment, item.item_id); await refresh(); setMessage(`${item.institution_name} ${environment === "sandbox" ? "Sandbox" : "Production"} connection disconnected.`);
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(""); }
  };

  const isSandbox = environment === "sandbox";
  return <section id="plaid-sandbox" className="plaid-connections">
    <div className="plaid-connections-heading">
      <div><span className="plaid-kicker">BANK CONNECTIONS · {isSandbox ? "SANDBOX" : "PRODUCTION"}</span><h2>{isSandbox ? "Plaid test connections" : "Connect a real account"}</h2></div>
      <span className={`plaid-environment-tag ${isSandbox ? "" : "plaid-production-tag"}`}>{isSandbox ? "Sandbox only" : "Production"}</span>
    </div>
    {!hostedMode && <div className="plaid-environment-switch" role="group" aria-label="Plaid environment">
      <button type="button" disabled={!!busy} aria-pressed={isSandbox} onClick={() => { setEnvironment("sandbox"); setError(""); setMessage(""); setClientId(""); setSecret(""); setEditingCredentials(false); }}>Sandbox</button>
      <button type="button" disabled={!!busy} aria-pressed={!isSandbox} onClick={() => { setEnvironment("production"); setError(""); setMessage(""); setClientId(""); setSecret(""); setEditingCredentials(false); }}>Production</button>
    </div>}
    <p className="plaid-description">{isSandbox
      ? "Try the connection flow with synthetic test accounts. Sandbox transactions never enter your spending history."
      : "Connect a real financial account. Posted transactions will be imported into this app and included in spending reports. Use Sync transactions to check for updates; Plaid refreshes accounts periodically, not in real time. Initial history can take a little while to arrive."}</p>

    {!hostedMode && (!configured || editingCredentials) ? <div className="plaid-credential-form">
      <div><label htmlFor="plaid-client-id">{isSandbox ? "Sandbox" : "Production"} Client ID</label><input id="plaid-client-id" autoComplete="off" value={clientId} onChange={(e) => setClientId(e.target.value)} /></div>
      <div><label htmlFor="plaid-secret">{isSandbox ? "Sandbox" : "Production"} Secret</label><input id="plaid-secret" type="password" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} /></div>
      <div className="plaid-credential-buttons"><button type="button" disabled={!clientId.trim() || !secret.trim() || !!busy} onClick={saveCredentials}>{busy === "credentials" ? "Saving…" : configured ? "Update credentials" : `Save ${isSandbox ? "Sandbox" : "Production"} credentials`}</button>
        {configured && <button type="button" className="plaid-cancel-button" disabled={!!busy} onClick={() => { setEditingCredentials(false); setClientId(""); setSecret(""); }}>Cancel</button>}</div>
      <small>Credentials are saved on this Mac in Keychain. The secret is never displayed again.</small>
    </div> : <div className="plaid-connected-actions">
      <div className="plaid-configured-note"><strong>{configured ? hostedMode ? "Secure connection ready" : "Credentials configured" : "Bank linking unavailable"}</strong><span>{hostedMode ? configured ? "Plaid credentials are managed securely by the service." : "The service owner has not configured Plaid for this environment." : "Stored securely in macOS Keychain."}</span></div>
      <div className="plaid-configured-buttons">{!hostedMode && configured && <button type="button" className="plaid-secondary-button" disabled={!!busy} onClick={() => setEditingCredentials(true)}>Update credentials</button>}<button type="button" className="plaid-primary-button" disabled={!configured || !!busy} onClick={connect}>{busy === "connect" ? "Opening Link…" : busy === "exchange" ? "Finishing connection…" : isSandbox ? "Connect a test account" : "Connect a bank account"}</button></div>
    </div>}

    {message && <p className="plaid-message" role="status">{message}</p>}
    {error && <p className="plaid-error" role="alert">{error}</p>}
    {configured && items.length > 0 && <div className="plaid-item-list">
      {items.map((item) => <article key={item.item_id} className="plaid-item-card">
        <div className="plaid-item-top"><div><h3>{item.institution_name}</h3><span>{item.accounts.length} {item.accounts.length === 1 ? "account" : "accounts"} · {isSandbox ? "Sandbox" : "Production"}</span></div>
          <div className="plaid-item-actions"><button type="button" disabled={!!busy} onClick={() => sync(item)}>{busy === item.item_id ? "Working…" : isSandbox ? "Sync test activity" : "Sync transactions"}</button><button type="button" className="plaid-remove-button" disabled={!!busy} onClick={() => remove(item)}>{isSandbox ? "Remove" : "Disconnect"}</button></div></div>
        <ul>{item.accounts.map((account) => <li key={account.account_id}><span>{account.name}{account.mask ? ` ···· ${account.mask}` : ""}</span><small>{[account.type, account.subtype].filter(Boolean).join(" · ")}</small></li>)}</ul>
        <div className="plaid-sync-summary">{item.last_sync_at ? <>Last synced {new Date(item.last_sync_at).toLocaleString()} · {isSandbox ? `${item.sync_counts.added} added · ${item.sync_counts.modified} modified · ${item.sync_counts.removed} removed` : `${item.transaction_counts.imported} imported · ${item.transaction_counts.duplicates} matched to existing transactions`}</> : "Not synced yet"}</div>
      </article>)}
    </div>}
  </section>;
}
