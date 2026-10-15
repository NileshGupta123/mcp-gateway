import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Role, type User, type UserCreated } from "../api";
import { Button, Card, Field, Notice, formatTime, inputClass } from "../ui";

export default function UsersPage({ me }: { me: User }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [busy, setBusy] = useState(false);
  const [invited, setInvited] = useState<UserCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load users");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      setInvited(await api.createUser({ email, name, role }));
      setEmail("");
      setName("");
      setRole("member");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the user");
    } finally {
      setBusy(false);
    }
  }

  async function patch(user: User, body: { role?: Role; active?: boolean }, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setError(null);
    try {
      await api.updateUser(user.id, body);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the user");
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setError("Could not copy. Select the password and copy it manually.");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Team</h2>
        <p className="text-sm text-slate-500">
          Admins manage servers and members. Members use the tools through their own API key and the chat agent.
        </p>
      </div>

      {error ? <Notice>{error}</Notice> : null}

      {invited ? (
        <Card className="ring-emerald-300">
          <h3 className="text-base font-semibold text-slate-900">User created: {invited.email}</h3>
          <p className="mt-1 text-sm text-slate-600">
            Share this temporary password with them now. It is shown only once, and they must change it at first sign-in.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="break-all rounded-md bg-slate-900 px-3 py-2 text-sm text-emerald-300">
              {invited.temporary_password}
            </code>
            <Button onClick={() => void copy(invited.temporary_password)}>{copied ? "Copied" : "Copy"}</Button>
            <Button onClick={() => setInvited(null)}>Done</Button>
          </div>
        </Card>
      ) : null}

      <Card>
        <h3 className="mb-3 text-base font-semibold text-slate-900">Invite a team member</h3>
        <form onSubmit={invite} className="grid gap-4 sm:grid-cols-4 sm:items-end">
          <Field label="Email">
            <input
              className={inputClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label="Name">
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
          </Field>
          <Field label="Role">
            <select className={inputClass} value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Creating…" : "Create user"}
          </Button>
        </form>
      </Card>

      <Card>
        <h3 className="mb-3 text-base font-semibold text-slate-900">Members</h3>
        {users ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Created</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => (
                  <tr key={u.id} className={u.active ? "" : "text-slate-400"}>
                    <td className="py-2 pr-4 font-medium">
                      {u.name}
                      {u.id === me.id ? <span className="ml-2 text-xs text-slate-400">(you)</span> : null}
                    </td>
                    <td className="py-2 pr-4">{u.email}</td>
                    <td className="py-2 pr-4">{u.role}</td>
                    <td className="py-2 pr-4">
                      {u.active ? (
                        u.must_change_password ? "invited" : "active"
                      ) : (
                        "deactivated"
                      )}
                    </td>
                    <td className="py-2 pr-4">{formatTime(u.created_at)}</td>
                    <td className="py-2">
                      {u.id !== me.id ? (
                        <div className="flex justify-end gap-2">
                          <Button
                            onClick={() =>
                              void patch(u, { role: u.role === "admin" ? "member" : "admin" })
                            }
                          >
                            Make {u.role === "admin" ? "member" : "admin"}
                          </Button>
                          {u.active ? (
                            <Button
                              variant="danger"
                              onClick={() =>
                                void patch(
                                  u,
                                  { active: false },
                                  `Deactivate ${u.email}? Their sessions and API keys stop working immediately.`,
                                )
                              }
                            >
                              Deactivate
                            </Button>
                          ) : (
                            <Button onClick={() => void patch(u, { active: true })}>Activate</Button>
                          )}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Loading…</p>
        )}
      </Card>
    </div>
  );
}