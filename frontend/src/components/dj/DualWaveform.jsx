import { useEffect, useRef, useMemo } from "react";

function buildBars(seed, count = 400) {
    let s = 0;
    for (let i = 0; i < seed.length; i++) s = (s * 31 + seed.charCodeAt(i)) >>> 0;
    const rng = () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 0xffffffff;
    };
    const arr = [];
    for (let i = 0; i < count; i++) {
        const t = i / count;
        const env = 0.4 + 0.6 * Math.sin(t * Math.PI);
        const noise = 0.25 + 0.75 * rng();
        const wave = (Math.sin(t * 23) + Math.sin(t * 57.2 + 1.2)) * 0.25 + 0.5;
        arr.push(Math.max(0.05, Math.min(1, env * wave * noise)));
    }
    return arr;
}

/** Full-mix waveform (overview, non-zoomed) with playhead line + track markers. */
export const FullWaveform = ({ mixId, currentTime, duration, tracks = [], onSeek, height = 56 }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const bars = useMemo(() => buildBars(mixId || "m", 360), [mixId]);

    useEffect(() => {
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;
        const dpr = window.devicePixelRatio || 1;
        const cssW = container.clientWidth;
        canvas.width = cssW * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${cssW}px`;
        canvas.style.height = `${height}px`;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, height);

        const barCount = bars.length;
        const barW = cssW / barCount;
        const progress = duration > 0 ? currentTime / duration : 0;
        const playedBars = Math.floor(progress * barCount);

        // background
        ctx.fillStyle = "#07090f";
        ctx.fillRect(0, 0, cssW, height);

        for (let i = 0; i < barCount; i++) {
            const v = bars[i];
            const h = v * (height - 4);
            const x = i * barW;
            const y = (height - h) / 2;
            const played = i <= playedBars;
            ctx.fillStyle = played ? "#00F0FF" : "#1A1D2E";
            ctx.fillRect(x, y, Math.max(0.5, barW - 0.5), h);
        }

        // track markers on top+bottom edge
        if (duration > 0 && tracks?.length) {
            ctx.fillStyle = "#39FF14";
            tracks.forEach((t) => {
                const tx = (t.start_seconds / duration) * cssW;
                ctx.fillRect(tx, 0, 1, 4);
                ctx.fillRect(tx, height - 4, 1, 4);
            });
        }

        // playhead
        const px = progress * cssW;
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(px - 0.5, 0, 1, height);
    }, [bars, currentTime, duration, tracks, height]);

    const handleClick = (e) => {
        if (!onSeek || !duration) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        onSeek((x / rect.width) * duration);
    };

    return (
        <div ref={containerRef} className="w-full cursor-pointer relative" onClick={handleClick} data-testid="full-waveform">
            <canvas ref={canvasRef} className="block" />
        </div>
    );
};

/** Zoomed CDJ-style waveform - 30s window centered on the playhead, stereo-style dual. */
export const ZoomedWaveform = ({ mixId, currentTime, duration, tracks = [], onSeek, height = 90, windowSec = 30 }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const bars = useMemo(() => buildBars((mixId || "m") + "-zoom", 1800), [mixId]);
    const bars2 = useMemo(() => buildBars((mixId || "m") + "-zoom2", 1800), [mixId]);

    useEffect(() => {
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;
        const dpr = window.devicePixelRatio || 1;
        const cssW = container.clientWidth;
        canvas.width = cssW * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${cssW}px`;
        canvas.style.height = `${height}px`;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, height);

        if (!duration || duration <= 0) return;

        const barsPerSec = bars.length / duration;
        const windowStartSec = currentTime - windowSec / 2;
        const pxPerSec = cssW / windowSec;

        // Background grid
        ctx.fillStyle = "#070911";
        ctx.fillRect(0, 0, cssW, height);
        // 1s vertical gridlines
        ctx.fillStyle = "#101322";
        for (let s = Math.floor(windowStartSec); s <= Math.floor(windowStartSec + windowSec); s++) {
            const x = (s - windowStartSec) * pxPerSec;
            ctx.fillRect(x, 0, 1, height);
        }

        const mid = height / 2;
        const bandH = height / 2 - 2;
        // Upper band (TREBLE) - cyan
        const drawBand = (data, color, topY, bandHeight) => {
            ctx.fillStyle = color;
            const sliceW = 1;
            for (let x = 0; x < cssW; x += sliceW) {
                const sec = windowStartSec + x / pxPerSec;
                if (sec < 0 || sec >= duration) continue;
                const idx = Math.floor(sec * barsPerSec);
                const v = data[idx] || 0;
                const h = v * bandHeight;
                ctx.fillRect(x, topY + bandHeight - h, sliceW, h);
            }
        };
        drawBand(bars, "#00F0FF", 2, bandH - 2);
        drawBand(bars2.map((v, i) => v * 0.9), "#FF9D00", mid + 1, bandH - 1);

        // Track boundary markers in window
        if (tracks?.length) {
            tracks.forEach((t) => {
                const inWin = t.start_seconds >= windowStartSec && t.start_seconds <= windowStartSec + windowSec;
                if (inWin) {
                    const x = (t.start_seconds - windowStartSec) * pxPerSec;
                    ctx.fillStyle = "#39FF14";
                    ctx.fillRect(x, 0, 1, height);
                    ctx.fillStyle = "#39FF14";
                    ctx.font = "10px 'JetBrains Mono', monospace";
                    ctx.fillText(`#${t.index}`, x + 3, 10);
                }
            });
        }

        // Centre playhead - always middle
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(cssW / 2 - 1, 0, 2, height);
        // center diamond
        ctx.fillStyle = "#FF003C";
        ctx.beginPath();
        ctx.moveTo(cssW / 2, mid - 3);
        ctx.lineTo(cssW / 2 + 4, mid);
        ctx.lineTo(cssW / 2, mid + 3);
        ctx.lineTo(cssW / 2 - 4, mid);
        ctx.closePath();
        ctx.fill();
    }, [bars, bars2, currentTime, duration, tracks, height, windowSec]);

    const handleClick = (e) => {
        if (!onSeek || !duration) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const offset = (x - rect.width / 2) / rect.width * windowSec;
        onSeek(Math.max(0, Math.min(duration, currentTime + offset)));
    };

    return (
        <div ref={containerRef} className="w-full cursor-pointer relative" onClick={handleClick} data-testid="zoomed-waveform">
            <canvas ref={canvasRef} className="block" />
            <div className="absolute top-1 left-2 label text-zinc-600" style={{ fontSize: 9 }}>
                -{windowSec / 2}s
            </div>
            <div className="absolute top-1 right-2 label text-zinc-600" style={{ fontSize: 9 }}>
                +{windowSec / 2}s
            </div>
        </div>
    );
};
