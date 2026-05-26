export interface WatchedDirectory {
  id: number;
  path: string;
  project_id: string;
  enabled: boolean;
  recursive: boolean;
  allowed_extensions: string;
  debounce_seconds: number;
  created_at: string;
  last_scan_at?: string;
  file_count?: number;
}

export interface ScheduledTask {
  id: number;
  name: string;
  cron_expression: string;
  agent_prompt: string;
  project_id: string;
  enabled: boolean;
  created_at: string;
  last_run?: string;
  next_run?: string;
}

export interface Document {
  file_id: string;
  filename: string;
  original_name: string;
  status: string;
  rag_enabled: boolean;
  project_id: string;
  chunk_count: number;
  uploaded_at: string;
  file_type: string;
  file_size_bytes: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  project_type: string;
  created_at: string;
  last_accessed_at: string;
  active: boolean;
  metadata?: any;
  history?: any[];
}

export interface EpisodicMemoryItem {
  id: string;
  task: string;
  tools_used: string[];
  success: boolean;
  summary: string;
  project_id: string;
  importance: number;
  session_id: string;
  access_count: number;
  last_accessed?: string;
  created_at: string;
}

export interface EpisodicMemoryResponse {
  episodes: EpisodicMemoryItem[];
  total: number;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  project_type?: string;
  metadata?: any;
  history?: any[];
  active?: boolean;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  project_type?: string;
  metadata?: any;
}

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

// ── Auth token management ──────────────────────────────────────────────
// Fetch the local session token once from the (public) /auth/token endpoint
// and cache it for the lifetime of the app. All API calls include it as
// Authorization: Bearer <token>.
let _cachedToken: string | null = null;

export async function getAuthToken(): Promise<string> {
  if (_cachedToken) return _cachedToken;
  try {
    const res = await fetch(`${API_BASE_URL}/auth/token`);
    if (res.ok) {
      const data = await res.json();
      _cachedToken = data.token;
      return _cachedToken!;
    }
  } catch {
    // Fall through — backend may not be up yet
  }
  return "";
}

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (_cachedToken) {
    headers["Authorization"] = `Bearer ${_cachedToken}`;
  }
  return headers;
}

export async function authFetch(url: string, opts: RequestInit = {}): Promise<Response> {
  // Ensure token is loaded before first request
  if (!_cachedToken) await getAuthToken();
  
  const headers = new Headers(opts.headers || {});
  if (_cachedToken) {
    headers.set("Authorization", `Bearer ${_cachedToken}`);
  }
  
  return fetch(url, { ...opts, headers });
}

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  project_id: string;
  type: string;
  trigger_type: string;
  trigger_config?: string;
  status: string;
  last_run?: string;
  created_at: string;
  steps?: string[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  project_id?: string;
  model_name?: string;
}

export interface ChatResponse {
  content: string;
  model: string;
  citations?: string[];
  artifact_url?: string;
  usage?: {
    engine: string;
    agent?: string;
    iterations?: number;
    thoughts?: string[];
  };
}

