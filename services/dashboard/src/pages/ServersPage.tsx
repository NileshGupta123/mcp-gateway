import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type AuthType, type Server } from "../api";
import { Button, Card, Field, Notice, StatusBadge, formatTime, inputClass } from "../ui";

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function ServerForm({
  server,
  onSaved,
  onCancel,
}: {
  server?: Server;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const editing = Boolean(server);
  const [name, setName] = useState(server?.name ?? "");
  const [url, setUrl] = useState(server?.url ?? "");
  const [authType, setAuthType] = useState<AuthType>(server?.auth_type ?? "none");
  const [headerName, setHeaderName] = useState(server?.header_name ?? "");
  const [credential, setCredential] = useState("");
  const [clearCredential, setClearCredential] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (server) {
        await api.updateServer(server.id, {
          url,
          auth_type: authType,
          header_name: authType === "header" ? headerName : undefined,
          credential: credential || undefined,
          clear_credential: clearCredential || undefined,
        });
      } else {
        await api.createServer({
          name,
          url,
          auth_type: authType,
          header_name: authType === "header" ? headerName : undefined,
          credential: authType === "none" ? undefined : credential || undefined,
        });
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the server"));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" hint="Lowercase letters, digits and hyphens. Becomes the tool prefix, e.g. notes__add_note.">
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase())}
            disabled={editing}
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            maxLength={32}
            required
          />
        </Field>
        <Field label="URL" hint="Streamable HTTP endpoint, e.g. http://my-server:8000/mcp">
          <input className={inputClass} value={url} onChange={(e) => setUrl(e.target.value)} required />
        </Field>
        <Field label="Authentication">
          <select className={inputClass} value={authType} onChange={(e) => setAuthType(e.target.value as AuthType)}>
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="header">Custom header</option>
          </select>
        </Field>
        {authType === "header" ? (
          <Field label="Header name">
            <input
              className={inputClass}
              value={headerName}
              onChange={(e) => setHeaderName(e.target.value)}
              placeholder="X-Api-Key"
              required
            />
          </Field>
        ) : null}
        {authType !== "none" ? (
          <Field
            label="Credential"
            hint={
              editing && server?.has_credential
                ? "A credential is already stored (encrypted). Leave empty to keep it."
                : "Stored encrypted on the server. It is never shown again."
            }
          >
            <input
              className={inputClass}
              type="password"
              autoComplete="off"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              required={!editing || !server?.has_credential}
            />
          </Field>
        ) : null}
      </div>
      {editing && server?.has_credential && authType !== "none" ? (
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={clearCredential} onChange={(e) => setClearCredential(e.target.checked)} />
          Remove the stored credential
        </label>
      ) : null}
      {error ? <Notice>{error}</Notice> : null}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Saving…" : editing ? "Save changes" : "Add server"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function ServerCard({
  server,
  editing,
  onEdit,
  onChanged,
}: {
  server: Server;
  editing: boolean;
  onEdit: (id: number | null) => void;
  onChanged: () => void;
}) {
  const [showTools, setShowTools] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await api.updateServer(server.id, { enabled: !server.enabled });
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not update the server"));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove server "${server.name}"? Its tools disappear from the gateway.`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteServer(server.id);
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not remove the server"));
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-base font-semibold text-slate-900">{server.name}</h3>
            <StatusBadge status={server.status} />
            {server.has_credential ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {server.auth_type === "bearer" ? "bearer token" : `header ${server.header_name}`} · encrypted
              </span>
            ) : null}
          </div>
          <p className="mt-1 truncate text-sm text-slate-500">{server.url}</p>
          {server.status === "unreachable" && server.error ? (
            <p className="mt-2 text-sm text-red-600">Reason: {server.error}</p>
          ) : null}
          <p className="mt-2 text-xs text-slate-400">
            {server.status === "connected"
              ? `${server.tools.length} tools · ${server.latency_ms ?? "?"} ms · checked ${formatTime(server.checked_at)}`
              : server.status === "unreachable"
                ? `checked ${formatTime(server.checked_at)}`
                : "Disabled: its tools are hidden from every client"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {server.tools.length > 0 ? (
            <Button onClick={() => setShowTools((v) => !v)}>{showTools ? "Hide tools" : "Show tools"}</Button>
          ) : null}
          <Button onClick={() => onEdit(editing ? null : server.id)}>{editing ? "Close" : "Edit"}</Button>
          <Button onClick={toggle} disabled={busy}>
            {server.enabled ? "Disable" : "Enable"}
          </Button>
          <Button variant="danger" onClick={remove} disabled={busy}>
            Remove
          </Button>
        </div>
      </div>
      {error ? (
        <div className="mt-3">
          <Notice>{error}</Notice>
        </div>
      ) : null}
      {showTools ? (
        <ul className="mt-4 divide-y divide-slate-100 rounded-md bg-slate-50 ring-1 ring-slate-200">
          {server.tools.map((t) => (
            <li key={t.name} className="px-3 py-2">
              <code className="text-sm font-medium text-indigo-700">{t.gateway_name}</code>
              <p className="mt-0.5 text-xs text-slate-500">{t.description || "No description"}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {editing ? (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <ServerForm
            server={server}
            onSaved={() => {
              onEdit(null);
              onChanged();
            }}
            onCancel={() => onEdit(null)}
          />
        </div>
      ) : null}
    </Card>
  );
}

export default function ServersPage() {
  const [servers, setServers] = useState<Server[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      setServers(await api.listServers(force));
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not load servers"));
    }
  }, []);

  useEffect(() => {
    void load();
    // Status auto-refresh: server ka pod kill ho to dashboard khud Unreachable dikha de
    const timer = setInterval(() => void load(), 15000);
    return () => clearInterval(timer);
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  }

  const connected = servers?.filter((s) => s.status === "connected") ?? [];
  const toolCount = connected.reduce((n, s) => n + s.tools.length, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">MCP servers</h2>
          <p className="text-sm text-slate-500">
            {servers
              ? `${connected.length} of ${servers.length} connected · ${toolCount} tools exposed through the gateway`
              : "Loading…"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={refresh} disabled={refreshing}>
            {refreshing ? "Checking…" : "Refresh status"}
          </Button>
          <Button variant="primary" onClick={() => setAdding((v) => !v)}>
            {adding ? "Close" : "Add server"}
          </Button>
        </div>
      </div>

      {error ? <Notice>{error}</Notice> : null}

      {adding ? (
        <Card>
          <h3 className="mb-4 text-base font-semibold text-slate-900">Add an MCP server</h3>
          <ServerForm
            onSaved={() => {
              setAdding(false);
              void load(true);
            }}
            onCancel={() => setAdding(false)}
          />
        </Card>
      ) : null}

      {servers?.map((s) => (
        <ServerCard
          key={s.id}
          server={s}
          editing={editingId === s.id}
          onEdit={setEditingId}
          onChanged={() => void load(true)}
        />
      ))}
      {servers && servers.length === 0 ? <Notice kind="info">No servers registered yet.</Notice> : null}
    </div>
  );
}