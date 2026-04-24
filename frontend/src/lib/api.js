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
    if (mix?.audio_filename) return `${API}/stream/${mix.id}`;
    return null;
};

export const coverUrl = (mix) => {
    if (mix?.cover_url) return mix.cover_url;
    if (mix?.cover_filename) return `${API}/cover/${mix.id}`;
    return null;
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
