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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

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
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chatRequest),
    });
    if (!response.ok) throw new Error("Failed to send message to ASTRA");
    return response.json();
  },

  getProjects: async (): Promise<Project[]> => {
    const response = await fetch(`${API_BASE_URL}/projects`);
    if (!response.ok) throw new Error("Failed to fetch projects");
    return response.json();
  },

  createProject: async (project: ProjectCreate): Promise<Project> => {
    const response = await fetch(`${API_BASE_URL}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!response.ok) throw new Error("Failed to create project");
    return response.json();
  },

  getProject: async (id: string): Promise<Project> => {
    const response = await fetch(`${API_BASE_URL}/projects/${id}`);
    if (!response.ok) throw new Error("Failed to fetch project details");
    return response.json();
  },

  updateProject: async (
    id: string,
    project: ProjectUpdate
  ): Promise<Project> => {
    const response = await fetch(`${API_BASE_URL}/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!response.ok) throw new Error("Failed to update project");
    return response.json();
  },

  deleteProject: async (id: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/projects/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete project");
  },

  // Workflow Methods
  getWorkflows: async (projectId?: string): Promise<Workflow[]> => {
    const url = projectId
      ? `${API_BASE_URL}/workflows?project_id=${projectId}`
      : `${API_BASE_URL}/workflows`;
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to fetch workflows");
    return response.json();
  },

  createWorkflow: async (workflow: any): Promise<Workflow> => {
    const response = await fetch(`${API_BASE_URL}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workflow),
    });
    if (!response.ok) throw new Error("Failed to create workflow");
    return response.json();
  },

  triggerWorkflow: async (id: string): Promise<any> => {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/trigger`, {
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
    
    const response = await fetch(`${API_BASE_URL}/agent/run`, {
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
};
