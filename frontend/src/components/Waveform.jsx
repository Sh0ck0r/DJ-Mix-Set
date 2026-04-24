import { useEffect, useRef, useMemo } from "react";

// Pseudo-random deterministic waveform built from the mix id - looks like a real waveform.
function buildBars(seed, count = 220) {
    let s = 0;
    for (let i = 0; i < seed.length; i++) s = (s * 31 + seed.charCodeAt(i)) >>> 0;
    const rng = () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 0xffffffff;
    };
    const arr = [];
    for (let i = 0; i < count; i++) {
        // mix two sine waves with random envelope for organic shape
        const t = i / count;
        const env = 0.45 + 0.55 * Math.sin(t * Math.PI);
        const noise = 0.2 + 0.8 * rng();
        const wave = (Math.sin(t * 18) + Math.sin(t * 47.3 + 1.2)) * 0.25 + 0.5;
        arr.push(Math.max(0.05, Math.min(1, env * wave * noise)));
    }
    return arr;
}

export const Waveform = ({ mixId, currentTime, duration, onSeek, tracks = [], height = 96 }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const bars = useMemo(() => buildBars(mixId || "default"), [mixId]);

    useEffect(() => {
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;
        const dpr = window.devicePixelRatio || 1;
        const cssW = container.clientWidth;
        const cssH = height;
        canvas.width = cssW * dpr;
        canvas.height = cssH * dpr;
        canvas.style.width = `${cssW}px`;
        canvas.style.height = `${cssH}px`;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, cssH);

        const barCount = bars.length;
        const barW = cssW / barCount;
        const progress = duration > 0 ? currentTime / duration : 0;
        const playedBars = Math.floor(progress * barCount);

        // background grid
        ctx.fillStyle = "#0a0c14";
        ctx.fillRect(0, 0, cssW, cssH);

        // horizontal centerline
        ctx.strokeStyle = "rgba(255,255,255,0.05)";
        ctx.beginPath();
        ctx.moveTo(0, cssH / 2);
        ctx.lineTo(cssW, cssH / 2);
        ctx.stroke();

        for (let i = 0; i < barCount; i++) {
            const v = bars[i];
            const h = v * (cssH - 8);
            const x = i * barW;
            const y = (cssH - h) / 2;
            const isPlayed = i <= playedBars;
            ctx.fillStyle = isPlayed ? "#39FF14" : "#1A1D2E";
            ctx.fillRect(x + 0.5, y, Math.max(1, barW - 1), h);
        }

        // glow for played portion
        if (playedBars > 0) {
            ctx.shadowColor = "rgba(57,255,20,0.55)";
            ctx.shadowBlur = 14;
            ctx.fillStyle = "rgba(57,255,20,0.15)";
            ctx.fillRect(0, 0, playedBars * barW, cssH);
            ctx.shadowBlur = 0;
        }

        // playhead
        const px = playedBars * barW;
        ctx.fillStyle = "#00F0FF";
        ctx.fillRect(px - 1, 0, 2, cssH);

        // track markers
        if (duration > 0 && tracks?.length) {
            ctx.fillStyle = "rgba(0,240,255,0.5)";
            tracks.forEach((tr) => {
                const tx = (tr.start_seconds / duration) * cssW;
                ctx.fillRect(tx, 0, 1, 6);
                ctx.fillRect(tx, cssH - 6, 1, 6);
            });
        }
    }, [bars, currentTime, duration, tracks, height]);

    const handleClick = (e) => {
        if (!onSeek || !duration) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        onSeek((x / rect.width) * duration);
    };

    return (
        <div ref={containerRef} className="w-full relative cursor-pointer group" onClick={handleClick} data-testid="waveform">
            <canvas ref={canvasRef} className="block" />
            <div className="absolute inset-0 pointer-events-none border border-neon-cyan/15" />
        </div>
    );
};
