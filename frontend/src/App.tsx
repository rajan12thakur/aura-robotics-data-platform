import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity, Archive, Bot, Boxes, BrainCircuit, CheckCircle2, ChevronRight, CircleHelp, ClipboardCheck, FileSearch,
  Clock3, Download, FileVideo2, FolderKanban, Gauge, History, LoaderCircle, Plus,
  Play, RefreshCw, RotateCcw, Save, Settings2, ShieldCheck, Sparkles, TrendingUp, Upload, Video, LogOut,
} from "lucide-react";
import { ApiError, api, type AuthUser } from "./api/client";
import KnowledgeWorkspace from "./KnowledgeWorkspace";
import type { Annotation, Project, RLExperiment, RLEnvironment, ValidationRun, Video as VideoAsset } from "./types/models";

type Page = "Overview" | "Projects" | "Annotation Workspace" | "Dataset Quality" | "AI Assistant" | "Video & Document Chat" | "Simulation" | "Policy & Guidelines" | "Audit Trail" | "Settings";
const pages: Array<{ name: Page; icon: typeof Activity }> = [
  { name: "Overview", icon: Gauge }, { name: "Projects", icon: FolderKanban },
  { name: "Annotation Workspace", icon: Video }, { name: "Dataset Quality", icon: ClipboardCheck },
  { name: "AI Assistant", icon: Bot }, { name: "Video & Document Chat", icon: FileSearch }, { name: "Simulation", icon: Boxes },
  { name: "Policy & Guidelines", icon: ShieldCheck }, { name: "Audit Trail", icon: History },
  { name: "Settings", icon: Settings2 },
];
const labels = ["approach", "reach", "grasp", "lift", "move", "place", "release", "withdraw", "inspect", "other"];

