import { useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Settings as SettingsIcon, ArrowLeft, CheckCircle2, AlertTriangle, Loader2, Server, Zap, Eye, EyeOff, Save } from "lucide-react";
import { BulkLLMRunner } from "../components/BulkLLMRunner";

const Field = ({ label, hint, children }) => (
    <label className="block">
        <span className="label block mb-1.5">{label}</span>
        {children}
        {hint ? <span className="font-mono text-[11px] text-zinc-500 block mt-1.5">{hint}</span> : null}
    </label>
);

const Input = ({ ...props }) => (
    <input
        {...props}
        className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2.5 text-white font-mono text-sm"
    />
);

export const AdminSettings = () => {
    const token = localStorage.getItem("mixdeck_token");
    const [settings, setSettings] = useState(null);
    const [form, setForm] = useState({
        llm_base_url: "",
        llm_api_key: "",
        llm_model: "",
        llm_enabled: true,
        whisper_base_url: "",
        whisper_api_key: "",
        whisper_model: "",
        whisper_enabled: false,
        whisper_language: "",
        whisper_transition_trim: 15,
    });
    const [showKey, setShowKey] = useState(false);
    const [showWhisperKey, setShowWhisperKey] = useState(false);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);
    const [testingWhisper, setTestingWhisper] = useState(false);
    const [whisperResult, setWhisperResult] = useState(null);

    useEffect(() => {
        api.getSettings().then((s) => {
            setSettings(s);
            setForm({
                llm_base_url: s.llm_base_url || "",
                llm_api_key: "",
                llm_model: s.llm_model || "",
                llm_enabled: !!s.llm_enabled,
                whisper_base_url: s.whisper_base_url || "",
                whisper_api_key: "",
                whisper_model: s.whisper_model || "",
                whisper_enabled: !!s.whisper_enabled,
                whisper_language: s.whisper_language || "",
                whisper_transition_trim: typeof s.whisper_transition_trim === "number" ? s.whisper_transition_trim : 15,
            });
        }).catch(() => toast.error("Failed to load settings"));
    }, []);

    if (!token) return <Navigate to="/admin/login" replace />;

    const runWhisperTest = async () => {
        setTestingWhisper(true);
        setWhisperResult(null);
        try {
            const res = await api.testWhisper();
            setWhisperResult(res);
            if (res.ok) {
                toast.success(`WHISPER REACHED · ${res.available_models?.length || 0} MODELS`, {
                    description: res.model_in_list === false
                        ? `WARNING: configured model "${res.configured_model}" not in available list`
                        : `Configured: ${res.configured_model} · lang: ${res.language}`,
                });
            } else {
                toast.error("WHISPER UNREACHABLE", { description: res.error });
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || "Test failed");
        } finally {
            setTestingWhisper(false);
        }
    };

    const set = (k) => (e) =>
        setForm({ ...form, [k]: e?.target?.type === "checkbox" ? e.target.checked : e.target.value });

    const save = async () => {
        setSaving(true);
        try {
            const patch = { ...form };
            if (!patch.llm_api_key) delete patch.llm_api_key; // empty -> keep existing
            if (!patch.whisper_api_key) delete patch.whisper_api_key;
            patch.whisper_transition_trim = parseInt(form.whisper_transition_trim, 10);
            if (!Number.isFinite(patch.whisper_transition_trim) || patch.whisper_transition_trim < 0) {
                patch.whisper_transition_trim = 15;
            }
            const updated = await api.updateSettings(patch);
            setSettings(updated);
            setForm((f) => ({ ...f, llm_api_key: "", whisper_api_key: "" }));
            toast.success("SETTINGS SAVED");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Save failed");
        } finally {
            setSaving(false);
        }
    };

    const runTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const res = await api.testLLM();
            setTestResult(res);
            if (res.ok) {
                toast.success(`LLM REACHED · ${res.available_models?.length || 0} MODELS`, {
                    description: res.model_in_list === false
                        ? `WARNING: configured model "${res.configured_model}" not in available list`
                        : `Configured: ${res.configured_model}`,
                });
            } else {
                toast.error("LLM UNREACHABLE", { description: res.error });
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || "Test failed");
        } finally {
            setTesting(false);
        }
    };

    if (!settings) {
        return (
            <div className="py-20 flex justify-center">
                <Loader2 className="w-6 h-6 text-neon-cyan animate-spin" />
            </div>
        );
    }

    return (
        <div className="max-w-3xl mx-auto px-4 md:px-8 py-8 pb-32" data-testid="admin-settings-page">
            <Link
                to="/admin"
                data-testid="back-to-admin"
                className="label inline-flex items-center gap-2 hover:text-neon-cyan mb-6"
            >
                <ArrowLeft className="w-3 h-3" /> BACK TO ADMIN
            </Link>
            <div className="mb-6">
                <h1 className="font-display font-black text-2xl uppercase tracking-widest flex items-center gap-3">
                    <SettingsIcon className="w-6 h-6 text-neon-cyan" />
                    APP <span className="text-neon-cyan">SETTINGS</span>
                </h1>
                <p className="label mt-1">// LLM ENDPOINT, MODEL, DEFAULTS</p>
            </div>

            <section className="border border-[#1A1D2E] bg-[#0a0c14] p-5 md:p-6 space-y-5 scanlines relative" data-testid="llm-settings-section">
                <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-neon-cyan" />
                    <span className="label text-neon-cyan">// LOCAL LLM ENDPOINT</span>
                    <span className="ml-auto label text-zinc-500">OpenAI-compatible · SGLang / Ollama / vLLM</span>
                </div>

                <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={form.llm_enabled}
                        onChange={set("llm_enabled")}
                        data-testid="llm-enabled-toggle"
                        className="w-4 h-4 accent-neon-cyan"
                    />
                    <span className="label">LLM ENABLED</span>
                    <span className="font-mono text-[11px] text-zinc-500 ml-2">Disable to hide AI features in the UI.</span>
                </label>

                <Field
                    label="BASE URL"
                    hint="e.g. http://localhost:30000/v1 (SGLang default), http://192.168.1.50:11434/v1 (Ollama on LAN). Must include /v1."
                >
                    <Input
                        value={form.llm_base_url}
                        onChange={set("llm_base_url")}
                        placeholder="http://localhost:30000/v1"
                        data-testid="llm-base-url-input"
                    />
                </Field>

                <Field
                    label="MODEL NAME"
                    hint="Whichever model is loaded on your server (e.g. llama3.2, mistral-7b, qwen2.5)."
                >
                    <Input
                        value={form.llm_model}
                        onChange={set("llm_model")}
                        placeholder="llama3.2"
                        data-testid="llm-model-input"
                    />
                </Field>

                <Field
                    label="API KEY (OPTIONAL)"
                    hint={settings.llm_api_key_set
                        ? "A key is currently set. Leave blank to keep it; type a new one to replace; set 'clear' below to remove."
                        : "Most local servers don't need a key. Leave blank for SGLang/Ollama."}
                >
                    <div className="relative">
                        <Input
                            type={showKey ? "text" : "password"}
                            value={form.llm_api_key}
                            onChange={set("llm_api_key")}
                            placeholder={settings.llm_api_key_set ? "•••••••• (unchanged)" : "(none)"}
                            data-testid="llm-api-key-input"
                        />
                        <button
                            type="button"
                            onClick={() => setShowKey((v) => !v)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-neon-cyan"
                            tabIndex={-1}
                        >
                            {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                </Field>

                <div className="flex flex-wrap items-center gap-3 pt-2">
                    <button
                        onClick={save}
                        disabled={saving}
                        data-testid="save-settings-button"
                        className="bg-neon-cyan text-black font-display font-black tracking-widest uppercase px-5 py-2.5 hover:bg-white transition-colors disabled:opacity-30 flex items-center gap-2 shadow-[0_0_20px_rgba(0,240,255,0.3)]"
                    >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        {saving ? "SAVING…" : "SAVE"}
                    </button>
                    <button
                        onClick={runTest}
                        disabled={testing || !settings.llm_enabled}
                        data-testid="test-llm-button"
                        className="bg-transparent text-neon-green font-display font-bold tracking-widest uppercase px-5 py-2.5 border border-neon-green/40 hover:bg-neon-green/10 transition-colors disabled:opacity-30 flex items-center gap-2"
                    >
                        {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                        TEST CONNECTION
                    </button>
                </div>

                {testResult && (
                    <div
                        data-testid="llm-test-result"
                        className={`mt-3 border p-3 ${testResult.ok ? "border-neon-green/40 bg-neon-green/5" : "border-neon-red/40 bg-neon-red/5"}`}
                    >
                        <div className="flex items-center gap-2 mb-1.5">
                            {testResult.ok ? (
                                <CheckCircle2 className="w-4 h-4 text-neon-green" />
                            ) : (
                                <AlertTriangle className="w-4 h-4 text-neon-red" />
                            )}
                            <span className={`label ${testResult.ok ? "text-neon-green" : "text-neon-red"}`}>
                                {testResult.ok ? "REACHABLE" : "UNREACHABLE"}
                            </span>
                        </div>
                        {testResult.ok ? (
                            <div className="font-mono text-xs text-zinc-300 space-y-1">
                                <div>BASE: <span className="text-neon-cyan">{testResult.base_url}</span></div>
                                <div>CONFIGURED MODEL: <span className="text-neon-cyan">{testResult.configured_model}</span>{testResult.model_in_list === false ? <span className="text-neon-red ml-2">⚠ NOT IN AVAILABLE LIST</span> : null}</div>
                                {testResult.available_models?.length > 0 && (
                                    <div>
                                        AVAILABLE: <span className="text-zinc-400">{testResult.available_models.slice(0, 8).join(", ")}{testResult.available_models.length > 8 ? "…" : ""}</span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="font-mono text-xs text-zinc-300">{testResult.error}</div>
                        )}
                    </div>
                )}
            </section>

            {/* ===== WHISPER SECTION ===== */}
            <section
                className="border border-[#1A1D2E] bg-[#0a0c14] p-5 md:p-6 space-y-5 mt-6 scanlines relative"
                data-testid="whisper-settings-section"
            >
                <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-neon-green" />
                    <span className="label text-neon-green">// LOCAL WHISPER ENDPOINT</span>
                    <span className="ml-auto label text-zinc-500">OpenAI-compatible · Speaches / faster-whisper / vLLM</span>
                </div>
                <p className="font-mono text-[11px] text-zinc-500 leading-relaxed">
                    When enabled, Whisper runs <span className="text-neon-cyan">automatically during track analysis</span>.
                    It smart-merges with LRCLIB lyrics (using LRCLIB text + Whisper timing for force-alignment).
                    For tracks not in LRCLIB, Whisper provides full text + timing. Single tracks can also be
                    re-transcribed on demand from the lyrics HUD.
                </p>

                <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={form.whisper_enabled}
                        onChange={set("whisper_enabled")}
                        data-testid="whisper-enabled-toggle"
                        className="w-4 h-4 accent-neon-green"
                    />
                    <span className="label">WHISPER ENABLED</span>
                    <span className="font-mono text-[11px] text-zinc-500 ml-2">Off by default - opt-in feature.</span>
                </label>

                <Field
                    label="BASE URL"
                    hint="e.g. http://localhost:8000/v1 (Speaches default), http://localhost:9000/v1 (faster-whisper-server). Must include /v1."
                >
                    <Input
                        value={form.whisper_base_url}
                        onChange={set("whisper_base_url")}
                        placeholder="http://localhost:8000/v1"
                        data-testid="whisper-base-url-input"
                    />
                </Field>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field
                        label="MODEL"
                        hint="e.g. Systran/faster-whisper-large-v3 (best quality), nvidia/parakeet-tdt-0.6b-v2 (fastest)."
                    >
                        <Input
                            value={form.whisper_model}
                            onChange={set("whisper_model")}
                            placeholder="Systran/faster-whisper-large-v3"
                            data-testid="whisper-model-input"
                        />
                    </Field>
                    <Field
                        label="LANGUAGE"
                        hint="Blank = auto-detect. Use ISO-639-1 codes (en, es, fr, de, ja). Auto is fine for most."
                    >
                        <Input
                            value={form.whisper_language}
                            onChange={set("whisper_language")}
                            placeholder="(auto)"
                            data-testid="whisper-language-input"
                        />
                    </Field>
                </div>

                <Field
                    label="TRANSITION TRIM (SECONDS)"
                    hint="Last N seconds of each track are the blend into the next track in your mix — Whisper will NOT transcribe this overlap zone. Default 15s."
                >
                    <Input
                        type="number"
                        min={0}
                        max={120}
                        value={form.whisper_transition_trim}
                        onChange={set("whisper_transition_trim")}
                        placeholder="15"
                        data-testid="whisper-transition-trim-input"
                    />
                </Field>

                <Field
                    label="API KEY (OPTIONAL)"
                    hint={settings.whisper_api_key_set
                        ? "A key is currently set. Leave blank to keep it; type a new one to replace."
                        : "Most local Whisper servers don't need a key. Leave blank for Speaches/faster-whisper."}
                >
                    <div className="relative">
                        <Input
                            type={showWhisperKey ? "text" : "password"}
                            value={form.whisper_api_key}
                            onChange={set("whisper_api_key")}
                            placeholder={settings.whisper_api_key_set ? "•••••••• (unchanged)" : "(none)"}
                            data-testid="whisper-api-key-input"
                        />
                        <button
                            type="button"
                            onClick={() => setShowWhisperKey((v) => !v)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-neon-green"
                            tabIndex={-1}
                        >
                            {showWhisperKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                </Field>

                <div className="flex flex-wrap items-center gap-3 pt-2">
                    <button
                        onClick={save}
                        disabled={saving}
                        data-testid="save-whisper-settings-button"
                        className="bg-neon-green text-black font-display font-black tracking-widest uppercase px-5 py-2.5 hover:bg-white transition-colors disabled:opacity-30 flex items-center gap-2 shadow-[0_0_20px_rgba(57,255,20,0.3)]"
                    >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        {saving ? "SAVING…" : "SAVE"}
                    </button>
                    <button
                        onClick={runWhisperTest}
                        disabled={testingWhisper || !form.whisper_enabled}
                        data-testid="test-whisper-button"
                        className="bg-transparent text-neon-cyan font-display font-bold tracking-widest uppercase px-5 py-2.5 border border-neon-cyan/40 hover:bg-neon-cyan/10 transition-colors disabled:opacity-30 flex items-center gap-2"
                    >
                        {testingWhisper ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                        TEST CONNECTION
                    </button>
                </div>

                {whisperResult && (
                    <div
                        data-testid="whisper-test-result"
                        className={`mt-3 border p-3 ${whisperResult.ok ? "border-neon-green/40 bg-neon-green/5" : "border-neon-red/40 bg-neon-red/5"}`}
                    >
                        <div className="flex items-center gap-2 mb-1.5">
                            {whisperResult.ok ? (
                                <CheckCircle2 className="w-4 h-4 text-neon-green" />
                            ) : (
                                <AlertTriangle className="w-4 h-4 text-neon-red" />
                            )}
                            <span className={`label ${whisperResult.ok ? "text-neon-green" : "text-neon-red"}`}>
                                {whisperResult.ok ? "REACHABLE" : "UNREACHABLE"}
                            </span>
                        </div>
                        {whisperResult.ok ? (
                            <div className="font-mono text-xs text-zinc-300 space-y-1">
                                <div>BASE: <span className="text-neon-cyan">{whisperResult.base_url}</span></div>
                                <div>MODEL: <span className="text-neon-cyan">{whisperResult.configured_model}</span>{whisperResult.model_in_list === false ? <span className="text-neon-red ml-2">⚠ NOT IN AVAILABLE LIST</span> : null}</div>
                                <div>LANGUAGE: <span className="text-neon-cyan">{whisperResult.language}</span></div>
                                {whisperResult.available_models?.length > 0 && (
                                    <div>
                                        AVAILABLE: <span className="text-zinc-400">{whisperResult.available_models.slice(0, 6).join(", ")}{whisperResult.available_models.length > 6 ? "…" : ""}</span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="font-mono text-xs text-zinc-300">{whisperResult.error}</div>
                        )}
                    </div>
                )}
            </section>

            <section className="border border-[#1A1D2E] bg-[#0a0c14] p-5 mt-6 scanlines relative">
                <div className="flex items-center gap-2 mb-3">
                    <Zap className="w-4 h-4 text-neon-green" />
                    <span className="label text-neon-green">// BULK AI OPERATIONS</span>
                    <span className="ml-auto label text-zinc-500">runs against your local LLM</span>
                </div>
                <p className="font-mono text-xs text-zinc-500 leading-relaxed mb-4">
                    Walk every mix in the library and auto-generate metadata or tags in the background.
                    Skips mixes that already have results unless FORCE is checked. Concurrency is capped
                    by <code className="text-neon-cyan">LLM_BULK_CONCURRENCY</code> (default 2) so your LLM doesn't get hammered.
                </p>
                <div className="space-y-3">
                    <BulkLLMRunner kind="tags" />
                    <BulkLLMRunner kind="descriptions" />
                </div>
            </section>

            <section className="border border-[#1A1D2E] bg-[#0a0c14] p-5 mt-6 scanlines relative">
                <div className="flex items-center gap-2 mb-3">
                    <Zap className="w-4 h-4 text-neon-green" />
                    <span className="label text-neon-green">// AI FEATURES UNLOCKED</span>
                </div>
                <ul className="font-mono text-sm text-zinc-400 leading-relaxed space-y-1">
                    <li>· <span className="text-neon-cyan">Generate Description</span> — auto-writes a 2–4 sentence vibey blurb from a mix's tracklist + BPM/key data. Available on each mix's edit modal.</li>
                    <li>· <span className="text-neon-cyan">Generate Tags</span> — infers 4–7 mood/vibe/sub-genre tags from the tracklist. Available on each mix's edit modal.</li>
                    <li>· Bulk operations above process the whole library in one shot.</li>
                </ul>
            </section>
        </div>
    );
};
