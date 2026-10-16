import { useEffect, useState } from "react";
import { api, type User } from "./api";
import { Button } from "./ui";
import AuditPage from "./pages/AuditPage";
import ChangePassword from "./pages/ChangePassword";
import ChatPage from "./pages/ChatPage";
import KeysPage from "./pages/KeysPage";
import Login from "./pages/Login";
import PermissionsPage from "./pages/PermissionsPage";
import ServersPage from "./pages/ServersPage";
import UsersPage from "./pages/UsersPage";

type Tab = "servers" | "permissions" | "users" | "keys" | "chat" | "audit";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("servers");

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function logout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-500">Loading…</div>;
  }
  if (!user) {
    return <Login onLoggedIn={setUser} />;
  }
  if (user.must_change_password) {
    return (
      <ChangePassword
        user={user}
        onDone={() => setUser({ ...user, must_change_password: false })}
        onLogout={logout}
      />
    );
  }

  const tabs: { id: Tab; label: string }[] =
    user.role === "admin"
      ? [
          { id: "servers", label: "MCP servers" },
          { id: "permissions", label: "Permissions" },
          { id: "users", label: "Team" },
          { id: "keys", label: "API keys" },
          { id: "chat", label: "Chat agent" },
          { id: "audit", label: "Audit log" },
        ]
      : [
          { id: "chat", label: "Chat agent" },
          { id: "keys", label: "API keys" },
          { id: "audit", label: "My activity" },
        ];
  const active = tabs.some((t) => t.id === tab) ? tab : tabs[0].id;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
          <div className="flex flex-wrap items-center gap-6">
            <span className="text-base font-semibold text-slate-900">Urumi MCP Gateway</span>
            <nav className="flex flex-wrap gap-1">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    active === t.id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">{user.email}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{user.role}</span>
            <Button onClick={logout}>Sign out</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        {active === "servers" ? <ServersPage /> : null}
        {active === "permissions" ? <PermissionsPage /> : null}
        {active === "users" ? <UsersPage me={user} /> : null}
        {active === "keys" ? <KeysPage user={user} /> : null}
        {active === "chat" ? <ChatPage /> : null}
        {active === "audit" ? <AuditPage user={user} /> : null}
      </main>
    </div>
  );
}