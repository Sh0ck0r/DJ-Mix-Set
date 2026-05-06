import { useEffect, useState, useCallback } from "react";
import { Navigate, Link } from "react-router-dom";
import { api, coverUrl, fmtTime } from "../lib/api";
import { Upload, Plus, Trash2, FileAudio, FileText, Image as ImageIcon, Loader2, CheckCircle2, Radar, Activity, AlertTriangle, Edit3, Settings } from "lucide-react";
import { toast } from "sonner";
import { BulkScan } from "../components/BulkScan";
import { MixEditModal } from "../components/MixEditModal";
import { AnalysisOverviewBar } from "../components/AnalysisOverviewBar";

const Field = ({ label, ...props }) => (
    <label className="block">
        <span className="label block mb-1.5">{label}</span>
        <input
            {...props}
            className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2 text-white font-mono text-sm"
        />
    </label>
);

const Drop = ({ label, accept, onFile, file, testid, hint }) => {
    const [drag, setDrag] = useState(false);
    return (
        <label
            data-testid={testid}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                if (e.dataTransfer.files?.[0]) onFile(e.dataTransfer.files[0]);
            }}
            className={`block border-2 border-dashed cursor-pointer p-4 transition-colors ${
                drag ? "border-neon-cyan bg-neon-cyan/5" : "border-[#1A1D2E] hover:border-neon-cyan/50"
            }`}
        >
            <input
                type="file"
                accept={accept}
                className="hidden"
                onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            />
            <div className="flex items-center gap-3">
                <Upload className="w-5 h-5 text-neon-cyan" />
                <div className="flex-1 min-w-0">
                    <div className="label">{label}</div>
                    {file ? (
                        <div className="font-mono text-xs text-neon-green truncate flex items-center gap-1.5 mt-0.5">
                            <CheckCircle2 className="w-3 h-3" /> {file.name}
                        </div>
                    ) : (
                        <div className="font-mono text-xs text-zinc-500 mt-0.5">{hint || "Drop or click to choose"}</div>
                    )}
                </div>
            </div>
        </label>
    );
};

