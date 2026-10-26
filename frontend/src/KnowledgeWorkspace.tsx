import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api/client";
import type {
  KnowledgeCitation, KnowledgeConversation, KnowledgeMessage, KnowledgeScope, KnowledgeSource, Video,
} from "./types/models";

interface Props {
  projectId: string;
  videos: Video[];
  initialVideoId: string;
}

function formatTime(value: number | null): string {
  return value === null ? "" : `${value.toFixed(3)}s`;
}

export default function KnowledgeWorkspace({ projectId, videos, initialVideoId }: Props) {
  const [videoId, setVideoId] = useState(initialVideoId);
  const [scope, setScope] = useState<KnowledgeScope>("selected_video");
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [conversations, setConversations] = useState<KnowledgeConversation[]>([]);
  const [conversation, setConversation] = useState<KnowledgeConversation | null>(null);
  const [selectedPdfIds, setSelectedPdfIds] = useState<string[]>([]);
  const [attachPdfToVideo, setAttachPdfToVideo] = useState(true);
  const [question, setQuestion] = useState("");
  const [citation, setCitation] = useState<KnowledgeCitation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retrievalSummary, setRetrievalSummary] = useState("");

  const selectedVideo = videos.find((video) => video.id === videoId);
  const pdfSources = useMemo(
    () => sources.filter((source) => source.source_type === "pdf" && (!source.video_id || source.video_id === videoId)),
    [sources, videoId],
  );

  const refreshSources = useCallback(async () => {
    if (!projectId) {
      setSources([]);
      return;
    }
    setSources(await api.knowledgeSources(projectId));
  }, [projectId]);

  const refreshConversations = useCallback(async () => {
    if (!projectId) {
      setConversations([]);
      setConversation(null);
      return;
    }
    setConversations(await api.knowledgeConversations(projectId));
  }, [projectId]);

  useEffect(() => {
    setVideoId(initialVideoId);
    setConversation(null);
    setSelectedPdfIds([]);
    setCitation(null);
    setError("");
    setNotice("");
  }, [initialVideoId, projectId]);

  useEffect(() => {
    Promise.all([refreshSources(), refreshConversations()]).catch((reason: unknown) => {
      setError(reason instanceof ApiError ? reason.message : "Could not load project knowledge.");
    });
  }, [refreshSources, refreshConversations]);

  async function indexVideo() {
    if (!videoId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const source = await api.indexVideoKnowledge(videoId);
      await refreshSources();
      setNotice(`Indexed ${source.chunk_count} stored metadata/annotation record(s). ${source.metadata.visual_pixels_available ? "Video file is present; no visual model analysis is claimed." : "Video pixels are unavailable; this is annotation-grounded only."}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Video evidence indexing failed.");
    } finally { setBusy(false); }
  }

  async function uploadPdf(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !projectId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const source = await api.uploadKnowledgePdf(projectId, file, attachPdfToVideo ? videoId || undefined : undefined);
      await refreshSources();
      setNotice(`PDF processing status: ${source.status}; ${source.chunk_count} chunk(s), ${source.index_backend} retrieval.`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "PDF upload or indexing failed.");
    } finally { setBusy(false); }
  }

  async function retrySource(sourceId: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      const source = await api.retryKnowledgeSource(sourceId);
      await refreshSources();
      setNotice(`Source retry finished: ${source.status} (${source.chunk_count} chunk(s)).`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Source retry failed.");
    } finally { setBusy(false); }
  }

  async function removeSource(source: KnowledgeSource) {
    if (!window.confirm(`Remove "${source.title}" and its searchable chunks?`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api.deleteKnowledgeSource(source.id);
      setSelectedPdfIds((ids) => ids.filter((id) => id !== source.id));
      await refreshSources();
      setNotice("Source removed from the searchable knowledge base.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Source removal failed.");
    } finally { setBusy(false); }
  }

  async function startConversation() {
    setBusy(true); setError(""); setNotice(""); setCitation(null);
    try {
      const created = await api.createKnowledgeConversation(projectId, {
        video_id: videoId || undefined,
        scope,
        source_ids: scope === "video_and_documents" || scope === "documents_only" ? selectedPdfIds : [],
      });
      setConversation(created);
      setRetrievalSummary("");
      await Promise.all([refreshSources(), refreshConversations()]);
      setNotice("New evidence-scoped conversation created.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not start a conversation.");
    } finally { setBusy(false); }
  }

  async function openConversation(id: string) {
    setBusy(true); setError(""); setNotice(""); setCitation(null);
    try {
      const loaded = await api.getKnowledgeConversation(id);
      setConversation(loaded);
      const lastAssistant = [...(loaded.messages ?? [])].reverse().find((message) => message.role === "assistant");
      const retrieval = lastAssistant?.retrieval.retrieval;
      setRetrievalSummary(retrieval ? `${retrieval.method} · ${retrieval.candidate_count} candidate(s)` : "");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not load the conversation.");
    } finally { setBusy(false); }
  }

  async function sendQuestion(event: React.FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (!value || !conversation) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.sendKnowledgeMessage(conversation.id, value);
      const loaded = await api.getKnowledgeConversation(conversation.id);
      setConversation(loaded);
      const lastAssistant = [...(loaded.messages ?? [])].reverse().find((message) => message.role === "assistant");
      const retrieval = lastAssistant?.retrieval.retrieval;
      setRetrievalSummary(retrieval ? `${retrieval.method} · ${retrieval.candidate_count} candidate(s)` : "");
      setQuestion("");
      setNotice(result.evidence_status === "supported" ? "Answer saved with source evidence." : "Answer saved; the selected evidence was insufficient.");
      await refreshConversations();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Question failed; your text is preserved so you can retry.");
    } finally { setBusy(false); }
  }

  async function renameConversation() {
    if (!conversation) return;
    const title = window.prompt("Conversation title", conversation.title);
    if (!title?.trim()) return;
    setBusy(true); setError("");
    try {
      setConversation(await api.renameKnowledgeConversation(conversation.id, title.trim()));
      await refreshConversations();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Conversation rename failed.");
    } finally { setBusy(false); }
  }

  async function removeConversation() {
    if (!conversation || !window.confirm("Delete this conversation and its messages?")) return;
    setBusy(true); setError("");
    try {
      await api.deleteKnowledgeConversation(conversation.id);
      setConversation(null);
      await refreshConversations();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Conversation deletion failed.");
    } finally { setBusy(false); }
  }

  function togglePdf(sourceId: string) {
    setSelectedPdfIds((current) => current.includes(sourceId)
      ? current.filter((id) => id !== sourceId)
      : [...current, sourceId]);
  }

  const canStart = Boolean(
    projectId
    && ((scope === "selected_video" && videoId)
      || (scope === "video_and_documents" && videoId && selectedPdfIds.length)
      || (scope === "documents_only" && selectedPdfIds.length)
      || scope === "project_knowledge"),
  );

  return (
    <section className="knowledge-workspace" aria-label="Video and document chat">
      <div className="section-heading">
        <div><h2>Video &amp; Document Chat</h2><p>Project-scoped retrieval from stored annotations and uploaded PDFs.</p></div>
        <span className="mode-chip">Deterministic extractive answers · no external LLM</span>
      </div>
      {error && <div className="alert error" role="alert"><span>{error}</span><button type="button" onClick={() => setError("")}>Dismiss</button></div>}
      {notice && <div className="alert success" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice("")}>Dismiss</button></div>}

      {!projectId ? <div className="panel"><p>Select a project to manage its knowledge sources.</p></div> : <div className="knowledge-layout">
        <aside className="panel knowledge-sources">
          <h3>Evidence sources</h3>
          <label className="field"><span>Video</span>
            <select value={videoId} onChange={(event) => setVideoId(event.target.value)}>
              <option value="">No video selected</option>
              {videos.map((video) => <option key={video.id} value={video.id}>{video.original_filename}</option>)}
            </select>
          </label>
          <button className="button secondary" type="button" onClick={indexVideo} disabled={!videoId || busy}>
            Index stored video annotations
          </button>
          {selectedVideo && selectedVideo.status === "unavailable" && <p className="knowledge-warning">This asset has no available video pixels. Only saved metadata and annotation records can be used.</p>}
          <label className="field upload-field"><span>Upload a project/video PDF</span>
            <input type="file" accept="application/pdf,.pdf" onChange={uploadPdf} disabled={busy} />
            <small>Private local storage; PDF signature and configured size limit are checked.</small>
          </label>
          <label className="knowledge-check"><input type="checkbox" checked={attachPdfToVideo} disabled={!videoId} onChange={(event) => setAttachPdfToVideo(event.target.checked)} /> Associate uploaded PDF with selected video</label>
          <div className="knowledge-source-list">
            {sources.length === 0 && <p className="muted">No indexed knowledge sources yet.</p>}
            {sources.filter((source) => source.source_type === "video" || !source.video_id || source.video_id === videoId).map((source) => <div className="knowledge-source" key={source.id}>
              <strong>{source.title}</strong>
              <small>{source.source_type} · {source.status} · {source.chunk_count} chunks</small>
              <small>{source.index_backend}{source.embedding_model ? ` · ${source.embedding_model}${source.embedding_dimensions ? ` (${source.embedding_dimensions}D)` : ""}` : ""}</small>
              <small>SHA-256 {source.checksum_sha256.slice(0, 16)}…</small>
              {source.warnings.map((warning) => <small className="knowledge-warning" key={warning}>{warning}</small>)}
              {source.error_summary && <small className="knowledge-error">{source.error_summary}</small>}
              {pdfSources.some((item) => item.id === source.id) && (scope === "video_and_documents" || scope === "documents_only") && source.status !== "failed" &&
                <label className="knowledge-check"><input type="checkbox" checked={selectedPdfIds.includes(source.id)} onChange={() => togglePdf(source.id)} /> Include PDF</label>}
              <div className="knowledge-source-actions">
                {(source.status === "failed" || source.status === "partially_indexed") && <button type="button" className="text-button" disabled={busy} onClick={() => retrySource(source.id)}>Retry / re-index</button>}
                <button type="button" className="text-button danger-text" disabled={busy} onClick={() => removeSource(source)}>Remove</button>
              </div>
            </div>)}
          </div>
          <label className="field"><span>Evidence scope</span>
            <select value={scope} onChange={(event) => setScope(event.target.value as KnowledgeScope)}>
              <option value="selected_video">Selected video</option>
              <option value="video_and_documents">Selected video + selected PDFs</option>
              <option value="documents_only">Selected PDFs only</option>
              <option value="project_knowledge">Project knowledge</option>
            </select>
          </label>
          {(scope === "video_and_documents" || scope === "documents_only") && selectedPdfIds.length === 0 &&
            <small className="knowledge-warning">Select at least one indexed PDF.</small>}
          <button className="button primary" type="button" disabled={!canStart || busy} onClick={startConversation}>New conversation</button>
          <div className="knowledge-history">
            <h3>Conversation history</h3>
            {conversations.length === 0 && <small>No conversations yet.</small>}
            {conversations.map((item) => <button key={item.id} type="button" className={`knowledge-history-item${conversation?.id === item.id ? " active" : ""}`} onClick={() => openConversation(item.id)} disabled={busy}>{item.title}</button>)}
          </div>
        </aside>

        <div className="knowledge-main">
          <div className="panel knowledge-chat">
            <div className="knowledge-chat-head">
              <div><h3>{conversation?.title ?? "Start an evidence-scoped conversation"}</h3><small>{conversation ? `${conversation.scope.replace(/_/g, " ")}${conversation.video_id ? " · video selected" : ""}` : "Choose a scope and create a conversation."}</small></div>
              {conversation && <div className="button-row"><button type="button" className="text-button" onClick={renameConversation} disabled={busy}>Rename</button><button type="button" className="text-button danger-text" onClick={removeConversation} disabled={busy}>Delete</button></div>}
            </div>
            {!conversation && <div className="knowledge-empty"><strong>No conversation open</strong><p>Video answers are grounded in stored AURA records. A missing video file is never treated as visually inspected.</p></div>}
            {conversation && <div className="knowledge-messages" aria-live="polite">
              {(conversation.messages ?? []).length === 0 && <p className="muted">Ask a question about the selected evidence.</p>}
              {(conversation.messages ?? []).map((message: KnowledgeMessage) => <article key={message.id} className={`knowledge-message ${message.role}`}>
                <strong>{message.role === "user" ? "You" : `AURA · ${message.answer_mode}`}</strong>
                <p>{message.content}</p>
                {message.role === "assistant" && <>
                  {message.retrieval.retrieval && <small className="knowledge-diagnostics">{message.retrieval.retrieval.method} · {message.retrieval.retrieval.candidate_count} retrieved · {message.retrieval.retrieval.embedding_model ?? "no embedding model"}</small>}
                  {message.citations.map((item) => <button type="button" className="citation-button" key={item.citation_id} onClick={() => setCitation(item)}>{item.citation_id} · {item.source_title} · {item.page_start ? `page ${item.page_start}` : item.start_seconds !== null ? formatTime(item.start_seconds) : "source record"}{item.score !== undefined ? ` · score ${item.score.toFixed(3)}` : ""}</button>)}
                </>}
              </article>)}
            </div>}
            {conversation && <form className="knowledge-compose" onSubmit={sendQuestion}>
              <label className="field"><span>Question</span><textarea rows={3} maxLength={4000} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask what the selected evidence records…" /></label>
              <button type="submit" className="button primary" disabled={!question.trim() || busy}>{busy ? "Working…" : "Ask from selected evidence"}</button>
            </form>}
            {retrievalSummary && <small className="knowledge-diagnostics">Latest retrieval: {retrievalSummary}</small>}
          </div>

          {citation && <aside className="panel knowledge-evidence" aria-label="Citation evidence">
            <div className="knowledge-chat-head"><h3>Evidence {citation.citation_id}</h3><button type="button" className="text-button" onClick={() => setCitation(null)}>Close</button></div>
            <p><strong>{citation.source_title}</strong> · {citation.source_type}</p>
            {citation.page_start && <p>PDF page {citation.page_start}{citation.page_end && citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}</p>}
            {citation.start_seconds !== null && <p>Video interval {formatTime(citation.start_seconds)}–{formatTime(citation.end_seconds)}</p>}
            {citation.annotation_id && <p>Annotation ID: <code>{citation.annotation_id}</code></p>}
            {citation.score !== undefined && <p>Retrieval score: {citation.score.toFixed(4)}</p>}
            {citation.stale && <p className="knowledge-warning">The original indexed chunk has been removed; this is a saved citation snapshot.</p>}
            <blockquote>{citation.snippet}</blockquote>
            <small>Content SHA-256: {citation.content_sha256}</small>
          </aside>}
        </div>
      </div>}
    </section>
  );
}
