import { useEffect, useRef, useState, useCallback } from "react";
import { coverUrl } from "../../lib/api";

export const JogWheel = ({
    mix,
    track = null,
    playing = false,
    currentTime = 0,
    duration = 0,
    bpm = null,
    label = "A",
    side = "left",
    size = 260,
    art = null,
    active = true,
    transitioning = false,
    onScrub = null, // (deltaSeconds) => void - called while dragging
    onScrubEnd = null,
    color = null,
}) => {
    const rotRef = useRef(0);
    const rafRef = useRef(null);
    const diskRef = useRef(null);
    const wheelRef = useRef(null);
    const lastAngleRef = useRef(null);
    const cumulativeRef = useRef(0); // cumulative scrub delta in seconds during this drag
    const [dragging, setDragging] = useState(false);
    const [prevArt, setPrevArt] = useState(null);
    const [artKey, setArtKey] = useState(0);
    const cover = art || coverUrl(mix);
    const accent = color || (active ? "#00F0FF" : "#39FF14");

    // When art changes, capture previous and bump key for crossfade
    useEffect(() => {
        if (cover) {
            setPrevArt((p) => (p === cover ? p : p));
            setArtKey((k) => k + 1);
        }
    }, [cover]);

    // Continuous rotation (only when active + playing) or follows drag
    useEffect(() => {
        let last = performance.now();
        const loop = (t) => {
            const dt = (t - last) / 1000;
            last = t;
            if (!dragging) {
                if (playing && active) rotRef.current = (rotRef.current + dt * 45) % 360;
                else if (active) rotRef.current = (rotRef.current + dt * 4) % 360; // very slow idle
            }
            if (diskRef.current) {
                diskRef.current.style.transform = `rotate(${rotRef.current}deg)`;
            }
            rafRef.current = requestAnimationFrame(loop);
        };
        rafRef.current = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(rafRef.current);
    }, [playing, active, dragging]);

    const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;
    const ring = size * 0.47;
    const circ = 2 * Math.PI * ring;
    const dash = circ * progress;

    const angleFromEvent = useCallback((clientX, clientY) => {
        const rect = wheelRef.current?.getBoundingClientRect();
        if (!rect) return 0;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        return Math.atan2(clientY - cy, clientX - cx) * (180 / Math.PI);
    }, []);

    const onPointerDown = useCallback((e) => {
        if (!onScrub || !active) return;
        e.preventDefault();
        wheelRef.current.setPointerCapture(e.pointerId);
        setDragging(true);
        lastAngleRef.current = angleFromEvent(e.clientX, e.clientY);
        cumulativeRef.current = 0;
    }, [onScrub, active, angleFromEvent]);

    const onPointerMove = useCallback((e) => {
        if (!dragging) return;
        const a = angleFromEvent(e.clientX, e.clientY);
        let delta = a - lastAngleRef.current;
        // normalise across the -180/180 wrap
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        lastAngleRef.current = a;
        // visual rotation follows finger
        rotRef.current = (rotRef.current + delta + 360) % 360;
        // 360deg of drag = 30 seconds of audio (CDJ-ish)
        const seconds = (delta / 360) * 30;
        cumulativeRef.current += seconds;
        onScrub?.(seconds);
    }, [dragging, angleFromEvent, onScrub]);

    const endDrag = useCallback((e) => {
        if (!dragging) return;
        try { wheelRef.current.releasePointerCapture(e.pointerId); } catch {}
        setDragging(false);
        onScrubEnd?.(cumulativeRef.current);
        cumulativeRef.current = 0;
    }, [dragging, onScrubEnd]);

    const dim = !active && !transitioning;
    const opacity = dim ? 0.55 : 1;

    return (
        <div
            data-testid={`jog-wheel-${label}`}
            ref={wheelRef}
            className="relative select-none touch-none"
            style={{ width: size, height: size, opacity, transition: "opacity 0.6s ease" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
        >
            {/* Outer bezel */}
            <div
                className="absolute inset-0 rounded-full"
                style={{
                    background: "radial-gradient(circle at 30% 30%, #2a2d3e 0%, #0e1018 55%, #05060a 100%)",
                    boxShadow: "inset 0 0 20px rgba(0,0,0,0.85), 0 0 40px rgba(0,240,255,0.08), 0 8px 30px rgba(0,0,0,0.7)",
                }}
            />
            {/* Progress ring */}
            <svg className="absolute inset-0" viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={size / 2} cy={size / 2} r={ring} fill="none" stroke="#161824" strokeWidth="3" />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={ring}
                    fill="none"
                    stroke={accent}
                    strokeWidth="3"
                    strokeDasharray={`${dash} ${circ - dash}`}
                    style={{
                        filter: `drop-shadow(0 0 6px ${accent})`,
                        transition: dragging ? "none" : "stroke-dasharray 0.1s linear",
                    }}
                />
            </svg>
            {/* Tick marks */}
            <div className="absolute inset-0 pointer-events-none">
                {Array.from({ length: 60 }).map((_, i) => {
                    const angle = (i / 60) * 360;
                    const major = i % 5 === 0;
                    return (
                        <div
                            key={i}
                            className="absolute left-1/2 top-1/2 origin-bottom"
                            style={{
                                width: 1,
                                height: major ? 8 : 4,
                                background: major ? "#5C6170" : "#2a2d3e",
                                transform: `translate(-50%, -${size / 2 - 8}px) rotate(${angle}deg)`,
                                transformOrigin: `50% ${size / 2 - 8}px`,
                            }}
                        />
                    );
                })}
            </div>
            {/* Jog disc */}
            <div
                ref={diskRef}
                className={`absolute rounded-full overflow-hidden ${dragging ? "cursor-grabbing" : active && onScrub ? "cursor-grab" : ""}`}
                style={{
                    top: "14%",
                    left: "14%",
                    right: "14%",
                    bottom: "14%",
                    background: "radial-gradient(circle at 40% 40%, #1a1d2e, #05060a 80%)",
                    boxShadow: `inset 0 0 30px rgba(0,0,0,0.9), 0 0 12px ${accent}30`,
                }}
            >
                {prevArt && prevArt !== cover && (
                    <img
                        src={prevArt}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover opacity-60"
                        style={{ animation: "fadeOut 0.8s ease forwards" }}
                    />
                )}
                {cover ? (
                    <img
                        key={artKey}
                        src={cover}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover"
                        style={{ animation: "fadeIn 0.8s ease forwards", opacity: 0 }}
                        onLoad={() => setPrevArt(cover)}
                    />
                ) : (
                    <div className="w-full h-full grid-bg" />
                )}
                {/* Radial grooves overlay */}
                <div
                    className="absolute inset-0"
                    style={{
                        background: "repeating-radial-gradient(circle at center, rgba(0,0,0,0.4) 0 1px, transparent 1px 3px)",
                        mixBlendMode: "multiply",
                    }}
                />
                {/* Center hub */}
                <div
                    className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full flex flex-col items-center justify-center"
                    style={{
                        width: size * 0.3,
                        height: size * 0.3,
                        background: "radial-gradient(circle, #111425 0%, #000 100%)",
                        border: `1px solid ${accent}`,
                        boxShadow: `0 0 14px ${accent}66`,
                    }}
                >
                    <div className="label tracking-[0.25em]" style={{ color: accent, fontSize: size * 0.055 }}>
                        DECK {label}
                    </div>
                    {bpm ? (
                        <div className="font-display font-black leading-none mt-0.5" style={{ color: "#fff", fontSize: size * 0.09 }}>
                            {bpm}
                        </div>
                    ) : (
                        <div className="label text-zinc-600" style={{ fontSize: size * 0.045 }}>
                            — BPM
                        </div>
                    )}
                    <div className="label text-zinc-500" style={{ fontSize: size * 0.035 }}>
                        {active && playing ? "PLAYING" : active ? "PAUSED" : "CUED"}
                    </div>
                </div>
            </div>
            {/* REC LED */}
            <div
                className="absolute rounded-full"
                style={{
                    top: 18,
                    right: side === "left" ? 18 : "auto",
                    left: side === "left" ? "auto" : 18,
                    width: 8,
                    height: 8,
                    background: active && playing ? "#FF003C" : "#1a1d2e",
                    boxShadow: active && playing ? "0 0 10px #FF003C" : "none",
                    transition: "all 0.3s ease",
                }}
            />
            {/* Track title scroller around the disc */}
            {track?.title && (
                <div
                    className="absolute left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-sm"
                    style={{
                        bottom: -6,
                        background: "#0a0c14",
                        border: `1px solid ${accent}40`,
                        maxWidth: size - 30,
                    }}
                >
                    <div className="font-mono text-[10px] truncate" style={{ color: accent }}>
                        {track.title}
                    </div>
                </div>
            )}
        </div>
    );
};
