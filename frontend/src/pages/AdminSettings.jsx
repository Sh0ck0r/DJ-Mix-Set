import { useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Settings as SettingsIcon, ArrowLeft, CheckCircle2, AlertTriangle, Loader2, Server, Zap, Eye, EyeOff, Save } from "lucide-react";

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
    });
    const [showKey, setShowKey] = useState(false);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);

    useEffect(() => {
        api.getSettings().then((s) => {
            setSettings(s);
            setForm({
                llm_base_url: s.llm_base_url || "",
                llm_api_key: "", // never preload secrets
                llm_model: s.llm_model || "",
                llm_enabled: !!s.llm_enabled,
            });
        }).catch(() => toast.error("Failed to load settings"));
    }, []);

    if (!token) return <Navigate to="/admin/login" replace />;

    const set = (k) => (e) =>
        setForm({ ...form, [k]: e?.target?.type === "checkbox" ? e.target.checked : e.target.value });

    const save = async () => {
        setSaving(true);
        try {
            const patch = { ...form };
            if (!patch.llm_api_key) delete patch.llm_api_key; // empty -> keep existing
            const updated = await api.updateSettings(patch);
            setSettings(updated);
            setForm((f) => ({ ...f, llm_api_key: "" }));
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

            <section className="border border-[#1A1D2E] bg-[#0a0c14] p-5 mt-6 scanlines relative">
                <div className="flex items-center gap-2 mb-3">
                    <Zap className="w-4 h-4 text-neon-green" />
                    <span className="label text-neon-green">// AI FEATURES UNLOCKED</span>
                </div>
                <ul className="font-mono text-sm text-zinc-400 leading-relaxed space-y-1">
                    <li>· <span className="text-neon-cyan">Generate Description</span> — auto-writes a 2–4 sentence vibey blurb from a mix's tracklist + BPM/key data. Available on each mix's edit modal.</li>
                    <li>· More AI features coming: smart playlist builder, mood-tag inference, etc.</li>
                </ul>
            </section>
        </div>
    );
};