export const api = {
  sendMessage: async (chatRequest: ChatRequest): Promise<ChatResponse> => {
    const response = await authFetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chatRequest),
    });
    if (!response.ok) throw new Error("Failed to send message to ASTRA");
    return response.json();
  },

  getProjects: async (): Promise<Project[]> => {
    const response = await authFetch(`${API_BASE_URL}/projects`);
    if (!response.ok) throw new Error("Failed to fetch projects");
    return response.json();
  },

  createProject: async (project: ProjectCreate): Promise<Project> => {
    const response = await authFetch(`${API_BASE_URL}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!response.ok) throw new Error("Failed to create project");
    return response.json();
  },

  getProject: async (id: string): Promise<Project> => {
    const response = await authFetch(`${API_BASE_URL}/projects/${id}`);
    if (!response.ok) throw new Error("Failed to fetch project details");
    return response.json();
  },

  updateProject: async (
    id: string,
    project: ProjectUpdate
  ): Promise<Project> => {
    const response = await authFetch(`${API_BASE_URL}/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!response.ok) throw new Error("Failed to update project");
    return response.json();
  },

  deleteProject: async (id: string): Promise<void> => {
    const response = await authFetch(`${API_BASE_URL}/projects/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete project");
  },

  // Workflow Methods
  getWorkflows: async (projectId?: string): Promise<Workflow[]> => {
    const url = projectId
      ? `${API_BASE_URL}/workflows?project_id=${projectId}`
      : `${API_BASE_URL}/workflows`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error("Failed to fetch workflows");
    return response.json();
  },

  createWorkflow: async (workflow: any): Promise<Workflow> => {
    const response = await authFetch(`${API_BASE_URL}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workflow),
    });
    if (!response.ok) throw new Error("Failed to create workflow");
    return response.json();
  },

  triggerWorkflow: async (id: string): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/workflows/${id}/trigger`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Failed to trigger workflow");
    return response.json();
  },

  /**
   * Streams chat messages from backend with proper buffer handling.
   * Supports AbortController for cancellation.
   */
  streamMessage: async (
    chatRequest: ChatRequest,
    onChunk: (chunk: any) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    // Extract the latest user message as the task for the agent
    const task = chatRequest.messages.length > 0 ? chatRequest.messages[chatRequest.messages.length - 1].content : "";
    
    const response = await authFetch(`${API_BASE_URL}/agent/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task: task,
        project_id: chatRequest.project_id,
        model: chatRequest.model_name
      }),
      signal,
    });

    if (!response.ok) {
      const errText = await response.text().catch(() => "Unknown error");
      throw new Error(`ASTRA Stream failed (${response.status}): ${errText}`);
    }
    if (!response.body) throw new Error("No response body");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last (potentially incomplete) line in the buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed === "[DONE]") continue;

          // Strip standard SSE "data: " prefix before JSON parsing
          const jsonStr = trimmed.startsWith("data: ")
            ? trimmed.slice(6)
            : trimmed;

          try {
            const data = JSON.parse(jsonStr);
            onChunk(data);
          } catch {
            console.warn("Skipping unparseable stream line:", trimmed);
          }
        }
      }

      // CRITICAL FIX: Process any remaining data in the buffer after stream ends
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer.trim());
          onChunk(data);
        } catch {
          console.warn("Skipping final buffer remnant:", buffer);
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  getMemoryEpisodes: async (
    projectId: string = "default",
    limit: number = 50,
    offset: number = 0
  ): Promise<EpisodicMemoryResponse> => {
    const response = await authFetch(
      `${API_BASE_URL}/memory?project_id=${projectId}&limit=${limit}&offset=${offset}`
    );
    if (!response.ok) throw new Error("Failed to fetch memory episodes");
    return response.json();
  },

  deleteMemoryEpisode: async (episodeId: string): Promise<void> => {
    const response = await authFetch(`${API_BASE_URL}/memory/${episodeId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete memory episode");
  },

  listDocuments: async (projectId: string): Promise<{ documents: Document[] }> => {
    const response = await authFetch(`${API_BASE_URL}/documents/list/${projectId}`);
    if (!response.ok) throw new Error("Failed to fetch documents");
    return response.json();
  },

  toggleDocument: async (fileId: string, enabled: boolean): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/documents/toggle/${fileId}?enabled=${enabled}`, {
      method: "PATCH",
    });
    if (!response.ok) throw new Error("Failed to toggle document RAG status");
    return response.json();
  },

  deleteDocument: async (fileId: string): Promise<void> => {
    const response = await authFetch(`${API_BASE_URL}/documents/${fileId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete document");
  },

  getStats: async (): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/stats`);
    if (!response.ok) throw new Error("Failed to fetch system stats");
    return response.json();
  },

  getSettings: async (): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/settings`);
    if (!response.ok) throw new Error("Failed to fetch settings");
    return response.json();
  },

  updateSettings: async (settings: any): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!response.ok) throw new Error("Failed to update settings");
    return response.json();
  },

  getTasks: async (projectId: string): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/tasks?project_id=${projectId}`);
    if (!response.ok) throw new Error("Failed to fetch background tasks");
    return response.json();
  },

  // ── Phase 3B: Sleep Mode ─────────────────────────────────────────

  sleepAgent: async (): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/sleep`, { method: "POST" });
    if (!response.ok) throw new Error("Failed to sleep agent");
    return response.json();
  },

  wakeAgent: async (): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/agent/wake`, { method: "POST" });
    if (!response.ok) throw new Error("Failed to wake agent");
    return response.json();
  },

  getSleepStatus: async (): Promise<{ sleeping: boolean; model: string }> => {
    const response = await authFetch(`${API_BASE_URL}/agent/sleep-status`);
    if (!response.ok) throw new Error("Failed to fetch sleep status");
    return response.json();
  },

  // ── Phase 3B: Background Task Run Count ──────────────────────────

  getTaskRunCount: async (since?: string): Promise<{ count: number }> => {
    const url = since
      ? `${API_BASE_URL}/agent/task-run-count?since=${encodeURIComponent(since)}`
      : `${API_BASE_URL}/agent/task-run-count`;
    const response = await authFetch(url);
    if (!response.ok) return { count: 0 };
    return response.json();
  },

  // ── Phase 3B: Watcher Endpoints ──────────────────────────────────

  listWatchedDirectories: async (): Promise<WatchedDirectory[]> => {
    const response = await authFetch(`${API_BASE_URL}/watcher/directories`);
    if (!response.ok) throw new Error("Failed to fetch watched directories");
    return response.json();
  },

  addWatchedDirectory: async (
    dir: Omit<WatchedDirectory, "id" | "created_at">
  ): Promise<WatchedDirectory> => {
    const response = await authFetch(`${API_BASE_URL}/watcher/directories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dir),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Failed to add watched directory" }));
      throw new Error(err.detail || "Failed to add watched directory");
    }
    return response.json();
  },

  updateWatchedDirectory: async (
    id: number,
    updates: Partial<WatchedDirectory>
  ): Promise<WatchedDirectory> => {
    const response = await authFetch(`${API_BASE_URL}/watcher/directories/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!response.ok) throw new Error("Failed to update watched directory");
    return response.json();
  },

  deleteWatchedDirectory: async (id: number): Promise<void> => {
    const response = await authFetch(`${API_BASE_URL}/watcher/directories/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete watched directory");
  },

  triggerWatchedDirectoryScan: async (id: number): Promise<{ status: string; indexed_count: number }> => {
    const response = await authFetch(`${API_BASE_URL}/watcher/directories/${id}/scan`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Failed to trigger directory scan");
    return response.json();
  },

  // ── Phase 3B: Scheduler Endpoints ────────────────────────────────

  listScheduledTasks: async (): Promise<ScheduledTask[]> => {
    const response = await authFetch(`${API_BASE_URL}/scheduler/tasks`);
    if (!response.ok) throw new Error("Failed to fetch scheduled tasks");
    return response.json();
  },

  addScheduledTask: async (
    task: Omit<ScheduledTask, "id" | "created_at">
  ): Promise<ScheduledTask> => {
    const response = await authFetch(`${API_BASE_URL}/scheduler/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(task),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Failed to add scheduled task" }));
      throw new Error(err.detail || "Failed to add scheduled task");
    }
    return response.json();
  },

  updateScheduledTask: async (
    id: number,
    updates: Partial<ScheduledTask>
  ): Promise<ScheduledTask> => {
    const response = await authFetch(`${API_BASE_URL}/scheduler/tasks/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!response.ok) throw new Error("Failed to update scheduled task");
    return response.json();
  },

  deleteScheduledTask: async (id: number): Promise<void> => {
    const response = await authFetch(`${API_BASE_URL}/scheduler/tasks/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete scheduled task");
  },

  triggerScheduledTask: async (id: number): Promise<any> => {
    const response = await authFetch(`${API_BASE_URL}/scheduler/tasks/${id}/trigger`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Failed to trigger scheduled task");
    return response.json();
  },
};
