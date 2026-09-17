import { useMemo } from "react";

function pickClip(visuals, t) {
  if (!visuals?.length) return null;
  for (const c of visuals) if (t >= c.start && t < c.end) return c;
  return t <= visuals[0].start ? visuals[0] : visuals[visuals.length - 1];
}

export default function Preview({ job, currentTime, playing }) {
  const tl = job.timeline;
  const canvas = tl.canvas;
  const style = job.caption_style || {};
  const clip = useMemo(() => pickClip(tl.visuals, currentTime), [tl.visuals, currentTime]);
  const caption = useMemo(
    () => (tl.captions || []).find((c) => currentTime >= c.start && currentTime <= c.end),
    [tl.captions, currentTime]
  );

  const isVideo = clip?.url && clip.url.endsWith(".mp4");
  const dur = clip ? Math.max(0.3, clip.end - clip.start) : 1;
  const effect = clip?.effect || "kenburns";
  const animStyle =
    effect === "shake"
      ? { animationPlayState: playing ? "running" : "paused" }
      : { animationDuration: `${dur}s`, animationPlayState: playing ? "running" : "paused" };

  const alignItems = style.position === "top" ? "flex-start" : style.position === "center" ? "center" : "flex-end";

  const captionText = caption ? (style.uppercase ? caption.text.toUpperCase() : caption.text) : "";
  const fontScale = (style.size || 54) / 1080 * 100; // cqh

  return (
    <div className="w-full flex items-center justify-center">
      <div
        className="relative bg-black rounded-xl overflow-hidden w-full"
        style={{ aspectRatio: `${canvas.w}/${canvas.h}`, maxHeight: "62vh", containerType: "size" }}
        data-testid="preview-canvas"
      >
        {clip?.url ? (
          isVideo ? (
            <video
              key={clip.id}
              src={clip.url}
              className={`absolute inset-0 w-full h-full object-cover fx-${effect}`}
              style={animStyle}
              autoPlay
              loop
              muted
              playsInline
            />
          ) : (
            <img
              key={clip.id}
              src={clip.url}
              alt=""
              className={`absolute inset-0 w-full h-full object-cover fx-${effect}`}
              style={animStyle}
            />
          )
        ) : (
          <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-[#1a1a2e] to-[#533483]">
            <span className="font-mono-x text-xs text-white/50">no media</span>
          </div>
        )}

        {/* Caption overlay */}
        {style.enabled !== false && caption && (
          <div
            className="absolute inset-0 flex justify-center px-[6%] py-[7%] pointer-events-none"
            style={{ alignItems }}
          >
            <span
              className="caption-outline text-center leading-tight"
              style={{
                fontFamily: style.font || "DejaVu Sans",
                fontWeight: style.bold ? 800 : 500,
                fontSize: `${fontScale}cqh`,
                color: style.color || "#FFFFFF",
                WebkitTextStroke: `${(style.outline_width || 4) / 12}cqh ${style.outline_color || "#000000"}`,
                textShadow: "0 2px 8px rgba(0,0,0,0.5)",
              }}
            >
              {captionText}
            </span>
          </div>
        )}

        {/* Emphasis flash marker */}
        {clip?.emphasis && (
          <div className="absolute top-3 left-3 text-[10px] font-mono-x px-2 py-0.5 rounded bg-[var(--magenta)] text-white">
            EMPHASIS
          </div>
        )}
      </div>
    </div>
  );
}
