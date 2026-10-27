export interface Project {
  id: string;
  name: string;
  description: string;
  task_type: string;
  status: string;
  video_count?: number;
  annotation_count?: number;
  created_at: string;
}

export interface Video {
  id: string;
  project_id: string;
  original_filename: string;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: string;
  managed: boolean;
  annotation_count: number;
  created_at: string;
}

export interface Annotation {
  id: string;
  project_id: string;
  video_id: string;
  start_time: number;
  end_time: number;
  action_label: string;
  object_label: string | null;
  actor_id: string | null;
  confidence: number | null;
  notes: string | null;
  source: string;
  status: string;
  revision: number;
}

export interface ValidationRun {
  id: string;
  status: string;
  total_records: number;
  valid_records: number;
  error_count: number;
  warning_count: number;
  issues: Array<{ code: string; severity: string; message: string; record_id?: string | null; source_row?: number | null }>;
}

export interface RLMetricSummary {
  episode_count: number;
  success_rate: number;
  mean_reward: number;
  mean_steps: number;
}

export interface RLExperiment {
  id: string;
  algorithm: "q_learning" | "baseline";
  status: string;
  environment_version: string;
  random_seed: number;
  actor: string;
  created_at: string;
  configuration: { episodes: number; max_steps: number; [key: string]: number };
  metrics: {
    training: {
      episodes: number;
      mean_reward: number | null;
      success_rate: number | null;
      learning_curve: Array<{ episode: number; mean_reward: number; success_rate: number }>;
    };
    evaluation: { learned_policy: RLMetricSummary; baseline_policy: RLMetricSummary };
  };
  limitations: string[];
}

export interface RLEnvironment {
  environment_version: string;
  grid_width: number;
  start_cell: number;
  object_cell: number;
  goal_cell: number;
  actions: string[];
  reward_design: Record<string, number>;
  limitations: string[];
}

export type KnowledgeScope = "selected_video" | "video_and_documents" | "documents_only" | "project_knowledge";

export interface KnowledgeSource {
  id: string;
  project_id: string;
  video_id: string | null;
  source_type: "pdf" | "video";
  title: string;
  checksum_sha256: string;
  byte_size: number;
  source_version: number;
  page_count: number | null;
  chunk_count: number;
  index_backend: string;
  embedding_model: string;
  embedding_dimensions: number | null;
  embedding_model_revision: string;
  index_status: "pending" | "processing" | "ready" | "failed" | "stale";
  dense_index_status: "not_configured" | "pending" | "processing" | "ready" | "failed" | "stale";
  index_version: number;
  status: "queued" | "processing" | "indexed" | "partially_indexed" | "failed" | "deleted";
  warnings: string[];
  error_summary: string;
  metadata: { visual_pixels_available?: boolean; evidence_basis?: string };
  created_at: string;
  processed_at: string | null;
}

export interface KnowledgeCitation {
  citation_id: string;
  source_id: string;
  source_title: string;
  source_type: string;
  annotation_id: string | null;
  video_id: string | null;
  start_seconds: number | null;
  end_seconds: number | null;
  page_start: number | null;
  page_end: number | null;
  snippet: string;
  content_sha256: string;
  stale?: boolean;
  score?: number;
}

export interface KnowledgeMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  answer_mode: string;
  evidence_status: string;
  retrieval: {
    retrieval?: {
      method: string;
      candidate_count: number;
      used_lexical_fallback: boolean;
      embedding_model: string | null;
      embedding_model_revision?: string | null;
    };
  };
  citations: KnowledgeCitation[];
  created_at: string;
}

export interface KnowledgeConversation {
  id: string;
  project_id: string;
  video_id: string | null;
  title: string;
  scope: KnowledgeScope;
  selected_source_ids: string[];
  created_at: string;
  updated_at: string;
  messages?: KnowledgeMessage[];
}

export interface KnowledgeAnswer {
  conversation_id: string;
  answer: string;
  answer_mode: string;
  evidence_status: string;
  citations: KnowledgeCitation[];
  retrieval: {
    method: string;
    candidate_count: number;
    used_lexical_fallback: boolean;
    embedding_model: string | null;
    embedding_model_revision?: string | null;
  };
  warnings: string[];
  messages: KnowledgeMessage[];
}
