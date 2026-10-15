import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ServerStatus } from "./api";

const base =
  "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";

const variants = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-500",
  secondary: "bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50",
  danger: "bg-white text-red-600 ring-1 ring-red-200 hover:bg-red-50",
} as const;

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants }) {
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg bg-white p-5 shadow-sm ring-1 ring-slate-200 ${className}`}>{children}</div>;
}

export function Notice({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  const styles = {
    error: "bg-red-50 text-red-700 ring-red-200",
    success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    info: "bg-slate-50 text-slate-700 ring-slate-200",
  } as const;
  return <div className={`rounded-md px-3 py-2 text-sm ring-1 ${styles[kind]}`}>{children}</div>;
}

export const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
}

export function StatusBadge({ status }: { status: ServerStatus }) {
  const map = {
    connected: { label: "Connected", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500" },
    unreachable: { label: "Unreachable", cls: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
    disabled: { label: "Disabled", cls: "bg-slate-100 text-slate-600 ring-slate-200", dot: "bg-slate-400" },
  } as const;
  const s = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${s.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

export function formatTime(iso: string | null): string {
  if (!iso) return "never";
  const date = new Date(iso);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}