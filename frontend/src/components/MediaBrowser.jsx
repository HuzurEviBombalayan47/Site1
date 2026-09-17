import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Search, Loader2, Check } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import api from "@/api";

const KINDS = [
  { id: "image", label: "Fotoğraf" },
  { id: "video", label: "Video" },
  { id: "gif", label: "GIF / Meme" },
];

export default function MediaBrowser({ open, onOpenChange, clip, jobId, onApply }) {
  const [kind, setKind] = useState("image");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(null);

  useEffect(() => {
    if (open && clip) {
      const initKind = clip.visual_type === "text" ? "image" : clip.visual_type;
      setKind(initKind);
      setQuery(clip.search_query || clip.topic || "");
      runSearch(clip.search_query || clip.topic || "", initKind);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const runSearch = async (q, k) => {
    if (!q?.trim()) return;
    setLoading(true);
    try {
      const res = await api.searchMedia(k, q);
      setResults(res);
    } catch (e) {
      toast.error("Arama başarısız: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const apply = async (item) => {
    setApplying(item.url);
    try {
      const updated = await api.patchJob(jobId, {
        clip: {
          id: clip.id,
          url: item.url,
          preview: item.preview,
          visual_type: item.type,
          provider: item.provider,
        },
      });
      onApply(updated);
      toast.success("Görsel değiştirildi");
      onOpenChange(false);
    } catch (e) {
      toast.error("Uygulanamadı: " + e.message);
    } finally {
      setApplying(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-card border-border text-foreground" data-testid="media-browser">
        <DialogHeader>
          <DialogTitle className="font-display">Medya kütüphanesi</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Bu görsel için alternatif fotoğraf, video veya GIF ara ve seç.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2 mb-3">
          {KINDS.map((k) => (
            <button
              key={k.id}
              data-testid={`browser-kind-${k.id}`}
              onClick={() => { setKind(k.id); runSearch(query, k.id); }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                kind === k.id ? "bg-[var(--lime)] text-black" : "bg-secondary text-muted-foreground hover:text-foreground"
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); runSearch(query, kind); }}
          className="flex gap-2 mb-4"
        >
          <Input
            data-testid="browser-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ara: elon musk, surprised reaction, mars..."
            className="bg-secondary border-border"
          />
          <Button type="submit" className="shrink-0" style={{ background: "var(--lime)", color: "#0b0b0f" }}>
            <Search className="w-4 h-4" />
          </Button>
        </form>

        <div className="h-[380px] overflow-y-auto">
          {loading ? (
            <div className="h-full grid place-items-center text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          ) : results.length === 0 ? (
            <div className="h-full grid place-items-center text-muted-foreground text-sm">Sonuç yok</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {results.map((item, i) => (
                <button
                  key={i}
                  data-testid={`browser-result-${i}`}
                  onClick={() => apply(item)}
                  className="relative aspect-video rounded-lg overflow-hidden border border-border hover:border-[var(--lime)] group"
                >
                  <img src={item.preview || item.url} alt="" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 grid place-items-center transition-opacity">
                    {applying === item.url ? (
                      <Loader2 className="w-6 h-6 animate-spin text-white" />
                    ) : (
                      <Check className="w-7 h-7 text-[var(--lime)]" />
                    )}
                  </div>
                  <span className="absolute top-1 left-1 text-[9px] font-mono-x px-1.5 py-0.5 rounded bg-black/60 text-white">{item.provider}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