function readableDate(value?: string) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [page, setPage] = useState<Page>("Overview");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [videoId, setVideoId] = useState("");
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [quality, setQuality] = useState<any>(null);
  const [exports, setExports] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [capabilities, setCapabilities] = useState<any>(null);
  const [policy, setPolicy] = useState<any>(null);
  const [simulation, setSimulation] = useState<any>(null);
  const [rlExperiments, setRlExperiments] = useState<RLExperiment[]>([]);
  const [rlEnvironment, setRlEnvironment] = useState<RLEnvironment | null>(null);
  const [rlForm, setRlForm] = useState({ episodes: "500", seed: "7" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [projectForm, setProjectForm] = useState({ name: "", description: "", task_type: "pick_and_place" });
  const [editingProjectId, setEditingProjectId] = useState("");
  const [videoForm, setVideoForm] = useState({ original_filename: "", duration_seconds: "" });
  const [annotationForm, setAnnotationForm] = useState({ start_time: "0", end_time: "1", action_label: "approach", object_label: "", actor_id: "human_1", notes: "" });
  const [currentTime, setCurrentTime] = useState(0);
  const [editingId, setEditingId] = useState("");
  const videoElement = useRef<HTMLVideoElement>(null);
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantResult, setAssistantResult] = useState<any>(null);
  const [policyQuery, setPolicyQuery] = useState("");
  const [policyResults, setPolicyResults] = useState<any[]>([]);
  const project = projects.find((item) => item.id === projectId);
  const selectedVideo = videos.find((item) => item.id === videoId);
  const roles = user?.roles ?? [];
  const canAnnotate = roles.some((role) => ["Administrator", "Project Manager", "Annotator"].includes(role));
  const canReview = roles.some((role) => ["Administrator", "Reviewer"].includes(role));
  const canExport = roles.some((role) => ["Administrator", "Dataset Manager"].includes(role));
  const canRunExperiment = roles.some((role) => ["Administrator", "Project Manager", "ML Engineer"].includes(role));

  const notifyError = (reason: unknown) => {
    setError(reason instanceof ApiError ? `${reason.message} (${reason.code})` : reason instanceof Error ? reason.message : "Unexpected request failure.");
    setNotice("");
  };

  const loadProjects = useCallback(async () => {
    const result = await api.projects();
    setProjects(result);
    setProjectId((current) => result.some((item: Project) => item.id === current) ? current : result[0]?.id ?? "");
  }, []);

  const loadProjectData = useCallback(async () => {
    if (!projectId) {
      setVideos([]); setVideoId(""); setQuality(null); setExports([]); setAudit([]); setRlExperiments([]);
      return;
    }
    const [videoRows, summary, exportRows, auditRows, experimentRows] = await Promise.all([
      api.videos(projectId), api.quality(projectId), api.exports(projectId), api.audit(projectId), api.rlExperiments(projectId),
    ]);
    setVideos(videoRows);
    setVideoId((current) => videoRows.some((item: VideoAsset) => item.id === current) ? current : videoRows[0]?.id ?? "");
    setQuality(summary); setExports(exportRows); setAudit(auditRows); setRlExperiments(experimentRows);
  }, [projectId]);

  const loadAnnotations = useCallback(async () => {
    if (!videoId) { setAnnotations([]); return; }
    setAnnotations(await api.annotations(videoId));
  }, [videoId]);

  useEffect(() => {
    api.csrf().then(() => api.me())
      .then(({ user: currentUser }) => { setUser(currentUser); setAuthenticated(true); })
      .catch((reason: unknown) => {
        if (reason instanceof ApiError && reason.code === "AUTHENTICATION_REQUIRED") {
          setAuthenticated(false);
          return;
        }
        notifyError(reason);
        setAuthenticated(false);
      });
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    setLoading(true);
    Promise.all([loadProjects(), api.capabilities(), api.policy(), api.rlEnvironment()])
      .then(([, caps, activePolicy, environment]) => { setCapabilities(caps); setPolicy(activePolicy); setRlEnvironment(environment); })
      .catch(notifyError).finally(() => setLoading(false));
  }, [authenticated, loadProjects]);

  useEffect(() => {
    if (!authenticated) return;
    setLoading(true);
    loadProjectData().catch(notifyError).finally(() => setLoading(false));
  }, [authenticated, loadProjectData]);

  useEffect(() => {
    if (!authenticated) return;
    loadAnnotations().catch(notifyError);
  }, [authenticated, loadAnnotations]);

  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api.login(loginForm.username, loginForm.password);
      setUser(result.user);
      setAuthenticated(true);
      setLoginForm({ username: "", password: "" });
      setNotice(`Signed in as ${result.user.username}.`);
    } catch (reason) { notifyError(reason); }
  }

  async function signOut() {
    try {
      await api.logout();
      setUser(null);
      setAuthenticated(false);
      setProjects([]); setVideos([]); setAnnotations([]);
    } catch (reason) { notifyError(reason); }
  }

  async function refresh() {
    setLoading(true);
    try { await loadProjects(); await loadProjectData(); await loadAnnotations(); setNotice("Workspace data refreshed."); }
    catch (reason) { notifyError(reason); }
    finally { setLoading(false); }
  }

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    try {
      const created = editingProjectId ? await api.updateProject(editingProjectId, projectForm) : await api.createProject(projectForm);
      setProjectForm({ name: "", description: "", task_type: "pick_and_place" });
      setEditingProjectId("");
      await loadProjects();
      setProjectId(created.id);
      setNotice(editingProjectId ? `Project "${created.name}" updated.` : `Project "${created.name}" created.`);
    } catch (reason) { notifyError(reason); }
  }

  async function archiveProject(projectItem: Project) {
    if (!window.confirm(`Archive "${projectItem.name}"? Existing records remain preserved.`)) return;
    try {
      await api.archiveProject(projectItem.id);
      await loadProjects();
      setNotice(`Project "${projectItem.name}" archived.`);
    } catch (reason) { notifyError(reason); }
  }

  async function loadSyntheticDemo() {
    try {
      const result = await api.loadDemo();
      await loadProjects();
      setProjectId(result.project.id);
      setPage("Annotation Workspace");
      setNotice(result.created ? "Synthetic Demo project loaded. It contains no real video or human-labeled data." : "Synthetic Demo project already exists; existing records were preserved.");
    } catch (reason) { notifyError(reason); }
  }

  async function registerVideo(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    try {
      const body = { ...videoForm, duration_seconds: videoForm.duration_seconds ? Number(videoForm.duration_seconds) : null };
      const created = await api.registerVideo(projectId, body);
      setVideoForm({ original_filename: "", duration_seconds: "" });
      await loadProjectData();
      setVideoId(created.id);
      setNotice("Video metadata registered. Playback is unavailable for metadata-only videos.");
    } catch (reason) { notifyError(reason); }
  }

  async function uploadVideo(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !projectId) return;
    try {
      const uploaded = await api.uploadVideo(projectId, file);
      await loadProjectData();
      setVideoId(uploaded.id);
      setNotice(`Uploaded ${uploaded.original_filename}.`);
    } catch (reason) { notifyError(reason); }
    finally { event.target.value = ""; }
  }

  async function importAnnotations(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !videoId) return;
    try {
      const result = await api.importAnnotations(videoId, file);
      await Promise.all([loadAnnotations(), loadProjectData()]);
      setNotice(`Imported ${result.imported_count} annotation(s).`);
    } catch (reason) { notifyError(reason); }
    finally { event.target.value = ""; }
  }

  async function saveAnnotation(event: React.FormEvent) {
    event.preventDefault();
    if (!videoId) return;
    const body = { ...annotationForm, start_time: Number(annotationForm.start_time), end_time: Number(annotationForm.end_time), object_label: annotationForm.object_label || null, actor_id: annotationForm.actor_id || null, notes: annotationForm.notes || null, source: "human" };
    if (!Number.isFinite(body.start_time) || !Number.isFinite(body.end_time) || body.start_time < 0 || body.end_time <= body.start_time) {
      setError("Enter finite seconds with start >= 0 and end > start."); return;
    }
    try {
      if (editingId) await api.updateAnnotation(editingId, body);
      else await api.createAnnotation(videoId, body);
      setEditingId("");
      await Promise.all([loadAnnotations(), loadProjectData()]);
      setNotice(editingId ? "Annotation updated." : "Annotation saved as draft.");
    } catch (reason) { notifyError(reason); }
  }

  function editAnnotation(item: Annotation) {
    if (videoElement.current && selectedVideo?.managed) {
      videoElement.current.currentTime = item.start_time;
      setCurrentTime(item.start_time);
    }
    setEditingId(item.id);
    setAnnotationForm({ start_time: String(item.start_time), end_time: String(item.end_time), action_label: item.action_label, object_label: item.object_label ?? "", actor_id: item.actor_id ?? "", notes: item.notes ?? "" });
  }

  async function removeAnnotation(id: string) {
    if (!window.confirm("Delete this annotation? This action is recorded in the audit trail.")) return;
    try {
      await api.deleteAnnotation(id);
      await Promise.all([loadAnnotations(), loadProjectData()]);
      setNotice("Annotation deleted.");
    } catch (reason) { notifyError(reason); }
  }

  async function validateProject() {
    if (!projectId) return;
    try {
      const result: ValidationRun = await api.validate(projectId);
      await loadProjectData();
      setNotice(`Validation ${result.status}: ${result.error_count} errors, ${result.warning_count} warnings.`);
    } catch (reason) { notifyError(reason); }
  }

  async function createExport(format: "csv" | "json", includeUnapproved = false) {
    if (!projectId) return;
    try {
      const result = await api.export(projectId, format, includeUnapproved);
      await loadProjectData();
      setNotice(`Created ${format.toUpperCase()} export with ${result.record_count} record(s). ${result.approval_state}.`);
    } catch (reason) { notifyError(reason); }
  }

  async function askAssistant(event: React.FormEvent) {
    event.preventDefault();
    try { setAssistantResult(await api.ask(assistantQuestion, projectId || undefined)); }
    catch (reason) { notifyError(reason); }
  }

  async function runSimulation() {
    if (!projectId) return;
    try { setSimulation(await api.prepareSimulation(projectId, videoId || undefined)); setNotice("Task representation prepared from saved annotations."); }
    catch (reason) { notifyError(reason); }
  }

  async function runRLExperiment(algorithm: "q_learning" | "baseline") {
    if (!projectId) return;
    setLoading(true);
    try {
      const result = await api.runRLExperiment(projectId, {
        algorithm,
        episodes: Number(rlForm.episodes),
        seed: Number(rlForm.seed),
        max_steps: 40,
      });
      setRlExperiments((current) => [result, ...current.filter((item) => item.id !== result.id)]);
      setNotice(`${algorithm === "q_learning" ? "Q-learning" : "Baseline"} run completed. Evaluation success: ${(result.metrics.evaluation.learned_policy.success_rate * 100).toFixed(0)}%.`);
    } catch (reason) { notifyError(reason); }
    finally { setLoading(false); }
  }

  const barDuration = Math.max(selectedVideo?.duration_seconds ?? 0, ...annotations.map((item) => item.end_time), 1);

  if (authenticated === null) {
    return <main className="login-shell"><div className="panel login-panel"><h1>AURA</h1><p>Checking your local session…</p></div></main>;
  }

  if (!authenticated) {
    return (
      <main className="login-shell">
        <form className="panel login-panel" onSubmit={signIn}>
          <div className="brand"><div className="brand-mark">A</div><div><strong>AURA</strong><small>ROBOTICS DATA WORKSPACE</small></div></div>
          <h1>Sign in to your workspace</h1>
          <p>Use a Django account provisioned for this local installation.</p>
          {error && <div className="alert error" role="alert">{error}</div>}
          <Field label="Username"><input autoComplete="username" required value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} /></Field>
          <Field label="Password"><input type="password" autoComplete="current-password" required value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} /></Field>
          <button className="button primary" type="submit">Sign in</button>
        </form>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">A</div><div><strong>AURA</strong><small>ROBOTICS DATA WORKSPACE</small></div></div>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {pages.map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${page === name ? "active" : ""}`} onClick={() => { setPage(name); setError(""); }}><Icon size={17} strokeWidth={1.8} /><span>{name}</span>{page === name && <ChevronRight size={15} />}</button>)}
        </nav>
        <div className="sidebar-foot"><span className="online-dot" /> Signed in as {user?.username}<small>{user?.roles.join(", ") || "No assigned role"}</small><button className="text-button" onClick={signOut}><LogOut size={14} /> Sign out</button></div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div><span className="eyebrow">AURA / {page.toUpperCase()}</span><h1>{page}</h1></div>
          <div className="top-actions">
            <label className="project-picker"><span>Project</span><select aria-label="Selected project" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select project</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <button className="icon-button" onClick={refresh} aria-label="Refresh workspace" title="Refresh"><RefreshCw size={17} /></button>
          </div>
        </header>
        <div className="content">
          {error && <div className="alert error" role="alert"><CircleHelp size={18} /><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
          {notice && <div className="alert success" role="status"><CheckCircle2 size={18} /><span>{notice}</span><button onClick={() => setNotice("")}>Dismiss</button></div>}
          {loading && <div className="loading-line"><LoaderCircle size={16} className="spin" /> Loading workspace data…</div>}
          {page === "Overview" && <section>
            <div className="welcome-row"><div><h2>Robotics demonstration data, under control.</h2><p>Prepare, annotate, validate, and review video datasets with traceable decisions.</p></div><button className="button primary" onClick={() => setPage("Projects")}><Plus size={16} /> New project</button></div>
            <div className="metric-grid">
              <Metric label="Projects" value={projects.length} icon={FolderKanban} hint="Stored locally" />
              <Metric label="Videos" value={videos.length} icon={FileVideo2} hint={project ? `In ${project.name}` : "Select a project"} />
              <Metric label="Annotations" value={quality?.annotation_count ?? 0} icon={Activity} hint="Persisted records" />
              <Metric label="Needs review" value={quality?.pending_review_count ?? 0} icon={ClipboardCheck} hint="Draft + needs review" />
            </div>
            <div className="panel-grid">
              <div className="panel"><PanelTitle title="Latest validation" caption="Deterministic policy checks" icon={ShieldCheck} />
                {quality?.latest_validation ? <div className="validation-overview"><StatusBadge value={quality.latest_validation.status} /><strong>{quality.latest_validation.error_count} errors</strong><span>{quality.latest_validation.warning_count} warnings</span><small>{readableDate(quality.latest_validation.created_at)}</small><button className="text-button" onClick={() => setPage("Dataset Quality")}>View findings <ChevronRight size={14} /></button></div> : <EmptyState title="No validation run yet" message="Run a project validation to create a factual quality snapshot." action="Validate data" onClick={validateProject} disabled={!projectId} />}
              </div>
              <div className="panel"><PanelTitle title="Recent activity" caption="Append-only local audit history" icon={History} />
                {audit.length ? <div className="activity-list">{audit.slice(0, 5).map((item) => <div className="activity-row" key={item.id}><span className="activity-dot" /><div><strong>{item.event_type}</strong><p>{item.summary}</p><small>{readableDate(item.created_at)} · {item.actor}</small></div></div>)}</div> : <EmptyState title="No activity recorded" message="Project edits, validation, review decisions, and exports appear here." />}
              </div>
            </div>
            <div className="notice-card"><Sparkles size={18} /><div><strong>Local-first by design</strong><p>Core annotation and validation work without cloud credentials or model downloads. AURA labels video segments; it does not generate robot control trajectories.</p></div><button className="text-button" onClick={() => setPage("Policy & Guidelines")}>Read policy</button></div>
          </section>}

          {page === "Projects" && <section>
            <div className="section-heading"><div><h2>Projects</h2><p>Organize tasks, videos, and annotation review.</p></div><button className="button secondary" onClick={loadSyntheticDemo}><Sparkles size={15} /> Load synthetic demo</button></div>
            <div className="panel create-panel"><PanelTitle title={editingProjectId ? "Edit project" : "Create a project"} caption="Project data persists in the local SQLite database" icon={Plus} />
              <form className="form-grid project-form" onSubmit={createProject}>
                <Field label="Project name"><input required maxLength={120} placeholder="Bottle Pick-and-Place Demonstration" value={projectForm.name} onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })} /></Field>
                <Field label="Task type"><select value={projectForm.task_type} onChange={(e) => setProjectForm({ ...projectForm, task_type: e.target.value })}><option value="pick_and_place">Pick and place</option><option value="inspection">Inspection</option><option value="other">Other</option></select></Field>
                <Field label="Description" className="wide"><input maxLength={4000} placeholder="Purpose, setup, or collection notes" value={projectForm.description} onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })} /></Field>
                <button className="button primary align-end" type="submit"><Plus size={16} /> {editingProjectId ? "Save project" : "Create project"}</button>
              </form>
            </div>
            <div className="project-grid">{projects.map((item) => <article className={`project-card ${projectId === item.id ? "selected" : ""}`} key={item.id}>
              <div className="project-card-top"><div className="project-icon"><FolderKanban size={19} /></div><StatusBadge value={item.status} /></div><h3>{item.name}</h3><p>{item.description || "No project description."}</p>
              <div className="project-stats"><span><FileVideo2 size={15} /> {item.video_count ?? 0} videos</span><span><Activity size={15} /> {item.annotation_count ?? 0} segments</span></div>
              <div className="project-card-foot"><small>Created {readableDate(item.created_at)}</small><div><button className="mini-button" onClick={() => { setEditingProjectId(item.id); setProjectForm({ name: item.name, description: item.description, task_type: item.task_type }); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Edit</button>{item.status === "active" && <button className="mini-button danger-text" onClick={() => archiveProject(item)}>Archive</button>}<button className="text-button" onClick={() => { setProjectId(item.id); setPage("Annotation Workspace"); }}>Open <ChevronRight size={14} /></button></div></div>
            </article>)}
              {!projects.length && <EmptyState title="Create the first project" message="Your local workspace is empty. Start with a project, then register or upload a demonstration video." />}
            </div>
          </section>}

          {page === "Annotation Workspace" && <section>
            <div className="section-heading"><div><h2>Annotation workspace</h2><p>Time-aligned action segments saved to the selected project.</p></div>{project && <span className="context-chip"><FolderKanban size={14} /> {project.name}</span>}</div>
            {!project ? <EmptyState title="Select a project" message="Choose a project from the header or create one to start annotating." action="View projects" onClick={() => setPage("Projects")} /> : <>
              <div className="panel media-panel">
                <div className="video-controls"><label className="field"><span>Video asset</span><select value={videoId} onChange={(e) => setVideoId(e.target.value)}><option value="">Choose video</option>{videos.map((item) => <option key={item.id} value={item.id}>{item.original_filename}</option>)}</select></label><label className="upload-button button secondary"><Upload size={15} /> Upload video<input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/avi" onChange={uploadVideo} /></label><label className={`upload-button button secondary ${!videoId ? "disabled" : ""}`}><Activity size={15} /> Import CSV/JSON<input type="file" accept=".csv,.json,text/csv,application/json" disabled={!videoId} onChange={importAnnotations} /></label></div>
                {selectedVideo?.managed ? <div className="video-player-wrap"><video ref={videoElement} controls src={`/api/v1/videos/${selectedVideo.id}/stream`} onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)} onClick={(e) => setCurrentTime(e.currentTarget.currentTime)} /><span className="media-meta">{selectedVideo.width ?? "?"}×{selectedVideo.height ?? "?"} · {selectedVideo.duration_seconds ? `${selectedVideo.duration_seconds.toFixed(2)}s` : "duration unavailable"}</span></div> :
                  <div className="no-video"><FileVideo2 size={24} /><strong>{selectedVideo ? "Metadata-only video registration" : "No video selected"}</strong><span>{selectedVideo ? "Playback is unavailable because no managed file was uploaded. Annotations can still be created using known timestamps." : "Upload a managed video or register external metadata to begin."}</span></div>}
                <form className="register-form" onSubmit={registerVideo}><strong>Register video metadata</strong><Field label="Filename"><input required maxLength={255} placeholder="demonstration.mp4" value={videoForm.original_filename} onChange={(e) => setVideoForm({ ...videoForm, original_filename: e.target.value })} /></Field><Field label="Duration (seconds)"><input type="number" min="0.01" step="any" placeholder="Optional" value={videoForm.duration_seconds} onChange={(e) => setVideoForm({ ...videoForm, duration_seconds: e.target.value })} /></Field><button className="button secondary" type="submit">Register</button></form>
              </div>
              {selectedVideo && <>
                <div className="panel timeline-panel"><PanelTitle title="Action timeline" caption={`Half-open intervals · ${barDuration.toFixed(1)} second display scale`} icon={Clock3} />
                  <div className="timeline-axis"><span>0s</span><span>{(barDuration / 2).toFixed(1)}s</span><span>{barDuration.toFixed(1)}s</span></div>
                  <div className="timeline-track">{annotations.map((item, index) => <button key={item.id} className={`timeline-segment tone-${index % 6}`} style={{ left: `${Math.max(0, item.start_time / barDuration * 100)}%`, width: `${Math.max(1, (item.end_time - item.start_time) / barDuration * 100)}%` }} title={`${item.action_label}: ${item.start_time}s–${item.end_time}s`} onClick={() => editAnnotation(item)}><span>{item.action_label}</span></button>)}</div>
                  {!annotations.length && <p className="muted">Saved annotations will appear on this timeline.</p>}
                </div>
                <div className="workspace-grid">
                  <div className="panel annotation-table-panel"><PanelTitle title="Annotations" caption={`${annotations.length} saved segment(s)`} icon={Activity} />
                    {annotations.length ? <div className="table-scroll"><table><thead><tr><th>Interval</th><th>Action</th><th>Object</th><th>Source / status</th><th></th></tr></thead><tbody>{annotations.map((item) => <tr key={item.id} onClick={() => editAnnotation(item)}><td>{item.start_time.toFixed(2)}–{item.end_time.toFixed(2)}s</td><td><strong>{item.action_label}</strong></td><td>{item.object_label || "—"}</td><td><span className="source-label">{item.source.replace("_", " ")}</span><StatusBadge value={item.status} /></td><td><button className="mini-button danger-text" aria-label={`Delete ${item.action_label}`} onClick={(e) => { e.stopPropagation(); removeAnnotation(item.id); }}>Delete</button></td></tr>)}</tbody></table></div> : <div className="inline-empty">No annotations yet. Add a segment using the form.</div>}
                  </div>
                  <div className="panel"><PanelTitle title={editingId ? "Edit segment" : "New segment"} caption="All new annotations remain drafts" icon={editingId ? Save : Plus} />
                    <form className="stack-form" onSubmit={saveAnnotation}>
                      <div className="two-col"><Field label="Start (seconds)"><input required type="number" min="0" step="any" value={annotationForm.start_time} onChange={(e) => setAnnotationForm({ ...annotationForm, start_time: e.target.value })} /></Field><Field label="End (seconds)"><input required type="number" min="0" step="any" value={annotationForm.end_time} onChange={(e) => setAnnotationForm({ ...annotationForm, end_time: e.target.value })} /></Field></div>
                      {selectedVideo.managed && <div className="mark-time-row"><span>Player time: {currentTime.toFixed(2)}s</span><button type="button" className="mini-button" onClick={() => setAnnotationForm({ ...annotationForm, start_time: currentTime.toFixed(2) })}>Set start</button><button type="button" className="mini-button" onClick={() => setAnnotationForm({ ...annotationForm, end_time: currentTime.toFixed(2) })}>Set end</button></div>}
                      <Field label="Action label"><select value={annotationForm.action_label} onChange={(e) => setAnnotationForm({ ...annotationForm, action_label: e.target.value })}>{labels.map((label) => <option key={label}>{label}</option>)}</select></Field>
                      <div className="two-col"><Field label="Object"><input maxLength={120} placeholder="e.g. water_bottle" value={annotationForm.object_label} onChange={(e) => setAnnotationForm({ ...annotationForm, object_label: e.target.value })} /></Field><Field label="Actor ID"><input maxLength={120} value={annotationForm.actor_id} onChange={(e) => setAnnotationForm({ ...annotationForm, actor_id: e.target.value })} /></Field></div>
                      <Field label="Notes"><textarea rows={3} maxLength={4000} value={annotationForm.notes} onChange={(e) => setAnnotationForm({ ...annotationForm, notes: e.target.value })} /></Field>
                      <div className="button-row"><button className="button primary" type="submit"><Save size={15} /> {editingId ? "Save changes" : "Add draft"}</button>{editingId && <button className="button secondary" type="button" onClick={() => { setEditingId(""); setAnnotationForm({ start_time: "0", end_time: "1", action_label: "approach", object_label: "", actor_id: "human_1", notes: "" }); }}>Cancel edit</button>}</div>
                    </form>
                  </div>
                </div>
              </>}
              <div className="footnote"><ShieldCheck size={15} /> Human-created, imported, synthetic, and model-suggested records retain provenance. Suggestions are never approved automatically.</div>
            </>}
          </section>}

          {page === "Dataset Quality" && <section>
            <div className="section-heading"><div><h2>Dataset quality & review</h2><p>Validation findings are deterministic snapshots; edits do not rewrite prior runs.</p></div><button className="button primary" disabled={!projectId} onClick={validateProject}><ClipboardCheck size={16} /> Run validation</button></div>
            {!project ? <EmptyState title="Select a project" message="Select a project to view quality metrics and review eligibility." /> : <>
              <div className="metric-grid quality-metrics"><Metric label="Annotations" value={quality?.annotation_count ?? 0} icon={Activity} hint="Current project records" /><Metric label="Valid records" value={quality?.latest_validation ? `${quality.latest_validation.valid_records}/${quality.latest_validation.total_records}` : "Not run"} icon={CheckCircle2} hint="Latest validation snapshot" /><Metric label="Errors" value={quality?.latest_validation?.error_count ?? 0} icon={CircleHelp} hint="Hard validation findings" /><Metric label="Warnings" value={quality?.latest_validation?.warning_count ?? 0} icon={Activity} hint="Human review recommended" /></div>
              {quality?.latest_validation ? <div className="panel findings-panel"><div className="finding-header"><PanelTitle title="Latest validation run" caption={`Policy v${quality.latest_validation.policy_version} · ${readableDate(quality.latest_validation.created_at)}`} icon={ShieldCheck} /><StatusBadge value={quality.latest_validation.status} /></div>
                {quality.latest_validation.issues.length ? <div className="issue-list">{quality.latest_validation.issues.map((issue: any, index: number) => <div className={`issue-row ${issue.severity}`} key={`${issue.code}-${issue.record_id ?? issue.source_row}-${index}`}><div className="issue-severity">{issue.severity}</div><div><strong>{issue.code}</strong><p>{issue.message}</p><small>{issue.record_id ? `Record ${issue.record_id}` : issue.source_row ? `Source row ${issue.source_row}` : "Dataset-level finding"} · {issue.field ?? "dataset"}</small></div></div>)}</div> : <div className="clean-state"><CheckCircle2 size={20} /><span>No findings in this validation snapshot.</span></div>}
              </div> : <EmptyState title="Validation has not run" message="Run deterministic checks against the currently persisted annotation records." action="Validate now" onClick={validateProject} />}
              <div className="panel quality-bottom"><div><PanelTitle title="Label distribution" caption="Counts from saved annotations" icon={Activity} />{Object.entries(quality?.counts_by_label ?? {}).map(([label, count]) => <div className="distribution-row" key={label}><span>{label}</span><div className="distribution-track"><i style={{ width: `${Math.max(2, (Number(count) / Math.max(1, quality.annotation_count)) * 100)}%` }} /></div><strong>{count as number}</strong></div>)}</div>
                <div><PanelTitle title="Review & exports" caption="Approvals are explicit and audited" icon={CheckCircle2} /><p className="muted">Submit drafts before review. Validation errors block approval; exports are immutable, versioned releases.</p><div className="button-wrap">
                  {canAnnotate && <button className="button secondary" disabled={!projectId} onClick={async () => { try { const result = await api.submitForReview(projectId); await Promise.all([loadProjectData(), loadAnnotations()]); setNotice(`Submitted ${result.submitted_count} annotation(s) for review.`); } catch (reason) { notifyError(reason); } }}>Submit drafts for review</button>}
                  {canReview && <button className="button secondary" disabled={!projectId} onClick={async () => { try { await api.review(projectId, "approved"); await loadProjectData(); setNotice("Project annotations approved."); } catch (reason) { notifyError(reason); } }}>Approve project</button>}
                  {canExport && <><button className="button secondary" disabled={!projectId} onClick={() => createExport("csv")}>Export approved CSV</button><button className="button secondary" disabled={!projectId} onClick={() => createExport("json")}>Export approved JSON</button><button className="button warning" disabled={!projectId} onClick={() => createExport("json", true)}>Include unapproved data…</button></>}
                </div></div>
              </div>
              {exports.length > 0 && <div className="panel"><PanelTitle title="Export lineage" caption="Manifest includes validation reference and SHA-256" icon={Download} /><div className="table-scroll"><table><thead><tr><th>File</th><th>Records</th><th>State</th><th>Created</th><th></th></tr></thead><tbody>{exports.map((item) => <tr key={item.id}><td>{item.filename}</td><td>{item.record_count}</td><td>{item.approval_state}</td><td>{readableDate(item.created_at)}</td><td>{canExport && <a className="text-button" href={`/api/v1/exports/${item.id}/download`} download><Download size={14} /> Download</a>}</td></tr>)}</tbody></table></div></div>}
            </>}
          </section>}

          {page === "AI Assistant" && <section>
            <div className="section-heading"><div><h2>AURA assistant</h2><p>Deterministic responses grounded in local policy and project facts.</p></div><span className="mode-chip"><span className="online-dot" /> Deterministic mode</span></div>
            <div className="assistant-layout"><div className="panel assistant-chat"><PanelTitle title="Ask about your dataset" caption="No video bytes or complete datasets are sent to a provider" icon={Bot} />
                <div className="assistant-welcome"><div className="assistant-avatar"><Bot size={20} /></div><div><strong>Local policy and data helper</strong><p>Ask why validation failed, how a label is defined, which records overlap, or what the project summary contains. Unsupported questions receive an explicit limitation.</p></div></div>
                {assistantResult && <div className="assistant-answer"><div className="answer-heading"><Sparkles size={15} /> Answer · {assistantResult.mode}</div><p>{assistantResult.answer}</p>{assistantResult.evidence?.length > 0 && <div className="evidence-box"><strong>Evidence</strong>{assistantResult.evidence.map((item: any, index: number) => <div key={index}><span>{item.title ?? item.type}</span><small>{item.source ?? `Run ${item.run_id ?? ""}`} · {item.policy_version ?? item.status ?? ""}</small></div>)}</div>}<div className="tool-summary">Tools: {assistantResult.tool_calls?.map((item: any) => item.tool).join(", ") || "none"}</div></div>}
                <form className="assistant-input" onSubmit={askAssistant}><textarea required rows={3} placeholder="e.g. Why did the latest validation fail?" value={assistantQuestion} onChange={(e) => setAssistantQuestion(e.target.value)} /><button className="button primary" type="submit"><Sparkles size={16} /> Ask AURA</button></form>
              </div>
              <aside className="panel supported-panel"><PanelTitle title="Supported questions" caption="Evidence-backed capabilities" icon={CircleHelp} /><ul><li>What validation findings exist?</li><li>How many annotations per action?</li><li>What does the policy say about overlaps?</li><li>What is the project summary?</li></ul><div className="limitation-callout">No LLM provider is connected in this implementation. This assistant will not guess about visual content or fabricate records.</div></aside>
            </div>
          </section>}

          {page === "Video & Document Chat" && <KnowledgeWorkspace projectId={projectId} videos={videos} initialVideoId={videoId} />}

          {page === "Simulation" && <section>
            <div className="section-heading"><div><h2>Task-level simulation</h2><p>Phases are mapped directly from saved annotation intervals.</p></div><button className="button primary" disabled={!projectId} onClick={runSimulation}><Boxes size={16} /> Prepare from annotations</button></div>
            {!project ? <EmptyState title="Select a project" message="Choose a project to prepare its annotation-derived task sequence." /> : <>
              <div className="simulation-banner"><Boxes size={20} /><div><strong>Scripted task visualization</strong><p>This is not a physical robot simulation. No geometry, trajectories, camera calibration, forces, or collision planning are modeled.</p></div></div>
              {simulation ? <SimulationView simulation={simulation} onStart={async () => { try { setSimulation(await api.simulation(simulation.id, "start")); } catch (reason) { notifyError(reason); } }} onReset={async () => { try { setSimulation(await api.simulation(simulation.id, "reset")); } catch (reason) { notifyError(reason); } }} /> : <div className="panel simulation-empty"><Boxes size={30} /><h3>No run prepared</h3><p>Prepare a run to create a versioned task representation from the selected video's actual annotations.</p></div>}
              <div className="panel rl-panel">
                <PanelTitle title="Reinforcement-learning lab" caption={`${rlEnvironment?.environment_version ?? "Grid world"} · local tabular Q-learning`} icon={BrainCircuit} />
                <p className="muted">The 3×3 environment starts with the gripper at cell {rlEnvironment?.start_cell ?? 0}, an object at cell {rlEnvironment?.object_cell ?? 2}, and a goal at cell {rlEnvironment?.goal_cell ?? 8}. Actions: {rlEnvironment?.actions.join(", ") ?? "loading"}.</p>
                <p className="rl-boundary">Training learns from environment rewards and next states—not from annotation labels. This is a deterministic task abstraction, not physics, safe motion planning, or a physical robot policy.</p>
                {canRunExperiment ? <form className="form-grid rl-controls" onSubmit={(event) => { event.preventDefault(); void runRLExperiment("q_learning"); }}>
                  <Field label="Training episodes"><input type="number" min={1} max={2000} required value={rlForm.episodes} onChange={(event) => setRlForm({ ...rlForm, episodes: event.target.value })} /></Field>
                  <Field label="Random seed"><input type="number" min={0} max={4294967295} required value={rlForm.seed} onChange={(event) => setRlForm({ ...rlForm, seed: event.target.value })} /></Field>
                  <button className="button primary align-end" type="submit" disabled={!projectId || loading}><Play size={15} /> Train Q-learning</button>
                  <button className="button secondary align-end" type="button" disabled={!projectId || loading} onClick={() => void runRLExperiment("baseline")}><TrendingUp size={15} /> Evaluate baseline</button>
                </form> : <p className="muted">Assign the ML Engineer, Project Manager, or Administrator role to start experiments.</p>}
                {rlExperiments.length > 0 ? <div className="rl-results">
                  <div className="rl-latest"><strong>Latest persisted run</strong><span>{rlExperiments[0].algorithm.replace("_", " ")} · seed {rlExperiments[0].random_seed} · {rlExperiments[0].configuration.episodes} episodes · {readableDate(rlExperiments[0].created_at)}</span></div>
                  <div className="metric-grid rl-metrics">
                    <Metric label="Learned policy success" value={`${(rlExperiments[0].metrics.evaluation.learned_policy.success_rate * 100).toFixed(0)}%`} icon={CheckCircle2} hint="Separate fixed-seed evaluation" />
                    <Metric label="Baseline success" value={`${(rlExperiments[0].metrics.evaluation.baseline_policy.success_rate * 100).toFixed(0)}%`} icon={TrendingUp} hint="Shortest-path rule policy" />
                    <Metric label="Learned mean steps" value={rlExperiments[0].metrics.evaluation.learned_policy.mean_steps} icon={Activity} hint="Across evaluation episodes" />
                    <Metric label="Training success" value={rlExperiments[0].metrics.training.success_rate === null ? "Baseline" : `${(rlExperiments[0].metrics.training.success_rate * 100).toFixed(0)}%`} icon={BrainCircuit} hint="Training episodes only" />
                  </div>
                  {rlExperiments[0].metrics.training.learning_curve.length > 1 && <div className="rl-curve"><strong>Training trend (20-episode rolling summary)</strong><div className="rl-curve-bars" role="img" aria-label="Q-learning training success rate by episode">{rlExperiments[0].metrics.training.learning_curve.map((point) => <span key={point.episode} title={`Episode ${point.episode}: ${(point.success_rate * 100).toFixed(0)}% success`} style={{ height: `${Math.max(3, point.success_rate * 100)}%` }} />)}</div><small>Bars show training success rate; evaluation uses a separate fixed seed set.</small></div>}
                  <div className="rl-run-list"><strong>Recent experiments</strong>{rlExperiments.slice(0, 5).map((run) => <div key={run.id}><span>{run.algorithm.replace("_", " ")} · {run.status} · seed {run.random_seed}</span><small>{readableDate(run.created_at)} · {run.environment_version}</small></div>)}</div>
                </div> : <EmptyState title="No learning run yet" message="Train a bounded tabular policy or evaluate the deterministic baseline. Run metrics and the Q-table are persisted by the backend." />}
              </div>
            </>}
          </section>}

          {page === "Policy & Guidelines" && <section>
            <div className="section-heading"><div><h2>Policy & guidelines</h2><p>Canonical annotation guidance used by the validator and local retrieval.</p></div><span className="context-chip">Active · v{policy?.version ?? "1.0"}</span></div>
            <div className="panel policy-panel"><div className="policy-toolbar"><div><h3>{policy?.title ?? "AURA Annotation Policy"}</h3><small>Canonical source: {policy?.source}</small></div><form onSubmit={async (e) => { e.preventDefault(); try { const result = await api.policySearch(policyQuery); setPolicyResults(result.results); } catch (reason) { notifyError(reason); } }}><input placeholder="Search policy…" value={policyQuery} onChange={(e) => setPolicyQuery(e.target.value)} /><button className="button secondary" type="submit">Search</button></form></div>
              {policyResults.length > 0 && <div className="policy-results">{policyResults.map((item: any, index) => <div key={index}><strong>{item.title}</strong><p>{item.excerpt}</p><small>{item.source} · v{item.policy_version}</small></div>)}</div>}
              <pre className="policy-content">{policy?.content ?? "Policy could not be loaded."}</pre>
            </div>
          </section>}

          {page === "Audit Trail" && <section>
            <div className="section-heading"><div><h2>Audit trail</h2><p>Consequential local actions, ordered newest first.</p></div></div>
            {!project ? <EmptyState title="Select a project" message="Project-specific audit events appear after selecting a project." /> : audit.length ? <div className="panel audit-panel">{audit.map((item) => <div className="audit-row" key={item.id}><div className="audit-icon"><History size={16} /></div><div className="audit-main"><div><strong>{item.summary}</strong><span className="audit-type">{item.event_type}</span></div><small>{readableDate(item.created_at)} · {item.actor}</small></div></div>)}</div> : <div className="panel"><EmptyState title="No events yet" message="Project creation, annotation edits, validation, review, assistant use, and exports are recorded here." /></div>}
          </section>}

          {page === "Settings" && <section>
            <div className="section-heading"><div><h2>Capabilities & local settings</h2><p>Capability status only. Secret values are never returned to the browser.</p></div></div>
            <div className="settings-grid">
              <div className="panel"><PanelTitle title="Runtime capabilities" caption="Reported by the local API" icon={Settings2} /><SettingRow title="Database" value={capabilities?.database ?? "Loading"} detail="Persistent workspace storage" /><SettingRow title="Assistant" value={capabilities?.assistant?.mode ?? "Loading"} detail="No LLM provider adapter is included" /><SettingRow title="OpenCV metadata" value={capabilities?.vision?.metadata_extraction ? "Available" : "Unavailable"} detail="Optional dependency for video metadata and frame sampling" /><SettingRow title="Detector" value={capabilities?.vision?.detector_ready ? "Ready" : "Not available"} detail="No inference adapter; weights are never downloaded" /></div>
              <div className="panel"><PanelTitle title="Storage & trust boundaries" caption="Local demo configuration" icon={ShieldCheck} /><div className="settings-note"><p>Uploads are saved under <code>data/media/</code>. Exports and reports are stored under <code>output/</code>. Database defaults to <code>data/aura.db</code>.</p><p>Django sessions and server-side roles protect application writes. Account administration, rate limiting, and production hardening remain incomplete; do not expose this development server to untrusted networks.</p><p>AURA segments label video events; those labels are not robot joint commands or a safe physical control policy.</p></div></div>
            </div>
          </section>}
        </div>
        <footer className="footer"><span>AURA · Local-first annotation workspace</span><span>Data remains on this machine by default</span></footer>
      </main>
    </div>
  );
}

