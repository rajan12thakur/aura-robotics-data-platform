import type { KnowledgeAnswer, KnowledgeConversation, KnowledgeScope, KnowledgeSource, RLExperiment, RLEnvironment } from "../types/models";

const API_ROOT = "/api/v1";

export interface AuthUser {
  id: number;
  username: string;
  roles: string[];
}

export class ApiError extends Error {
  code: string;
  details: unknown;

  constructor(message: string, code = "API_ERROR", details: unknown = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    let csrfToken = document.cookie.split("; ").find((cookie) => cookie.startsWith("csrftoken="))?.split("=")[1];
    if (!csrfToken && path !== "/auth/csrf") {
      await request<{ csrf_token: string }>("/auth/csrf");
      csrfToken = document.cookie.split("; ").find((cookie) => cookie.startsWith("csrftoken="))?.split("=")[1];
    }
    if (csrfToken) headers.set("X-CSRFToken", decodeURIComponent(csrfToken));
  }
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers, credentials: "include" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(error?.message ?? `Request failed (${response.status}).`, error?.code, error?.details);
  }
  return body as T;
}

function json(method: string, body?: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) };
}

export const api = {
  csrf: () => request<{ csrf_token: string }>("/auth/csrf"),
  me: () => request<{ authenticated: true; user: AuthUser }>("/auth/me"),
  login: (username: string, password: string) => request<{ authenticated: true; user: AuthUser }>("/auth/login", json("POST", { username, password })),
  logout: () => request<{ authenticated: false }>("/auth/logout", json("POST")),
  projects: () => request<any[]>("/projects"),
  createProject: (body: { name: string; description: string; task_type: string }) => request<any>("/projects", json("POST", body)),
  updateProject: (id: string, body: Record<string, unknown>) => request<any>(`/projects/${id}`, json("PATCH", body)),
  archiveProject: (id: string) => request<any>(`/projects/${id}/archive`, json("POST")),
  loadDemo: () => request<any>("/demo/load", json("POST")),
  videos: (projectId: string) => request<any[]>(`/projects/${projectId}/videos`),
  registerVideo: (projectId: string, body: Record<string, unknown>) => request<any>(`/projects/${projectId}/videos/register`, json("POST", body)),
  uploadVideo: (projectId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<any>(`/projects/${projectId}/videos`, { method: "POST", body: data });
  },
  annotations: (videoId: string) => request<any[]>(`/videos/${videoId}/annotations`),
  importAnnotations: (videoId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<any>(`/videos/${videoId}/annotations/import`, { method: "POST", body: data });
  },
  createAnnotation: (videoId: string, body: Record<string, unknown>) => request<any>(`/videos/${videoId}/annotations`, json("POST", body)),
  updateAnnotation: (id: string, body: Record<string, unknown>) => request<any>(`/annotations/${id}`, json("PATCH", body)),
  deleteAnnotation: (id: string) => request<any>(`/annotations/${id}`, { method: "DELETE" }),
  validate: (projectId: string) => request<any>(`/projects/${projectId}/validate`, json("POST")),
  quality: (projectId: string) => request<any>(`/projects/${projectId}/quality-summary`),
  submitForReview: (projectId: string) => request<any>(`/projects/${projectId}/submit-review`, json("POST")),
  review: (projectId: string, decision: string) => request<any>(`/projects/${projectId}/review`, json("POST", { decision })),
  export: (projectId: string, format: string, include_unapproved: boolean) => request<any>(`/projects/${projectId}/exports`, json("POST", { format, include_unapproved })),
  exports: (projectId: string) => request<any[]>(`/projects/${projectId}/exports`),
  ask: (question: string, project_id?: string) => request<any>("/assistant/ask", json("POST", { question, project_id })),
  policy: () => request<any>("/policy/active"),
  policySearch: (q: string) => request<any>(`/policy/search?q=${encodeURIComponent(q)}`),
  audit: (projectId: string) => request<any[]>(`/projects/${projectId}/audit-events`),
  capabilities: () => request<any>("/config/capabilities"),
  prepareSimulation: (projectId: string, videoId?: string) => request<any>(`/projects/${projectId}/simulation/prepare${videoId ? `?video_id=${encodeURIComponent(videoId)}` : ""}`, json("POST")),
  simulation: (id: string, action: "start" | "reset") => request<any>(`/simulation-runs/${id}/${action}`, json("POST")),
  rlEnvironment: () => request<RLEnvironment>("/rl/environment"),
  rlExperiments: (projectId: string) => request<RLExperiment[]>(`/projects/${projectId}/rl-experiments`),
  runRLExperiment: (projectId: string, body: { algorithm: "q_learning" | "baseline"; episodes: number; seed: number; max_steps: number }) => request<RLExperiment>(`/projects/${projectId}/rl-experiments`, json("POST", body)),
  knowledgeSources: (projectId: string, videoId?: string) => request<KnowledgeSource[]>(`/projects/${projectId}/knowledge/sources${videoId ? `?video_id=${encodeURIComponent(videoId)}` : ""}`),
  uploadKnowledgePdf: (projectId: string, file: File, videoId?: string) => {
    const data = new FormData();
    data.append("file", file);
    if (videoId) data.append("video_id", videoId);
    return request<KnowledgeSource>(`/projects/${projectId}/knowledge/sources`, { method: "POST", body: data });
  },
  indexVideoKnowledge: (videoId: string) => request<KnowledgeSource>(`/videos/${videoId}/knowledge/index`, json("POST")),
  retryKnowledgeSource: (sourceId: string) => request<KnowledgeSource>(`/knowledge/sources/${sourceId}/lifecycle`, json("POST")),
  deleteKnowledgeSource: (sourceId: string) => request<{ id: string; status: string }>(`/knowledge/sources/${sourceId}/lifecycle`, { method: "DELETE" }),
  knowledgeConversations: (projectId: string) => request<KnowledgeConversation[]>(`/projects/${projectId}/knowledge/conversations`),
  createKnowledgeConversation: (projectId: string, body: { video_id?: string; scope: KnowledgeScope; source_ids: string[]; title?: string }) => request<KnowledgeConversation>(`/projects/${projectId}/knowledge/conversations`, json("POST", body)),
  getKnowledgeConversation: (conversationId: string) => request<KnowledgeConversation>(`/knowledge/conversations/${conversationId}`),
  renameKnowledgeConversation: (conversationId: string, title: string) => request<KnowledgeConversation>(`/knowledge/conversations/${conversationId}`, json("PATCH", { title })),
  deleteKnowledgeConversation: (conversationId: string) => request<{ id: string; deleted: boolean }>(`/knowledge/conversations/${conversationId}`, { method: "DELETE" }),
  sendKnowledgeMessage: (conversationId: string, question: string) => request<KnowledgeAnswer>(`/knowledge/conversations/${conversationId}/messages`, json("POST", { question })),
};
