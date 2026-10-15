import { useState, type FormEvent } from "react";
import { api, ApiError, type User } from "../api";
import { Button, Card, Field, Notice, inputClass } from "../ui";

export default function ChangePassword({
  user,
  onDone,
  onLogout,
}: {
  user: User;
  onDone: () => void;
  onLogout: () => void;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next !== confirm) {
      setError("The new passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password");
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-lg font-semibold text-slate-900">Set a new password</h1>
        <p className="mb-4 mt-1 text-sm text-slate-500">
          {user.email} is using a temporary password. Choose your own (at least 10 characters) to continue.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Temporary password">
            <input
              className={inputClass}
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </Field>
          <Field label="New password">
            <input
              className={inputClass}
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              minLength={10}
              required
            />
          </Field>
          <Field label="Repeat new password">
            <input
              className={inputClass}
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              minLength={10}
              required
            />
          </Field>
          {error ? <Notice>{error}</Notice> : null}
          <div className="flex gap-2">
            <Button type="submit" variant="primary" className="flex-1" disabled={busy}>
              {busy ? "Saving…" : "Save password"}
            </Button>
            <Button type="button" onClick={onLogout}>
              Sign out
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}