function Metric({ label, value, icon: Icon, hint }: { label: string; value: string | number; icon: typeof Activity; hint: string }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><Icon size={17} /></div><strong>{value}</strong><small>{hint}</small></div>;
}

function PanelTitle({ title, caption, icon: Icon }: { title: string; caption: string; icon: typeof Activity }) {
  return <div className="panel-title"><div className="panel-icon"><Icon size={16} /></div><div><h3>{title}</h3><p>{caption}</p></div></div>;
}

function StatusBadge({ value }: { value: string }) {
  const kind = value?.includes("failed") || value === "rejected" || value === "archived" ? "danger" : value?.includes("warning") || value === "needs_review" ? "warning" : value === "approved" || value === "passed" || value === "active" || value === "completed" ? "good" : "neutral";
  return <span className={`status-badge ${kind}`}>{(value || "unknown").replace(/_/g, " ")}</span>;
}

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return <label className={`field ${className}`}><span>{label}</span>{children}</label>;
}

function EmptyState({ title, message, action, onClick, disabled }: { title: string; message: string; action?: string; onClick?: () => void; disabled?: boolean }) {
  return <div className="empty-state"><div className="empty-icon"><Archive size={19} /></div><strong>{title}</strong><p>{message}</p>{action && <button className="button secondary" disabled={disabled} onClick={onClick}>{action}</button>}</div>;
}

