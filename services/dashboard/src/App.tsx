import { useEffect, useState } from "react";
import { api, type User } from "./api";
import { Button } from "./ui";
import ChangePassword from "./pages/ChangePassword";
import KeysPage from "./pages/KeysPage";
import Login from "./pages/Login";
import ServersPage from "./pages/ServersPage";

type Tab = "servers" | "keys";

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
          { id: "keys", label: "API keys" },
        ]
      : [{ id: "keys", label: "API keys" }];
  const active = tabs.some((t) => t.id === tab) ? tab : tabs[0].id;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-base font-semibold text-slate-900">Urumi MCP Gateway</span>
            <nav className="flex gap-1">
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
        {active === "servers" ? <ServersPage /> : <KeysPage user={user} />}
      </main>
    </div>
  );
}