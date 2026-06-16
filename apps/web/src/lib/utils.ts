import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatSize(bytes?: number | null) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function statusTone(value?: string | boolean | null) {
  if (value === true) return "ok";
  if (value === false) return "warn";
  if (!value) return "muted";
  const text = String(value);
  if (["ready", "present", "prepared", "ok", "pass", "passed", "usable"].includes(text)) return "ok";
  if (["missing", "blocked", "blocked_by_phase3_gate", "not_authorized", "needs_extraction", "needs_hotpe"].includes(text)) {
    return "warn";
  }
  if (["danger", "failed", "error", "invalid"].includes(text)) return "danger";
  return "muted";
}

export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json() as Promise<T>;
}

export async function postAdmin<T>(url: string, payload: unknown, token: string): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-SynaBoot-Admin-Token": token,
    },
    body: JSON.stringify(payload ?? {}),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${url} ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  return (contentType.includes("application/json") ? response.json() : response.text()) as Promise<T>;
}
