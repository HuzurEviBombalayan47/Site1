import { useRef } from "react";
import { Mic, Image as ImageIcon, MessageSquare, Volume2, Music, Zap } from "lucide-react";

const PX_PER_SEC = 90;
const TYPE_COLORS = {
  image: "var(--cyan)",
  video: "var(--lime)",
  gif: "var(--magenta)",
  text: "#8b8b93",
};

function fmt(t) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const ROWS = [
  { key: "audio", label: "Audio", icon: Mic },
  { key: "visuals", label: "Visuals", icon: ImageIcon },
  { key: "captions", label: "Captions", icon: MessageSquare },
  { key: "sfx", label: "SFX", icon: Volume2 },
  { key: "music", label: "Music", icon: Music },
];

export default function Timeline({ job, currentTime, duration, onSeek, selectedClipId, onSelectClip }) {
  const tl = job.timeline;
  const trackRef = useRef(null);
  const width = Math.max(duration * PX_PER_SEC, 400);
  const ticks = [];
  for (let s = 0; s <= Math.ceil(duration); s++) ticks.push(s);

  const seekAt = (e) => {
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const x = e.clientX - rect.left + track.scrollLeft;
    onSeek(Math.max(0, Math.min(duration, x / PX_PER_SEC)));
  };

  return (
    <div className="border-t border-border bg-card/60 backdrop-blur">
      <div className="flex">
        {/* Fixed labels */}
        <div className="w-[92px] shrink-0 border-r border-border bg-card z-10">
          <div className="h-7 border-b border-border" />
          {ROWS.map((r) => {
            const Icon = r.icon;
            return (
              <div key={r.key} className="h-[52px] flex items-center gap-1.5 px-3 border-b border-border/60 text-xs font-medium text-muted-foreground">
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{r.label}</span>
              </div>
            );
          })}
        </div>

        {/* Scrollable track */}
        <div ref={trackRef} className="flex-1 overflow-x-auto relative" data-testid="timeline-track">
          <div style={{ width }} className="relative">
            {/* Ruler */}
            <div className="h-7 border-b border-border relative cursor-pointer" onClick={seekAt}>
              {ticks.map((s) => (
                <div key={s} className="absolute top-0 h-full border-l border-border/50" style={{ left: s * PX_PER_SEC }}>
                  <span className="absolute top-1 left-1 text-[9px] font-mono-x text-muted-foreground">{fmt(s)}</span>
                </div>
              ))}
            </div>

            {/* Audio row */}
            <div className="h-[52px] border-b border-border/60 relative cursor-pointer px-0" onClick={seekAt}>
              <div className="absolute inset-x-1 top-1/2 -translate-y-1/2 h-8 rounded bg-gradient-to-r from-[hsl(72_100%_55%_/_0.25)] to-[hsl(72_100%_55%_/_0.1)] border border-[hsl(72_100%_55%_/_0.3)] flex items-center overflow-hidden">
                <div className="flex items-end gap-[2px] px-2 h-full py-2 opacity-60">
                  {Array.from({ length: Math.ceil(width / 6) }).map((_, i) => (
                    <div key={i} className="w-[2px] bg-[var(--lime)]" style={{ height: `${20 + Math.abs(Math.sin(i * 0.7)) * 60}%` }} />
                  ))}
                </div>
              </div>
            </div>

            {/* Visuals row */}
            <div className="h-[52px] border-b border-border/60 relative cursor-pointer" onClick={seekAt}>
              {tl.visuals.map((c) => {
                const active = c.id === selectedClipId;
                return (
                  <button
                    key={c.id}
                    data-testid={`timeline-clip-${c.id}`}
                    onClick={(e) => { e.stopPropagation(); onSelectClip(c.id); }}
                    className={`absolute top-1.5 bottom-1.5 rounded overflow-hidden border-2 transition-all ${active ? "z-20" : "z-10 border-transparent hover:border-white/40"}`}
                    style={{
                      left: c.start * PX_PER_SEC + 2,
                      width: Math.max((c.end - c.start) * PX_PER_SEC - 4, 14),
                      borderColor: active ? TYPE_COLORS[c.visual_type] : undefined,
                      boxShadow: active ? `0 0 0 1px ${TYPE_COLORS[c.visual_type]}` : undefined,
                    }}
                  >
                    {c.preview || c.url ? (
                      <img src={c.preview || c.url} alt="" className="absolute inset-0 w-full h-full object-cover opacity-80" />
                    ) : (
                      <div className="absolute inset-0" style={{ background: TYPE_COLORS[c.visual_type] }} />
                    )}
                    <div className="absolute inset-0 bg-black/30" />
                    <div className="absolute bottom-0.5 left-1 right-1 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: TYPE_COLORS[c.visual_type] }} />
                      {c.emphasis && <Zap className="w-2.5 h-2.5 text-[var(--magenta)] shrink-0" />}
                      <span className="text-[9px] text-white truncate font-mono-x">{c.search_query}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Captions row */}
            <div className="h-[52px] border-b border-border/60 relative cursor-pointer" onClick={seekAt}>
              {(tl.captions || []).map((c) => (
                <div
                  key={c.id}
                  className="absolute top-3 bottom-3 rounded bg-secondary border border-border flex items-center px-1.5 overflow-hidden"
                  style={{ left: c.start * PX_PER_SEC + 2, width: Math.max((c.end - c.start) * PX_PER_SEC - 4, 10) }}
                >
                  <span className="text-[9px] text-foreground truncate">{c.text}</span>
                </div>
              ))}
            </div>

            {/* SFX row */}
            <div className="h-[52px] border-b border-border/60 relative cursor-pointer" onClick={seekAt}>
              {(tl.sfx || []).map((s) => (
                <div
                  key={s.id}
                  className="absolute top-1/2 -translate-y-1/2 flex flex-col items-center"
                  style={{ left: s.time * PX_PER_SEC }}
                  title={s.name}
                >
                  <div className="w-2.5 h-2.5 rounded-full bg-[var(--magenta)] glow-magenta" />
                  <span className="text-[8px] font-mono-x text-muted-foreground mt-0.5 whitespace-nowrap">{s.name}</span>
                </div>
              ))}
            </div>

            {/* Music row */}
            <div className="h-[52px] relative flex items-center px-3">
              <span className="text-[10px] font-mono-x text-muted-foreground/60">müzik katmanı — boş</span>
            </div>

            {/* Playhead */}
            <div className="absolute top-0 bottom-0 w-[2px] bg-white z-30 pointer-events-none" style={{ left: currentTime * PX_PER_SEC }}>
              <div className="w-3 h-3 -ml-[5px] -mt-[2px] rotate-45 bg-white" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
