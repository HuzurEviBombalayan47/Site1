import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { UploadCloud, Music4, Zap, Flame, Clapperboard, Film, Loader2, FileAudio } from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/api";

const MODES = [
  { id: "documentary", label: "Documentary", desc: "Belgesel / video-essay, konuya uygun B-roll", icon: Film },
  { id: "normal", label: "Normal", desc: "Temiz YouTube edit'i", icon: Clapperboard },
  { id: "fast", label: "Fast", desc: "Daha fazla görsel, hızlı geçiş", icon: Zap },
  { id: "shitpost", label: "Shitpost", desc: "Absürt meme, ani zoom, kaos SFX", icon: Flame },
];

const FORMATS = [
  { id: "youtube", label: "YouTube", ratio: "16:9", box: "w-14 h-8" },
  { id: "shorts", label: "Shorts", ratio: "9:16", box: "w-6 h-11" },
  { id: "square", label: "Square", ratio: "1:1", box: "w-10 h-10" },
];

export default function UploadScreen({ onCreated }) {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("documentary");
  const [format, setFormat] = useState("youtube");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [providers, setProviders] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    api.getConfig().then((c) => setProviders(c.providers)).catch(() => {});
  }, []);

  const pick = (f) => {
    if (!f) return;
    if (!f.type.startsWith("audio")) {
      toast.error("Lütfen bir ses dosyası yükle (mp3, wav, m4a...)");
      return;
    }
    setFile(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0]);
  };

  const submit = async () => {
    if (!file) {
      toast.error("Önce bir ses dosyası seç");
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("audio", file);
      fd.append("mode", mode);
      fd.append("format", format);
      const res = await api.createJob(fd);
      onCreated(res.id);
    } catch (e) {
      toast.error("Yükleme başarısız: " + (e?.response?.data?.detail || e.message));
      setSubmitting(false);
    }
  };

  return (
    <div className="relative z-10 min-h-screen flex flex-col items-center px-5 py-10 sm:py-16 bg-grid">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3 mb-2"
      >
        <div className="w-9 h-9 rounded-lg grid place-items-center font-display font-extrabold text-xl" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
          S
        </div>
        <span className="font-mono-x text-xs tracking-[0.3em] text-muted-foreground uppercase">Shitpost Studio</span>
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="font-display font-extrabold text-center leading-[0.95] text-5xl sm:text-6xl lg:text-7xl max-w-4xl mt-4"
      >
        Sesini at.
        <br />
        <span className="text-lime">videosunu al.</span>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15 }}
        className="text-muted-foreground text-center max-w-xl mt-5 text-base"
      >
        Tek yapman gereken bir ses dosyası yüklemek. AI konuşmayı anlar, meme'leri, GIF'leri,
        B-roll'ları ve ses efektlerini tam zamanında yerleştirir.
      </motion.p>

      {/* Dropzone */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="w-full max-w-2xl mt-10"
      >
        <div
          data-testid="upload-dropzone"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
            dragging ? "border-[var(--lime)] bg-[hsl(72_100%_55%_/_0.06)]" : "border-border bg-card/60"
          } ${file ? "glow-lime" : ""}`}
        >
          <input
            ref={inputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            data-testid="upload-file-input"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {file ? (
            <div className="flex flex-col items-center gap-2">
              <FileAudio className="w-10 h-10 text-lime" />
              <div className="font-display font-bold text-lg" data-testid="upload-filename">{file.name}</div>
              <div className="text-xs text-muted-foreground font-mono-x">
                {(file.size / 1024 / 1024).toFixed(2)} MB · değiştirmek için tıkla
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="w-14 h-14 rounded-full grid place-items-center bg-secondary">
                <UploadCloud className="w-7 h-7 text-lime" />
              </div>
              <div className="font-display font-bold text-lg">Ses dosyasını sürükle veya seç</div>
              <div className="text-xs text-muted-foreground flex items-center gap-1.5 font-mono-x">
                <Music4 className="w-3.5 h-3.5" /> MP3 · WAV · M4A · OGG · FLAC
              </div>
            </div>
          )}
        </div>
      </motion.div>

      {/* Mode selector */}
      <div className="w-full max-w-2xl mt-8">
        <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3 font-mono-x">Edit modu</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {MODES.map((m) => {
            const Icon = m.icon;
            const active = mode === m.id;
            return (
              <button
                key={m.id}
                data-testid={`mode-${m.id}`}
                onClick={() => setMode(m.id)}
                className={`text-left rounded-xl border p-4 transition-all ${
                  active ? "border-[var(--lime)] bg-secondary glow-lime" : "border-border bg-card/50 hover:border-muted-foreground"
                }`}
              >
                <Icon className={`w-5 h-5 mb-2 ${active ? "text-lime" : "text-muted-foreground"}`} />
                <div className="font-display font-bold">{m.label}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{m.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Format selector */}
      <div className="w-full max-w-2xl mt-6">
        <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3 font-mono-x">Format</div>
        <div className="flex gap-3">
          {FORMATS.map((f) => {
            const active = format === f.id;
            return (
              <button
                key={f.id}
                data-testid={`format-${f.id}`}
                onClick={() => setFormat(f.id)}
                className={`flex-1 rounded-xl border p-4 flex flex-col items-center gap-2 transition-all ${
                  active ? "border-[var(--lime)] bg-secondary glow-lime" : "border-border bg-card/50 hover:border-muted-foreground"
                }`}
              >
                <div className={`${f.box} rounded ${active ? "bg-[var(--lime)]" : "bg-muted-foreground/40"}`} />
                <div className="font-display font-bold text-sm">{f.label}</div>
                <div className="text-[10px] text-muted-foreground font-mono-x">{f.ratio}</div>
              </button>
            );
          })}
        </div>
      </div>

      <motion.div className="w-full max-w-2xl mt-8">
        <Button
          data-testid="analyze-button"
          onClick={submit}
          disabled={submitting || !file}
          className="w-full h-14 text-base font-display font-bold rounded-xl"
          style={{ background: "var(--lime)", color: "#0b0b0f" }}
        >
          {submitting ? (
            <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Başlatılıyor...</>
          ) : (
            <><Flame className="w-5 h-5 mr-2" /> Analiz Et</>
          )}
        </Button>
      </motion.div>

      {providers && (
        <div className="flex flex-wrap justify-center gap-x-5 gap-y-2 mt-6 text-[11px] font-mono-x text-muted-foreground">
          {[
            ["AssemblyAI", providers.stt_assemblyai],
            ["Gemini", providers.llm_gemini],
            ["Pexels", providers.pexels],
            ["Giphy", providers.giphy],
          ].map(([n, ok]) => (
            <span key={n} className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-[var(--lime)]" : "bg-destructive"}`} />
              {n}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
