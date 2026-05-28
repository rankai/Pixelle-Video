import { invoke } from "@tauri-apps/api/core";

export type RuntimeInfo = {
  apiBaseUrl: string;
  desktopToken: string;
};

export type IpBroadcastState = {
  session_id: string;
  current_step: number;
  completed_steps: number;
  next_action: {
    key: string;
    step: number;
    label: string;
    description: string;
    disabled: boolean;
  };
  missing_requirements: string[];
  step_status: Record<string, string>;
  notices: Record<string, { kind: string; message: string }>;
  artifacts: Record<string, string>;
  state: Record<string, unknown>;
};

export type DesktopConfig = {
  llm: {
    base_url: string;
    api_key: string;
    model: string;
  };
  runninghub: {
    api_key: string;
    instance_type: string;
  };
  output_dir: string;
};

let runtime: RuntimeInfo | null = null;

export async function getRuntime(): Promise<RuntimeInfo> {
  if (runtime) return runtime;
  try {
    runtime = await invoke<RuntimeInfo>("desktop_runtime");
  } catch {
    runtime = {
      apiBaseUrl: "http://127.0.0.1:8000",
      desktopToken: "",
    };
  }
  return runtime;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function createSession() {
  return apiFetch<IpBroadcastState>("/api/ip-broadcast/sessions", { method: "POST" });
}

export function getSession(sessionId: string) {
  return apiFetch<IpBroadcastState>(`/api/ip-broadcast/sessions/${sessionId}`);
}

export function updateSessionConfig(sessionId: string, values: Record<string, unknown>) {
  return apiFetch<IpBroadcastState>(`/api/ip-broadcast/sessions/${sessionId}/config`, {
    method: "PATCH",
    body: JSON.stringify(values),
  });
}

export function runStep(sessionId: string, stepKey: string) {
  return apiFetch<{ session_id: string; step_key: string; task_id: string }>(
    `/api/ip-broadcast/sessions/${sessionId}/steps/${stepKey}/run`,
    { method: "POST" },
  );
}

export function getTask(taskId: string) {
  return apiFetch<{
    task_id: string;
    status: "pending" | "running" | "completed" | "failed" | "cancelled";
    result?: unknown;
    error?: string;
  }>(`/api/tasks/${taskId}`);
}

export function getDesktopConfig() {
  return apiFetch<DesktopConfig>("/api/desktop/config");
}

export function saveDesktopConfig(config: Partial<DesktopConfig>) {
  return apiFetch<DesktopConfig>("/api/desktop/config", {
    method: "PATCH",
    body: JSON.stringify(config),
  });
}

export function getDiagnostics() {
  return apiFetch<Record<string, unknown>>("/api/desktop/diagnostics");
}

export async function downloadArtifact(sessionId: string, artifactKey: string) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers();
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(
    `${apiBaseUrl}/api/ip-broadcast/sessions/${sessionId}/artifacts/${artifactKey}`,
    { headers },
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] || `${artifactKey}.mp4`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
