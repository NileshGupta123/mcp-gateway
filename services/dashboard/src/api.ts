export type Role = "admin" | "member";
export type ServerStatus = "connected" | "unreachable" | "disabled";
export type AuthType = "none" | "bearer" | "header";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface ServerTool {
  name: string;
  gateway_name: string;
  description: string;
}

export interface Server {
  id: number;
  name: string;
  url: string;
  enabled: boolean;
  auth_type: AuthType;
  header_name: string | null;
  has_credential: boolean;
  status: ServerStatus;
  error: string | null;
  latency_ms: number | null;
  checked_at: string | null;
  created_at: string;
  tools: ServerTool[];
}

export interface ServerCreate {
  name: string;
  url: string;
  auth_type: AuthType;
  header_name?: string;
  credential?: string;
}

export interface ServerUpdate {
  url?: string;
  enabled?: boolean;
  auth_type?: AuthType;
  header_name?: string;
  credential?: string;
  clear_credential?: boolean;
}

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  user_id: number;
  user_email: string | null;
  status: "active" | "revoked";
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface CreatedKey extends ApiKey {
  key: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg, ...}]
    const parts = detail.map((d) => {
      const item = d as { loc?: unknown[]; msg?: string };
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
      return item.msg ? `${field ? field + ": " : ""}${item.msg}` : "";
    });
    const joined = parts.filter(Boolean).join("; ");
    return joined || fallback;
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const data = await res.json();
      message = formatDetail(data?.detail, message);
    } catch {
      /* response JSON nahi tha */
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<User>("POST", "/api/auth/login", { email, password }),
  logout: () => request<{ ok: boolean }>("POST", "/api/auth/logout"),
  me: () => request<User>("GET", "/api/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("POST", "/api/auth/change-password", { current_password, new_password }),

  listServers: (refresh = false) => request<Server[]>("GET", `/api/servers${refresh ? "?refresh=true" : ""}`),
  createServer: (body: ServerCreate) => request<Server>("POST", "/api/servers", body),
  updateServer: (id: number, body: ServerUpdate) => request<Server>("PATCH", `/api/servers/${id}`, body),
  deleteServer: (id: number) => request<{ deleted: number }>("DELETE", `/api/servers/${id}`),

  listKeys: (all = false) => request<ApiKey[]>("GET", `/api/keys${all ? "?all=true" : ""}`),
  createKey: (name: string) => request<CreatedKey>("POST", "/api/keys", { name }),
  revokeKey: (id: number) => request<ApiKey>("DELETE", `/api/keys/${id}`),
};