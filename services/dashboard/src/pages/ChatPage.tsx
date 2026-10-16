import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type ChatToolCall } from "../api";
import { Button, Card, Notice, inputClass } from "../ui";

interface Turn {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ChatToolCall[];
}

const SUGGESTIONS = [
  "What orders came in today?",
  "Create a product called Blue Notebook priced at 150 rupees",
  "What time is it in New York? Save a note with that time.",
];

function ToolCalls({ calls }: { calls: ChatToolCall[] }) {
  return (
    <div className="mt-2 space-y-1">
      {calls.map((c, i) => (
        <details key={i} className="rounded-md bg-white ring-1 ring-slate-200">
          <summary className="cursor-pointer list-none px-3 py-1.5 text-xs">
            <span className={c.ok ? "font-medium text-emerald-700" : "font-medium text-red-600"}>
              {c.ok ? "ok" : "failed"}
            </span>
            <code className="ml-2 text-indigo-700">{c.name}</code>
            <span className="ml-2 text-slate-400">{c.duration_ms} ms</span>
          </summary>
          <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
            <div className="font-medium text-slate-500">Arguments</div>
            <pre className="mb-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(c.arguments, null, 2)}</pre>
            <div className="font-medium text-slate-500">Result</div>
            <pre className="overflow-x-auto whitespace-pre-wrap">{c.result}</pre>
          </div>
        </details>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: Turn[] = [...turns, { role: "user", content }];
    setTurns(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      // Server stateless hai: har request mein recent history jaati hai (sirf text)
      const history = next.slice(-12).map((t) => ({ role: t.role, content: t.content }));
      const res = await api.chat(history);
      setTurns([...next, { role: "assistant", content: res.reply, toolCalls: res.tool_calls }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the gateway");
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Chat agent</h2>
          <p className="text-sm text-slate-500">
            Ask in plain language. The agent calls the same gateway tools as an external MCP client, as you, so every
            call shows up in the audit log under your name.
          </p>
        </div>
        {turns.length > 0 ? (
          <Button
            onClick={() => {
              setTurns([]);
              setError(null);
            }}
          >
            Clear chat
          </Button>
        ) : null}
      </div>

      <Card className="flex min-h-[24rem] flex-col">
        <div className="flex-1 space-y-4">
          {turns.length === 0 ? (
            <div>
              <p className="text-sm text-slate-500">Try one of these:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} onClick={() => void send(s)} disabled={busy}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          ) : null}
          {turns.map((t, i) => (
            <div key={i} className={t.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  t.role === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                }`}
              >
                <div className="whitespace-pre-wrap">{t.content}</div>
                {t.toolCalls && t.toolCalls.length > 0 ? <ToolCalls calls={t.toolCalls} /> : null}
              </div>
            </div>
          ))}
          {busy ? <p className="text-sm text-slate-400">Thinking and calling tools…</p> : null}
          <div ref={endRef} />
        </div>

        {error ? (
          <div className="mt-3">
            <Notice>{error}</Notice>
          </div>
        ) : null}

        <form onSubmit={submit} className="mt-4 flex gap-2">
          <input
            className={inputClass}
            placeholder="Ask about orders, products, notes or time…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={4000}
            disabled={busy}
          />
          <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
            Send
          </Button>
        </form>
      </Card>
    </div>
  );
}