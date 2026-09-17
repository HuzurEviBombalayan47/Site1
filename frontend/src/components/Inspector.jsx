import { useRef, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, ImageIcon, Wand2, Trash2, Plus, Loader2 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/api";

const EFFECTS = ["kenburns", "zoom_in", "zoom_out", "pan_left", "pan_right", "shake"];
const KINDS = ["image", "video", "gif"];
const FONTS = ["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono", "Liberation Sans", "Liberation Serif"];

export default function Inspector({ job, setJob, selectedClip, sfxLib, currentTime, jobId, tab, setTab, onOpenBrowser }) {
  const [regenLoading, setRegenLoading] = useState(false);
  const [localQuery, setLocalQuery] = useState("");
  const patchTimer = useRef(null);

  const style = job.caption_style || {};

  const updateStyle = (partial) => {
    const next = { ...style, ...partial };
    setJob({ ...job, caption_style: next });
    clearTimeout(patchTimer.current);
    patchTimer.current = setTimeout(() => {
      api.patchJob(jobId, { caption_style: partial }).catch(() => {});
    }, 350);
  };

  const regenerate = async (kindOverride) => {
    if (!selectedClip) return;
    setRegenLoading(true);
    try {
      const body = { clip_id: selectedClip.id };
      const q = localQuery || selectedClip.search_query;
      if (q) body.query = q;
      if (kindOverride) body.kind = kindOverride;
      const res = await api.regenerate(jobId, body);
      const visuals = job.timeline.visuals.map((c) => (c.id === res.clip.id ? res.clip : c));
      setJob({ ...job, timeline: { ...job.timeline, visuals } });
      toast.success("Yeni görsel bulundu");
    } catch (e) {
      toast.error("Bulunamadı: " + (e?.response?.data?.detail || e.message));
    } finally {
      setRegenLoading(false);
    }
  };

  const setEffect = async (effect) => {
    const visuals = job.timeline.visuals.map((c) => (c.id === selectedClip.id ? { ...c, effect } : c));
    setJob({ ...job, timeline: { ...job.timeline, visuals } });
    api.patchJob(jobId, { clip: { id: selectedClip.id, effect } }).catch(() => {});
  };

  const removeSfx = (id) => {
    const sfx = (job.timeline.sfx || []).filter((s) => s.id !== id);
    setJob({ ...job, timeline: { ...job.timeline, sfx } });
    api.patchJob(jobId, { sfx }).catch(() => {});
  };

  const addSfx = (name) => {
    const sfx = [
      ...(job.timeline.sfx || []),
      { id: crypto.randomUUID(), time: Math.round(currentTime * 100) / 100, name, volume: 0.9 },
    ].sort((a, b) => a.time - b.time);
    setJob({ ...job, timeline: { ...job.timeline, sfx } });
    api.patchJob(jobId, { sfx }).catch(() => {});
    toast.success(`${name} eklendi @ ${currentTime.toFixed(1)}s`);
  };

  return (
    <div className="h-full flex flex-col bg-card/60 border-l border-border">
      <Tabs value={tab} onValueChange={setTab} className="flex flex-col h-full">
        <TabsList className="grid grid-cols-3 m-3 bg-secondary">
          <TabsTrigger value="clip" data-testid="tab-clip">Klip</TabsTrigger>
          <TabsTrigger value="captions" data-testid="tab-captions">Altyazı</TabsTrigger>
          <TabsTrigger value="sfx" data-testid="tab-sfx">SFX</TabsTrigger>
        </TabsList>

        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {/* CLIP TAB */}
          <TabsContent value="clip" className="mt-0 space-y-4">
            {!selectedClip ? (
              <div className="text-sm text-muted-foreground text-center py-10">
                Timeline'dan bir görsele tıkla ve düzenle.
              </div>
            ) : (
              <>
                <div className="aspect-video rounded-lg overflow-hidden border border-border bg-black">
                  {selectedClip.preview || selectedClip.url ? (
                    <img src={selectedClip.preview || selectedClip.url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full grid place-items-center text-xs text-muted-foreground">no media</div>
                  )}
                </div>
                <div className="flex items-center justify-between text-xs font-mono-x text-muted-foreground">
                  <span className="px-2 py-0.5 rounded bg-secondary uppercase">{selectedClip.visual_type}</span>
                  <span>{selectedClip.start.toFixed(1)}s – {selectedClip.end.toFixed(1)}s</span>
                </div>
                {selectedClip.topic && (
                  <p className="text-xs text-muted-foreground italic">"{selectedClip.topic}"</p>
                )}

                <div>
                  <Label className="text-xs">Arama sorgusu</Label>
                  <Input
                    data-testid="clip-query-input"
                    defaultValue={selectedClip.search_query}
                    key={selectedClip.id}
                    onChange={(e) => setLocalQuery(e.target.value)}
                    className="bg-secondary border-border mt-1.5"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button data-testid="clip-regenerate" onClick={() => regenerate()} disabled={regenLoading} className="font-semibold" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
                    {regenLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><RefreshCw className="w-4 h-4 mr-1.5" /> Yenile</>}
                  </Button>
                  <Button data-testid="clip-browse" variant="outline" onClick={() => onOpenBrowser(selectedClip)} className="border-border">
                    <ImageIcon className="w-4 h-4 mr-1.5" /> Kütüphane
                  </Button>
                </div>

                <div>
                  <Label className="text-xs">Görsel türü</Label>
                  <div className="flex gap-1.5 mt-1.5">
                    {KINDS.map((k) => (
                      <button
                        key={k}
                        data-testid={`clip-kind-${k}`}
                        onClick={() => regenerate(k)}
                        className="flex-1 text-xs py-1.5 rounded-lg bg-secondary hover:bg-muted capitalize"
                      >
                        {k}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <Label className="text-xs">Efekt</Label>
                  <Select value={selectedClip.effect} onValueChange={setEffect}>
                    <SelectTrigger data-testid="clip-effect-select" className="bg-secondary border-border mt-1.5">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EFFECTS.map((e) => (
                        <SelectItem key={e} value={e}>{e}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
          </TabsContent>

          {/* CAPTIONS TAB */}
          <TabsContent value="captions" className="mt-0 space-y-4">
            <div className="flex items-center justify-between">
              <Label className="text-sm">Altyazılar açık</Label>
              <Switch data-testid="caption-enabled" checked={style.enabled !== false} onCheckedChange={(v) => updateStyle({ enabled: v })} />
            </div>
            <div>
              <Label className="text-xs">Font</Label>
              <Select value={style.font} onValueChange={(v) => updateStyle({ font: v })}>
                <SelectTrigger data-testid="caption-font" className="bg-secondary border-border mt-1.5"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {FONTS.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Boyut · {style.size}px</Label>
              <Slider data-testid="caption-size" value={[style.size || 54]} min={24} max={120} step={2} onValueChange={([v]) => updateStyle({ size: v })} className="mt-2" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Renk</Label>
                <input data-testid="caption-color" type="color" value={style.color || "#FFFFFF"} onChange={(e) => updateStyle({ color: e.target.value })} className="w-full h-9 mt-1.5 rounded bg-secondary border border-border" />
              </div>
              <div>
                <Label className="text-xs">Kenarlık</Label>
                <input data-testid="caption-outline-color" type="color" value={style.outline_color || "#000000"} onChange={(e) => updateStyle({ outline_color: e.target.value })} className="w-full h-9 mt-1.5 rounded bg-secondary border border-border" />
              </div>
            </div>
            <div>
              <Label className="text-xs">Kenarlık kalınlığı · {style.outline_width}</Label>
              <Slider data-testid="caption-outline-width" value={[style.outline_width ?? 4]} min={0} max={12} step={1} onValueChange={([v]) => updateStyle({ outline_width: v })} className="mt-2" />
            </div>
            <div>
              <Label className="text-xs">Konum</Label>
              <Select value={style.position} onValueChange={(v) => updateStyle({ position: v })}>
                <SelectTrigger data-testid="caption-position" className="bg-secondary border-border mt-1.5"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="bottom">Alt</SelectItem>
                  <SelectItem value="center">Orta</SelectItem>
                  <SelectItem value="top">Üst</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm">Kalın</Label>
              <Switch data-testid="caption-bold" checked={!!style.bold} onCheckedChange={(v) => updateStyle({ bold: v })} />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm">BÜYÜK HARF</Label>
              <Switch data-testid="caption-uppercase" checked={!!style.uppercase} onCheckedChange={(v) => updateStyle({ uppercase: v })} />
            </div>
          </TabsContent>

          {/* SFX TAB */}
          <TabsContent value="sfx" className="mt-0 space-y-4">
            <div>
              <Label className="text-xs">Playhead'e SFX ekle ({currentTime.toFixed(1)}s)</Label>
              <Select onValueChange={addSfx}>
                <SelectTrigger data-testid="sfx-add-select" className="bg-secondary border-border mt-1.5">
                  <SelectValue placeholder="Bir ses efekti seç..." />
                </SelectTrigger>
                <SelectContent>
                  {sfxLib.map((s) => (
                    <SelectItem key={s.name} value={s.name}>{s.label} — {s.mood}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Yerleştirilen SFX ({(job.timeline.sfx || []).length})</Label>
              {(job.timeline.sfx || []).length === 0 && (
                <p className="text-xs text-muted-foreground">Henüz SFX yok.</p>
              )}
              {(job.timeline.sfx || []).map((s) => (
                <div key={s.id} data-testid={`sfx-item-${s.id}`} className="flex items-center justify-between rounded-lg bg-secondary px-3 py-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-[var(--magenta)] shrink-0" />
                    <span className="text-sm font-medium truncate">{s.name}</span>
                    <span className="text-xs font-mono-x text-muted-foreground shrink-0">{s.time.toFixed(1)}s</span>
                  </div>
                  <button data-testid={`sfx-remove-${s.id}`} onClick={() => removeSfx(s.id)} className="text-muted-foreground hover:text-destructive">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