export const AdminDashboard = () => {
    const token = localStorage.getItem("mixdeck_token");
    const [mixes, setMixes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [showScan, setShowScan] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            setMixes(await api.listMixes());
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    if (!token) return <Navigate to="/admin/login" replace />;

    return (
        <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-8 pb-32">
            <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
                <div>
                    <h1 className="font-display font-black text-2xl uppercase tracking-widest">
                        ADMIN <span className="text-neon-cyan">CONSOLE</span>
                    </h1>
                    <p className="label mt-1">// MANAGE YOUR DECK</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <Link
                        to="/admin/settings"
                        data-testid="link-admin-settings"
                        className="font-display font-bold tracking-widest uppercase px-3 py-2.5 transition-colors flex items-center gap-2 border bg-transparent text-zinc-400 border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan"
                        title="App settings (LLM endpoint, model)"
                    >
                        <Settings className="w-4 h-4" /> SETTINGS
                    </Link>
                    <button
                        onClick={() => { setShowScan((v) => !v); if (!showScan) setShowForm(false); }}
                        data-testid="toggle-bulk-scan"
                        className={`font-display font-bold tracking-widest uppercase px-4 py-2.5 transition-colors flex items-center gap-2 border ${
                            showScan
                                ? "bg-neon-cyan text-black border-neon-cyan shadow-[0_0_20px_rgba(0,240,255,0.3)]"
                                : "bg-transparent text-neon-cyan border-neon-cyan/40 hover:bg-neon-cyan/10"
                        }`}
                    >
                        <Radar className="w-4 h-4" /> {showScan ? "CLOSE SCAN" : "BULK SCAN"}
                    </button>
                    <button
                        onClick={() => { setShowForm((v) => !v); if (!showForm) setShowScan(false); }}
                        data-testid="toggle-new-mix"
                        className={`font-display font-bold tracking-widest uppercase px-4 py-2.5 transition-colors flex items-center gap-2 border ${
                            showForm
                                ? "bg-neon-cyan text-black border-neon-cyan shadow-[0_0_20px_rgba(0,240,255,0.3)]"
                                : "bg-transparent text-neon-cyan border-neon-cyan/40 hover:bg-neon-cyan/10"
                        }`}
                    >
                        <Plus className="w-4 h-4" /> {showForm ? "CLOSE" : "NEW MIX"}
                    </button>
                </div>
            </div>

            <AnalysisOverviewBar onChanged={load} />

            {showScan && <BulkScan onScanned={load} />}
            {showForm && <NewMixForm onCreated={() => { setShowForm(false); load(); }} />}

            <h2 className="font-display font-bold text-sm uppercase tracking-widest mt-10 mb-3 text-zinc-400">
                Existing Mixes <span className="text-neon-cyan">{mixes.length}</span>
            </h2>
            {loading ? (
                <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 text-neon-cyan animate-spin" /></div>
            ) : mixes.length === 0 ? (
                <div className="border border-dashed border-[#1A1D2E] p-8 text-center label">NO MIXES YET</div>
            ) : (
                <div className="space-y-2" data-testid="admin-mix-list">
                    {mixes.map((m) => (
                        <AdminMixRow key={m.id} mix={m} onChanged={load} />
                    ))}
                </div>
            )}
        </div>
    );
};

const NewMixForm = ({ onCreated }) => {
    const [meta, setMeta] = useState({ title: "", artist: "", genre: "", bpm: "", description: "" });
    const [audio, setAudio] = useState(null);
    const [cover, setCover] = useState(null);
    const [cue, setCue] = useState(null);
    const [busy, setBusy] = useState(false);
    const [progress, setProgress] = useState(0);

    const set = (k) => (e) => setMeta({ ...meta, [k]: e.target.value });

    const submit = async (e) => {
        e.preventDefault();
        if (!meta.title) {
            toast.error("Title required");
            return;
        }
        setBusy(true);
        try {
            const created = await api.createMix({
                title: meta.title,
                artist: meta.artist,
                genre: meta.genre,
                bpm: meta.bpm ? parseInt(meta.bpm, 10) : null,
                description: meta.description,
            });
            if (audio) await api.uploadAudio(created.id, audio, setProgress);
            if (cover) await api.uploadCover(created.id, cover);
            if (cue) await api.uploadCue(created.id, cue);
            toast.success("MIX UPLOADED");
            onCreated?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Upload failed");
        } finally {
            setBusy(false);
            setProgress(0);
        }
    };

    return (
        <form
            onSubmit={submit}
            data-testid="new-mix-form"
            className="border border-[#1A1D2E] bg-[#0a0c14] p-5 md:p-6 space-y-4 scanlines relative"
        >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="TITLE *" value={meta.title} onChange={set("title")} data-testid="title-input" />
                <Field label="DJ / ARTIST" value={meta.artist} onChange={set("artist")} data-testid="artist-input" />
                <Field label="GENRE" value={meta.genre} onChange={set("genre")} data-testid="genre-input" />
                <Field label="BPM" type="number" value={meta.bpm} onChange={set("bpm")} data-testid="bpm-input" />
            </div>
            <label className="block">
                <span className="label block mb-1.5">DESCRIPTION</span>
                <textarea
                    value={meta.description}
                    onChange={set("description")}
                    rows={3}
                    data-testid="description-input"
                    className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2 text-white font-mono text-sm"
                />
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Drop label="AUDIO FILE (.mp3 / .flac)" accept=".mp3,.flac,.wav,.m4a,.ogg,audio/*" file={audio} onFile={setAudio} testid="audio-drop" />
                <Drop label="CUE SHEET (.cue)" accept=".cue,text/*" file={cue} onFile={setCue} testid="cue-drop" hint="Standard CUE for tracklist" />
                <Drop label="COVER ART" accept="image/*" file={cover} onFile={setCover} testid="cover-drop" />
            </div>
            {busy && progress > 0 && (
                <div className="border border-[#1A1D2E]">
                    <div className="h-1.5 bg-neon-cyan transition-all" style={{ width: `${progress}%` }} />
                    <div className="px-2 py-1 label">UPLOADING AUDIO… {progress}%</div>
                </div>
            )}
            <button
                type="submit"
                disabled={busy}
                data-testid="submit-new-mix"
                className="w-full bg-neon-cyan text-black font-display font-black tracking-widest uppercase py-3 hover:bg-white transition-colors disabled:opacity-30 flex items-center justify-center gap-2"
            >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {busy ? "UPLOADING…" : "UPLOAD MIX"}
            </button>
        </form>
    );
};

const AdminMixRow = ({ mix, onChanged }) => {
    const [busy, setBusy] = useState(false);
    const [status, setStatus] = useState(mix.analysis_status || "none");
    const [editing, setEditing] = useState(false);
    const cover = coverUrl(mix);

    useEffect(() => {
        setStatus(mix.analysis_status || "none");
    }, [mix.analysis_status]);

    // Poll while running
    useEffect(() => {
        if (status !== "pending" && status !== "running") return;
        const iv = setInterval(async () => {
            try {
                const s = await api.analysisStatus(mix.id);
                setStatus(s.status);
                if (s.status === "done" || s.status === "failed") {
                    clearInterval(iv);
                    onChanged?.();
                }
            } catch {
                clearInterval(iv);
            }
        }, 2500);
        return () => clearInterval(iv);
    }, [status, mix.id, onChanged]);

    const onUpload = async (kind, file) => {
        if (!file) return;
        setBusy(true);
        try {
            if (kind === "audio") await api.uploadAudio(mix.id, file);
            if (kind === "cue") await api.uploadCue(mix.id, file);
            if (kind === "cover") await api.uploadCover(mix.id, file);
            toast.success(`${kind.toUpperCase()} UPDATED`);
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed");
        } finally {
            setBusy(false);
        }
    };

    const remove = async () => {
        if (!window.confirm(`Delete "${mix.title}"?`)) return;
        try {
            await api.deleteMix(mix.id);
            toast.success("DELETED");
            onChanged?.();
        } catch {
            toast.error("Delete failed");
        }
    };

    const analyze = async () => {
        try {
            await api.analyzeMix(mix.id);
            setStatus("pending");
            toast.message("ANALYSIS QUEUED", { description: "BPM + key detection running…" });
        } catch (err) {
            toast.error(err.response?.data?.detail || "Analyze failed");
        }
    };

    const trackCount = mix.tracks?.length || 0;
    const analyzedCount = (mix.tracks || []).filter((t) => t.bpm).length;

    return (
        <div className="border border-[#1A1D2E] p-3 flex items-center gap-4 hover:border-neon-cyan/40 transition-colors" data-testid="admin-mix-row">
            <div className="w-14 h-14 bg-black border border-[#1A1D2E] overflow-hidden shrink-0">
                {cover ? <img src={cover} alt={mix.title} className="w-full h-full object-cover" /> : <div className="w-full h-full grid-bg" />}
            </div>
            <div className="flex-1 min-w-0">
                <div className="font-display font-bold text-white truncate flex items-center gap-2">
                    {mix.title}
                    {mix.bpm ? (
                        <span className="label px-1.5 py-0.5 border border-neon-green/40 text-neon-green">{mix.bpm} BPM</span>
                    ) : null}
                    {mix.camelot ? (
                        <span className="label px-1.5 py-0.5 border border-neon-cyan/40 text-neon-cyan" title={mix.key || ""}>
                            {mix.camelot}
                        </span>
                    ) : null}
                </div>
                <div className="label truncate">
                    {mix.artist || "—"} • {mix.genre || "—"} • {trackCount} TRX
                    {analyzedCount > 0 && ` (${analyzedCount} ANALYZED)`}
                    {" "}• {fmtTime(mix.duration || 0)}
                </div>
            </div>
            <div className="flex items-center gap-1.5">
                <AnalysisBadge status={status} />
                <button
                    onClick={() => setEditing(true)}
                    data-testid="edit-mix-button"
                    className="w-9 h-9 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan text-zinc-400 flex items-center justify-center transition-colors"
                    title="Edit metadata"
                >
                    <Edit3 className="w-4 h-4" />
                </button>
                <button
                    onClick={analyze}
                    disabled={status === "pending" || status === "running"}
                    data-testid="analyze-mix-button"
                    className="w-9 h-9 border border-[#1A1D2E] hover:border-neon-green hover:text-neon-green text-zinc-400 flex items-center justify-center transition-colors disabled:opacity-40"
                    title="Analyze BPM + Key"
                >
                    {status === "running" || status === "pending" ? (
                        <Loader2 className="w-4 h-4 animate-spin text-neon-green" />
                    ) : (
                        <Activity className="w-4 h-4" />
                    )}
                </button>
                <UploadIcon icon={<FileAudio />} accept=".mp3,.flac,.wav,.m4a,.ogg,audio/*" onFile={(f) => onUpload("audio", f)} title="Replace audio" />
                <UploadIcon icon={<FileText />} accept=".cue,text/*" onFile={(f) => onUpload("cue", f)} title="Upload cue" />
                <UploadIcon icon={<ImageIcon />} accept="image/*" onFile={(f) => onUpload("cover", f)} title="Replace cover" />
                <button
                    onClick={remove}
                    disabled={busy}
                    data-testid="delete-mix-button"
                    className="w-9 h-9 border border-[#1A1D2E] hover:border-neon-red hover:text-neon-red text-zinc-400 flex items-center justify-center transition-colors"
                    title="Delete mix"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            </div>
            <MixEditModal
                mix={mix}
                open={editing}
                onClose={() => setEditing(false)}
                onSaved={onChanged}
            />
        </div>
    );
};

const AnalysisBadge = ({ status }) => {
    if (status === "done")
        return <span className="label px-2 py-1 border border-neon-green/40 text-neon-green flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> ANALYZED</span>;
    if (status === "running")
        return <span className="label px-2 py-1 border border-neon-cyan/40 text-neon-cyan flex items-center gap-1 animate-pulse"><Activity className="w-3 h-3" /> ANALYZING</span>;
    if (status === "pending")
        return <span className="label px-2 py-1 border border-neon-cyan/40 text-neon-cyan flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> QUEUED</span>;
    if (status === "failed")
        return <span className="label px-2 py-1 border border-neon-red/40 text-neon-red flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> FAILED</span>;
    return null;
};

const UploadIcon = ({ icon, accept, onFile, title }) => (
    <label
        title={title}
        className="w-9 h-9 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan text-zinc-400 flex items-center justify-center cursor-pointer transition-colors"
    >
        <input type="file" accept={accept} className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        <span className="[&_svg]:w-4 [&_svg]:h-4">{icon}</span>
    </label>
);