function SimulationView({ simulation, onStart, onReset }: { simulation: any; onStart: () => void; onReset: () => void }) {
  const phases = simulation.task?.phases ?? [];
  const phaseActions = ["approach", "reach", "grasp", "lift", "move", "place", "release", "withdraw"];
  const present = new Set(phases.map((item: any) => item.action));
  return <div className="panel simulation-run"><div className="simulation-run-head"><div><span className="eyebrow">RUN {simulation.id.slice(0, 8).toUpperCase()}</span><h3>{simulation.task?.task_type?.replace(/_/g, " ")}</h3><p>{phases.length} annotation-derived phase(s) · object {simulation.task?.object_label ?? "unspecified"}</p></div><StatusBadge value={simulation.status} /></div>
    <div className="phase-rail">{phaseActions.map((action, index) => <div className={`phase-step ${present.has(action) ? "present" : "missing"} ${index < simulation.current_phase ? "done" : ""}`} key={action}><div className="phase-node">{present.has(action) ? <CheckCircle2 size={16} /> : <span>{index + 1}</span>}</div><strong>{action}</strong><small>{present.has(action) ? `${phases.filter((item: any) => item.action === action).length} segment(s)` : "Missing"}</small></div>)}</div>
    {phases.some((item: any) => !phaseActions.includes(item.action)) && <div className="issue-row warning"><div className="issue-severity">UNMAPPED</div><div><strong>Unmapped action labels</strong><p>{phases.filter((item: any) => !phaseActions.includes(item.action)).map((item: any) => item.action).join(", ")}</p></div></div>}
    <div className="simulation-object"><div className={`object-cube ${simulation.status === "completed" ? "placed" : ""}`} /><div className="object-caption"><strong>{simulation.task?.object_label ?? "Unspecified object"}</strong><span>Task-state illustration · no geometry or motion capture</span></div></div>
    <div className="simulation-actions"><button className="button primary" disabled={simulation.status === "completed"} onClick={onStart}><Activity size={15} /> {simulation.current_phase ? "Advance phase" : "Start scripted run"}</button><button className="button secondary" onClick={onReset}><RotateCcw size={15} /> Reset</button><span>{simulation.current_phase}/{phases.length} phases complete</span></div>
    <div className="limitation-callout">{simulation.task?.limitations?.join(" ")}</div>
  </div>;
}

function SettingRow({ title, value, detail }: { title: string; value: string; detail: string }) {
  return <div className="setting-row"><div><strong>{title}</strong><small>{detail}</small></div><span>{value}</span></div>;
}
