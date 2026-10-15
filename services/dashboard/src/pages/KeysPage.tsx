import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type ApiKey, type CreatedKey, type User } from "../api";
import { Button, Card, Field, Notice, formatTime, inputClass } from "../ui";

// Dev mein dashboard localhost:5173 pe hota hai, lekin gateway ka asli URL ingress wala hai
const MCP_URL = import.meta.env.DEV ? "http://app.localtest.me/mcp" : `${window.location.origin}/mcp`;

export default function KeysPage({ user }: { user: User }) {
  const isAdmin = user.role === "admin";
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setKeys(await api.listKeys(isAdmin && showAll));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load keys");
    }
  }, [isAdmin, showAll]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      setCreated(await api.createKey(name));
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the key");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key: ApiKey) {
    if (!window.confirm(`Revoke "${key.name}"? Clients using it will be rejected immediately.`)) return;
    setError(null);
    try {
      await api.revokeKey(key.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke the key");
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setError("Could not copy. Select the key and copy it manually.");
    }
  }

  const claudeCommand = `claude mcp add --transport http urumi ${MCP_URL} --header "Authorization: Bearer ${
    created?.key ?? "<your-key>"
  }"`;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">API keys</h2>
        <p className="text-sm text-slate-500">
          One gateway URL and your key give an MCP client every enabled server. You never see the upstream credentials.
        </p>
      </div>

      {error ? <Notice>{error}</Notice> : null}

      {created ? (
        <Card className="ring-emerald-300">
          <h3 className="text-base font-semibold text-slate-900">Your new key</h3>
          <p className="mt-1 text-sm text-slate-600">Copy it now. It is shown only once and cannot be recovered later.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="break-all rounded-md bg-slate-900 px-3 py-2 text-sm text-emerald-300">{created.key}</code>
            <Button onClick={() => void copy(created.key)}>{copied ? "Copied" : "Copy"}</Button>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </div>
        </Card>
      ) : null}

      <Card>
        <h3 className="mb-3 text-base font-semibold text-slate-900">Create a key</h3>
        <form onSubmit={create} className="flex flex-wrap items-end gap-3">
          <div className="w-full max-w-xs">
            <Field label="Key name" hint="For example: my laptop, Cursor">
              <input
                className={inputClass}
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
              />
            </Field>
          </div>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Creating…" : "Create key"}
          </Button>
        </form>
      </Card>

      <Card>
        <h3 className="text-base font-semibold text-slate-900">Connect an MCP client</h3>
        <p className="mt-1 text-sm text-slate-600">
          Gateway URL: <code className="rounded bg-slate-100 px-1.5 py-0.5">{MCP_URL}</code> with the header{" "}
          <code className="rounded bg-slate-100 px-1.5 py-0.5">Authorization: Bearer &lt;key&gt;</code>. For Claude Code:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{claudeCommand}</pre>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">{showAll ? "All keys" : "Your keys"}</h3>
          {isAdmin ? (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              Show every user's keys
            </label>
          ) : null}
        </div>
        {keys && keys.length === 0 ? <p className="text-sm text-slate-500">No keys yet.</p> : null}
        {keys && keys.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  {showAll ? <th className="py-2 pr-4">Owner</th> : null}
                  <th className="py-2 pr-4">Key</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Last used</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td className="py-2 pr-4 font-medium text-slate-800">{k.name}</td>
                    {showAll ? <td className="py-2 pr-4 text-slate-600">{k.user_email}</td> : null}
                    <td className="py-2 pr-4">
                      <code className="text-xs text-slate-600">{k.prefix}…</code>
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          k.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {k.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-slate-500">{formatTime(k.last_used_at)}</td>
                    <td className="py-2 text-right">
                      {k.status === "active" ? (
                        <Button variant="danger" onClick={() => void revoke(k)}>
                          Revoke
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}