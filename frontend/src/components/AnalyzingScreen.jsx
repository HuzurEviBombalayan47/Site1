import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Check, AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/api";

const STEPS = [
  { key: "transcribing", label: "Ses analiz ediliyor" },
  { key: "analyzing", label: "Konular belirleniyor" },
  { key: "searching", label: "Görseller aranıyor" },
  { key: "captions", label: "Altyazılar oluşturuluyor" },
  { key: "ready", label: "Editör hazırlanıyor" },
];

function stageToStep(status, stage) {
  if (status === "transcribing") return 0;
  if (status === "analyzing") {
    if ((stage || "").includes("Görsel")) return 2;
    if ((stage || "").includes("Altyazı")) return 3;
    return 1;
  }
  if (status === "ready") return 4;
  return 0;
}

export default function AnalyzingScreen({ jobId, onReady, onReset }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const j = await api.getJob(jobId);
        if (cancelled) return;
        setJob(j);
        if (j.status === "ready") {
          setTimeout(() => onReady(), 600);
          return;
        }
        if (j.status === "error") {
          setError(j.error || "Bilinmeyen hata");
          return;
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
        return;
      }
      timer.current = setTimeout(poll, 1500);
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
  }, [jobId, onReady]);

  const activeStep = job ? stageToStep(job.status, job.stage) : 0;
  const progress = job?.progress || 0;

  return (
    <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-5 bg-grid">
      {error ? (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="max-w-md text-center">
          <div className="w-16 h-16 rounded-full grid place-items-center bg-destructive/15 mx-auto mb-5">
            <AlertTriangle className="w-8 h-8 text-destructive" />
          </div>
          <h2 className="font-display font-bold text-2xl mb-2">Bir şeyler ters gitti</h2>
          <p className="text-muted-foreground text-sm mb-6 font-mono-x break-words" data-testid="analyze-error">{error}</p>
          <Button onClick={onReset} data-testid="analyze-error-retry" className="rounded-xl font-display font-bold" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
            <RotateCcw className="w-4 h-4 mr-2" /> Tekrar dene
          </Button>
        </motion.div>
      ) : (
        <div className="w-full max-w-lg" data-testid="analyzing-screen">
          <div className="flex items-center gap-3 mb-8">
            <Loader2 className="w-6 h-6 text-lime animate-spin" />
            <div>
              <div className="font-display font-extrabold text-2xl leading-tight">Videon üretiliyor</div>
              <div className="text-xs text-muted-foreground font-mono-x">AI editör devrede — bu birkaç dakika sürebilir</div>
            </div>
          </div>

          <div className="space-y-3">
            {STEPS.map((s, i) => {
              const done = i < activeStep || job?.status === "ready";
              const active = i === activeStep && job?.status !== "ready";
              return (
                <div
                  key={s.key}
                  className={`flex items-center gap-3 rounded-xl border p-3.5 transition-all ${
                    active ? "border-[var(--lime)] bg-secondary" : done ? "border-border bg-card/40" : "border-border/50 bg-transparent opacity-50"
                  }`}
                >
                  <div className={`w-6 h-6 rounded-full grid place-items-center shrink-0 ${done ? "bg-[var(--lime)]" : active ? "bg-secondary pulse-ring" : "bg-muted"}`}>
                    {done ? <Check className="w-4 h-4 text-black" /> : active ? <Loader2 className="w-3.5 h-3.5 animate-spin text-lime" /> : null}
                  </div>
                  <span className={`font-medium ${active ? "text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground"}`}>
                    {s.label}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="mt-8">
            <div className="flex justify-between text-xs font-mono-x text-muted-foreground mb-2">
              <AnimatePresence mode="wait">
                <motion.span key={job?.stage} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  {job?.stage || "Sıraya alındı..."}
                </motion.span>
              </AnimatePresence>
              <span>{progress}%</span>
            </div>
            <div className="h-2 rounded-full bg-secondary overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ background: "var(--lime)" }}
                animate={{ width: `${progress}%` }}
                transition={{ ease: "easeOut" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
