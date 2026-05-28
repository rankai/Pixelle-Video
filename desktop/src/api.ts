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

export type VoiceAsset = {
  reference_id: string;
  name: string;
  filename: string;
  created_at: string;
  asset_path: string;
  file_url: string;
};

export type PortraitAsset = {
  portrait_id: string;
  name: string;
  filename: string;
  created_at: string;
  media_type: "image" | "video";
  asset_path: string;
  file_url: string;
};

export type VideoAsset = {
  asset_id: string;
  name: string;
  filename: string;
  created_at: string;
  duration: number;
  size: number;
  thumbnail_exists: boolean;
  asset_path: string;
  file_url: string;
  thumbnail_url: string;
};

export type IpTemplateAsset = {
  template_id: string;
  display_name: string;
  short_description: string;
  full_description: string;
  cover_template_path: string;
  preview_image_path: string;
  preview_url: string;
  subtitle_style: Record<string, unknown>;
};

export type TaskInfo = {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress?: {
    current: number;
    total: number;
    percentage: number;
    message: string;
  } | null;
  result?: unknown;
  error?: string;
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
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
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
  return apiFetch<TaskInfo>(`/api/tasks/${taskId}`);
}

export function cancelTask(taskId: string) {
  return apiFetch<{ success: boolean; message: string }>(`/api/tasks/${taskId}`, {
    method: "DELETE",
  });
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

export function listVoiceAssets() {
  return apiFetch<{ items: VoiceAsset[] }>("/api/assets/voices");
}

export function uploadVoiceAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<VoiceAsset>("/api/assets/voices", { method: "POST", body: form });
}

export function deleteVoiceAsset(referenceId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/voices/${referenceId}`, {
    method: "DELETE",
  });
}

export function listPortraitAssets() {
  return apiFetch<{ items: PortraitAsset[] }>("/api/assets/portraits");
}

export function uploadPortraitAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<PortraitAsset>("/api/assets/portraits", { method: "POST", body: form });
}

export function deletePortraitAsset(portraitId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/portraits/${portraitId}`, {
    method: "DELETE",
  });
}

export function listVideoAssets() {
  return apiFetch<{ items: VideoAsset[] }>("/api/assets/videos");
}

export function uploadVideoAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<VideoAsset>("/api/assets/videos", { method: "POST", body: form });
}

export function deleteVideoAsset(assetId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/videos/${assetId}`, {
    method: "DELETE",
  });
}

export function listIpTemplateAssets() {
  return apiFetch<{ items: IpTemplateAsset[] }>("/api/assets/templates/ip-broadcast");
}

export async function assetUrl(path: string) {
  const { apiBaseUrl } = await getRuntime();
  return `${apiBaseUrl}${path}`;
}

export async function assetBlobUrl(path: string) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers();
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(`${apiBaseUrl}${path}`, { headers });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return URL.createObjectURL(await response.blob());
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
