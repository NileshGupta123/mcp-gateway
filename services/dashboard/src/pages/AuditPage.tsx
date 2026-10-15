import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type AuditOutcome, type AuditResponse, type User } from "../api";
import { Button, Card, Notice, inputClass } from "../ui";

const PAGE_SIZE = 25;

const outcomeStyle: Record<AuditOutcome, string> = {
  success: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-700",
  denied: "bg-amber-50 text-amber-700",
};

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
}

export default function AuditPage({ user }: { user: User }) {
  const isAdmin = user.role === "admin";
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [outcome, setOutcome] = useState("");
  const [server, setServer] = useState("");

  const load = useCallback(async () => {
    try {
      setData(
        await api.listAudit({
          limit: PAGE_SIZE,
          offset,
          outcome: outcome || undefined,
          server: server.trim() || undefined,
        }),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the audit log");
    }
  }, [offset, outcome, server]);

  useEffect(() => {
    void load();
    // Naye calls apne aap dikhein, isliye har 10 second mein refresh
    const timer = setInterval(() => void load(), 10000);
    return () => clearInterval(timer);
  }, [load]);

  const total = data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">{isAdmin ? "Audit log" : "My activity"}</h2>
          <p className="text-sm text-slate-500">
            {isAdmin
              ? "Every tool call through the gateway: who, which server and tool, when, how long, and the outcome."
              : "Your tool calls through the gateway."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            className={`${inputClass} w-40`}
            placeholder="Server name"
            value={server}
            onChange={(e) => {
              setServer(e.target.value);
              setOffset(0);
            }}
          />
          <select
            className={`${inputClass} w-36`}
            value={outcome}
            onChange={(e) => {
              setOutcome(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All outcomes</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
            <option value="denied">Denied</option>
          </select>
          <Button onClick={() => void load()}>Refresh</Button>
        </div>
      </div>

      {error ? <Notice>{error}</Notice> : null}

      <Card>
        {data && data.items.length === 0 ? <p className="text-sm text-slate-500">No tool calls yet.</p> : null}
        {data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">User</th>
                  <th className="py-2 pr-4">Server</th>
                  <th className="py-2 pr-4">Tool</th>
                  <th className="py-2 pr-4">Duration</th>
                  <th className="py-2 pr-4">Outcome</th>
                  <th className="py-2">Via</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap py-2 pr-4 text-slate-500">{formatWhen(row.ts)}</td>
                    <td className="py-2 pr-4">{row.user_email}</td>
                    <td className="py-2 pr-4">{row.server ?? "–"}</td>
                    <td className="py-2 pr-4">
                      <code className="text-xs text-indigo-700">{row.tool}</code>
                    </td>
                    <td className="whitespace-nowrap py-2 pr-4 text-slate-500">{row.duration_ms} ms</td>
                    <td className="py-2 pr-4">
                      <span
                        title={row.error ?? undefined}
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${outcomeStyle[row.outcome]}`}
                      >
                        {row.outcome}
                      </span>
                    </td>
                    <td className="py-2 text-slate-500">{row.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {!data ? <p className="text-sm text-slate-500">Loading…</p> : null}
        {data && total > 0 ? (
          <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
            <span>
              {from}–{to} of {total}
            </span>
            <div className="flex gap-2">
              <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Newer
              </Button>
              <Button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Older
              </Button>
            </div>
          </div>
        ) : null}
      </Card>
      <p className="text-xs text-slate-400">Hover an error outcome to see the reason.</p>
    </div>
  );
}