import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

client.interceptors.request.use((config) => {
    const token = localStorage.getItem("mixdeck_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

export const api = {
    listMixes: (q = "", genre = "") =>
        client.get("/mixes", { params: { q: q || undefined, genre: genre || undefined } }).then((r) => r.data),
    getMix: (id) => client.get(`/mixes/${id}`).then((r) => r.data),
    incPlay: (id) => client.post(`/mixes/${id}/play`),
    listGenres: () => client.get("/mixes/genres").then((r) => r.data),
    seedDemo: () => client.post("/seed-demo").then((r) => r.data),
    compatibleMixes: (id, limit = 8) => client.get(`/mixes/${id}/compatible`, { params: { limit } }).then((r) => r.data),
    waveform: (id) => client.get(`/mixes/${id}/waveform`).then((r) => r.data),
    trackArtwork: (artist, title) =>
        client.get("/tracks/artwork", { params: { artist: artist || "", title: title || "" } }).then((r) => r.data),

    login: (password) => client.post("/auth/login", { password }).then((r) => r.data),
    verify: () => client.get("/auth/verify").then((r) => r.data),

    createMix: (body) => client.post("/admin/mixes", body).then((r) => r.data),
    updateMix: (id, body) => client.patch(`/admin/mixes/${id}`, body).then((r) => r.data),
    deleteMix: (id) => client.delete(`/admin/mixes/${id}`).then((r) => r.data),
    uploadAudio: (id, file, onProgress) => {
        const fd = new FormData();
        fd.append("file", file);
        return client.post(`/admin/mixes/${id}/audio`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
            onUploadProgress: (e) => onProgress?.(Math.round((e.loaded * 100) / (e.total || e.loaded))),
        }).then((r) => r.data);
    },
    uploadCover: (id, file) => {
        const fd = new FormData();
        fd.append("file", file);
        return client.post(`/admin/mixes/${id}/cover`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
        }).then((r) => r.data);
    },
    uploadCue: (id, file) => {
        const fd = new FormData();
        fd.append("file", file);
        return client.post(`/admin/mixes/${id}/cue`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
        }).then((r) => r.data);
    },
    scanDirectory: (path, recursive = true, default_genre = "", analyze = true) =>
        client.post("/admin/scan", { path, recursive, default_genre, analyze }, { timeout: 30000 }).then((r) => r.data),
    scanStatus: (taskId) => client.get(`/admin/scan/${taskId}`).then((r) => r.data),
    analysisOverview: () => client.get("/admin/analysis_overview").then((r) => r.data),
    analyzeAll: (force = false) => client.post(`/admin/analyze_all`, null, { params: { force } }).then((r) => r.data),
    analyzeMix: (id) => client.post(`/admin/mixes/${id}/analyze`).then((r) => r.data),
    analysisStatus: (id) => client.get(`/mixes/${id}/analysis_status`).then((r) => r.data),
    getSettings: () => client.get("/admin/settings").then((r) => r.data),
    updateSettings: (patch) => client.patch("/admin/settings", patch).then((r) => r.data),
    testLLM: () => client.post("/admin/settings/test_llm").then((r) => r.data),
    generateDescription: (id) => client.post(`/admin/mixes/${id}/generate_description`).then((r) => r.data),
    setDuration: (id, duration) => {
        const fd = new FormData();
        fd.append("duration", duration);
        return client.post(`/mixes/${id}/duration`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
        });
    },
};

export const streamUrl = (mix) => {
    if (mix?.audio_url) return mix.audio_url;
    if (mix?.audio_filename || mix?.source_path) return `${API}/stream/${mix.id}`;
    return null;
};

export const coverUrl = (mix) => {
    if (mix?.cover_url) return mix.cover_url;
    if (mix?.cover_filename || mix?.source_cover_path) return `${API}/cover/${mix.id}`;
    return null;
};

// Build the public, OG-rich share URL for a mix (used in social sharing).
// Always points at the backend's /api/share/{id} so crawlers see the meta tags;
// real users get auto-redirected to /mix/{id} via meta-refresh.
export const shareUrl = (mixId, t) => {
    const base = `${API}/share/${mixId}`;
    return t > 0 ? `${base}?t=${Math.floor(t)}` : base;
};

// Resume positions (saved by PlayerContext every 5s while listening).
const RESUME_KEY = "mixdeck_resume";
export const getResumePosition = (mixId) => {
    try {
        const raw = localStorage.getItem(RESUME_KEY);
        if (!raw) return null;
        const map = JSON.parse(raw);
        const e = map[mixId];
        return e && e.t > 0 ? { t: e.t, at: e.at } : null;
    } catch {
        return null;
    }
};
export const clearResumePosition = (mixId) => {
    try {
        const raw = localStorage.getItem(RESUME_KEY);
        if (!raw) return;
        const map = JSON.parse(raw);
        delete map[mixId];
        localStorage.setItem(RESUME_KEY, JSON.stringify(map));
    } catch { /* ignore */ }
};

export const fmtTime = (s) => {
    if (!Number.isFinite(s) || s < 0) return "00:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    if (m >= 60) {
        const h = Math.floor(m / 60);
        return `${String(h).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    }
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};

// Parse "12:34" or "01:02:03" or "734" (seconds) -> seconds
export const parseTimeStamp = (raw) => {
    if (raw == null) return null;
    const s = String(raw).trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) return parseInt(s, 10);
    const parts = s.split(":").map((p) => parseInt(p, 10));
    if (parts.some((p) => Number.isNaN(p))) return null;
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return null;
};
