import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type PermissionServer } from "../api";
import { Card, Notice, StatusBadge } from "../ui";

function Switch({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
        on ? "bg-indigo-600" : "bg-slate-300"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 rounded-full bg-white shadow transition ${
          on ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function PermissionsPage() {
  const [servers, setServers] = useState<PermissionServer[] | null>(null);
  const [denied, setDenied] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getPermissions();
      setServers(data.servers);
      setDenied(data.denied);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load permissions");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(server: string, tool: string, allowed: boolean) {
    // Pehle screen badalte hain, fail ho to wapas server ki sach dikhate hain
    setServers((current) =>
      current
        ? current.map((s) =>
            s.server === server
              ? { ...s, tools: s.tools.map((t) => (t.name === tool ? { ...t, members_allowed: allowed } : t)) }
              : s,
          )
        : current,
    );
    try {
      await api.setPermission(server, tool, allowed);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the change");
      await load();
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Tool permissions</h2>
        <p className="text-sm text-slate-500">
          Choose which tools members can use. Blocked tools disappear from a member's tool list (MCP clients and the
          chat agent) and are rejected if called directly. Admins can always use every tool.
        </p>
        <p className="mt-1 text-sm text-slate-500">
          {denied.length === 0 ? "No restrictions: members can use every tool." : `${denied.length} tool(s) blocked for members.`}
        </p>
      </div>

      {error ? <Notice>{error}</Notice> : null}

      {servers?.map((s) => (
        <Card key={s.server}>
          <div className="mb-3 flex items-center gap-3">
            <h3 className="text-base font-semibold text-slate-900">{s.server}</h3>
            <StatusBadge status={s.status} />
          </div>
          {s.tools.length === 0 ? (
            <p className="text-sm text-slate-500">
              No tools to show while this server is {s.status}. Existing rules still apply.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {s.tools.map((t) => (
                <li key={t.name} className="flex items-center justify-between gap-4 py-2">
                  <div className="min-w-0">
                    <code className="text-sm font-medium text-indigo-700">{t.gateway_name}</code>
                    <p className="truncate text-xs text-slate-500">{t.description || "No description"}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className={`text-xs ${t.members_allowed ? "text-slate-500" : "font-medium text-amber-700"}`}>
                      {t.members_allowed ? "Members allowed" : "Admins only"}
                    </span>
                    <Switch
                      on={t.members_allowed}
                      label={`Allow members to use ${t.gateway_name}`}
                      onChange={(value) => void toggle(s.server, t.name, value)}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
      {servers === null && !error ? <p className="text-sm text-slate-500">Loading…</p> : null}
    </div>
  );
}