import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Play, Pause, Download, Plus, Film, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import Preview from "@/components/Preview";
import Timeline from "@/components/Timeline";
import Inspector from "@/components/Inspector";
import MediaBrowser from "@/components/MediaBrowser";
import api from "@/api";

function fmt(t) {
  if (!isFinite(t)) t = 0;
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function Editor({ jobId, onReset }) {
  const [job, setJob] = useState(null);
  const [sfxLib, setSfxLib] = useState([]);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedClipId, setSelectedClipId] = useState(null);
  const [tab, setTab] = useState("clip");
  const [browserClip, setBrowserClip] = useState(null);
  const audioRef = useRef(null);
  const rafRef = useRef();
  const lastTRef = useRef(0);
  const lastUiRef = useRef(0);

  useEffect(() => {
    api.getJob(jobId).then(setJob);
    api.getSfx().then(setSfxLib).catch(() => {});
  }, [jobId]);

  const duration = job?.timeline?.duration || job?.audio_duration || 0;

  useEffect(() => {
    const tick = () => {
      const a = audioRef.current;
      if (a) {
        const t = a.currentTime;
        if (!a.paused) {
          const sfx = job?.timeline?.sfx || [];
          for (const s of sfx) {
            if (s.time > lastTRef.current && s.time <= t) {
              try {
                const au = new Audio(api.sfxUrl(s.name));
                au.volume = s.volume ?? 0.9;
                au.play().catch(() => {});
              } catch (e) {}
            }
          }
          lastTRef.current = t;
        }
        const now = performance.now();
        if (now - lastUiRef.current > 60) {
          setCurrentTime(t);
          lastUiRef.current = now;
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [job]);

  const togglePlay = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      lastTRef.current = a.currentTime;
      a.play();
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  };

  const seek = (t) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = t;
    lastTRef.current = t;
    setCurrentTime(t);
  };

  const startRender = async () => {
    try {
      await api.renderJob(jobId);
      setJob((p) => ({ ...p, status: "rendering", progress: 0, output_ready: false }));
      toast.info("Render başladı — bu birkaç dakika sürebilir");
    } catch (e) {
      toast.error("Render başlatılamadı: " + (e?.response?.data?.detail || e.message));
    }
  };

  useEffect(() => {
    if (job?.status !== "rendering") return;
    const iv = setInterval(async () => {
      try {
        const j = await api.getJob(jobId);
        setJob((prev) => ({ ...prev, status: j.status, progress: j.progress, stage: j.stage, output_ready: j.output_ready, error: j.error, output_path: j.output_path }));
        if (j.status === "done") { clearInterval(iv); toast.success("Video hazır! 🎬"); }
        if (j.status === "error") { clearInterval(iv); toast.error("Render hatası: " + j.error); }
      } catch (e) {}
    }, 1300);
    return () => clearInterval(iv);
  }, [job?.status, jobId]);

  if (!job || !job.timeline) {
    return (
      <div className="relative z-10 min-h-screen grid place-items-center">
        <Loader2 className="w-8 h-8 animate-spin text-lime" />
      </div>
    );
  }

  const selectedClip = job.timeline.visuals.find((c) => c.id === selectedClipId) || null;
  const rendering = job.status === "rendering";
  const done = job.status === "done" && job.output_ready;

  return (
    <div className="relative z-10 min-h-screen flex flex-col">
      <audio ref={audioRef} src={api.audioUrl(jobId)} preload="auto" onEnded={() => setPlaying(false)} />

      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/70 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg grid place-items-center font-display font-extrabold" style={{ background: "var(--lime)", color: "#0b0b0f" }}>S</div>
          <div className="hidden sm:flex items-center gap-2">
            <span className="text-xs font-mono-x px-2 py-0.5 rounded bg-secondary uppercase">{job.mode}</span>
            <span className="text-xs font-mono-x px-2 py-0.5 rounded bg-secondary">{job.timeline.canvas.label}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button data-testid="new-video-button" variant="ghost" onClick={onReset} className="text-muted-foreground hover:text-foreground">
            <Plus className="w-4 h-4 mr-1.5" /> Yeni
          </Button>
          {done ? (
            <a href={api.downloadUrl(jobId)} data-testid="download-button" download>
              <Button className="font-display font-bold rounded-lg" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
                <Download className="w-4 h-4 mr-1.5" /> İndir
              </Button>
            </a>
          ) : (
            <Button data-testid="render-button" onClick={startRender} disabled={rendering} className="font-display font-bold rounded-lg" style={{ background: "var(--magenta)", color: "#fff" }}>
              {rendering ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> {job.progress}%</> : <><Film className="w-4 h-4 mr-1.5" /> Render MP4</>}
            </Button>
          )}
        </div>
      </header>

      {/* Main */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0">
        {/* Left: preview + transport */}
        <div className="flex-1 flex flex-col p-4 min-w-0">
          <div className="relative flex-1 flex items-center justify-center">
            <Preview job={job} currentTime={currentTime} playing={playing && !rendering} />

            {(rendering || done) && (
              <div className="absolute inset-0 grid place-items-center rounded-xl bg-black/80 backdrop-blur-sm" data-testid="render-overlay">
                {rendering ? (
                  <div className="text-center w-72">
                    <Loader2 className="w-8 h-8 animate-spin text-lime mx-auto mb-4" />
                    <div className="font-display font-bold text-lg mb-1">{job.stage}</div>
                    <div className="text-xs text-muted-foreground font-mono-x mb-3">Video render ediliyor</div>
                    <div className="h-2 rounded-full bg-secondary overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${job.progress}%`, background: "var(--lime)" }} />
                    </div>
                    <div className="text-xs font-mono-x text-muted-foreground mt-2">{job.progress}%</div>
                  </div>
                ) : (
                  <div className="text-center px-6">
                    <div className="w-14 h-14 rounded-full grid place-items-center mx-auto mb-4 glow-lime" style={{ background: "var(--lime)" }}>
                      <Film className="w-7 h-7 text-black" />
                    </div>
                    <div className="font-display font-extrabold text-xl mb-1">Videon hazır! 🎬</div>
                    <div className="w-full max-w-sm mt-4">
                      <video src={api.downloadUrl(jobId)} controls className="w-full rounded-lg border border-border" data-testid="final-video" />
                    </div>
                    <div className="flex gap-2 justify-center mt-4">
                      <a href={api.downloadUrl(jobId)} download>
                        <Button className="font-display font-bold" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
                          <Download className="w-4 h-4 mr-1.5" /> MP4 indir
                        </Button>
                      </a>
                      <Button variant="outline" className="border-border" onClick={() => setJob((p) => ({ ...p, status: "ready" }))} data-testid="back-to-editor">
                        Editöre dön
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Transport */}
          <div className="flex items-center gap-3 mt-4">
            <button data-testid="play-toggle" onClick={togglePlay} className="w-11 h-11 rounded-full grid place-items-center shrink-0 glow-lime" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
              {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
            </button>
            <span className="text-xs font-mono-x text-muted-foreground w-10 text-right">{fmt(currentTime)}</span>
            <input
              data-testid="scrubber"
              type="range"
              min={0}
              max={duration}
              step={0.01}
              value={currentTime}
              onChange={(e) => seek(parseFloat(e.target.value))}
              className="flex-1 accent-[var(--lime)] h-1.5"
            />
            <span className="text-xs font-mono-x text-muted-foreground w-10">{fmt(duration)}</span>
          </div>
        </div>

        {/* Right: inspector */}
        <aside className="w-full lg:w-[340px] shrink-0 lg:h-auto h-[400px]">
          <Inspector
            job={job}
            setJob={setJob}
            selectedClip={selectedClip}
            sfxLib={sfxLib}
            currentTime={currentTime}
            jobId={jobId}
            tab={tab}
            setTab={setTab}
            onOpenBrowser={(clip) => setBrowserClip(clip)}
          />
        </aside>
      </div>

      {/* Timeline */}
      <Timeline
        job={job}
        currentTime={currentTime}
        duration={duration}
        onSeek={seek}
        selectedClipId={selectedClipId}
        onSelectClip={selectClipHandler(setSelectedClipId, setTab)}
      />

      <MediaBrowser
        open={!!browserClip}
        onOpenChange={(o) => !o && setBrowserClip(null)}
        clip={browserClip}
        jobId={jobId}
        onApply={(updated) => setJob(updated)}
      />
    </div>
  );
}

function selectClipHandler(setSelectedClipId, setTab) {
  return (id) => {
    setSelectedClipId(id);
    setTab("clip");
  };
}
