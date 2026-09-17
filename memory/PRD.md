# Shitpost Studio — PRD

## Original problem statement
Kullanıcı yalnızca bir ses dosyası yükleyerek tamamen otomatik, YouTube tarzı, hızlı tempolu,
komik/shitpost bir video üretebilsin. Sistem sesi analiz eder, konuşmayı yazıya döker, anlam
bloklarına ayırır, uygun internet görselleri/GIF/meme/B-roll ve SFX'leri zamanlamayla yerleştirir,
altyazı üretir, timeline'ı editörde gösterir, kullanıcı düzenler ve MP4 render alır.

### Kritik kısıt (kullanıcı)
- **EMERGENT_LLM_KEY / Universal Key KULLANILMAYACAK.** Tüm AI (LLM + STT) ve medya servisleri
  kullanıcının KENDİ doğrudan API key'leriyle bağlanır. Proje Emergent dışına taşınınca aynı env
  değişkenleriyle çalışmalı.

## Architecture
- **Frontend:** React (CRACO) + Tailwind + shadcn/ui + framer-motion. Views: Upload → Analyzing → Editor.
- **Backend:** FastAPI (`/api`), MongoDB (job store). Threaded worker (sync pymongo) for
  transcription/analysis and rendering; FastAPI (motor) for API.
- **Pipeline:** `providers/` (stt=AssemblyAI, llm=Gemini, media=Pexels+Giphy) + `pipeline/`
  (analyze → timeline → render[ffmpeg] + sfx library).
- **Storage:** portable `STORAGE_DIR` (pod-local in preview; mount a volume on deploy). FFmpeg is a system dep.

## External services (user's own keys, in backend/.env)
- `ASSEMBLYAI_API_KEY` — STT (word-level timestamps)
- `GEMINI_API_KEY` + `GEMINI_MODEL=gemini-3.5-flash` — meaning-block analysis + edit decisions
- `PEXELS_API_KEY` — image + video B-roll
- `GIPHY_API_KEY` — reaction GIFs/memes

## Implemented (2026-06)
- Audio upload with mode (normal/fast/shitpost) + format (youtube/shorts/square)
- AssemblyAI transcription with word timings
- Gemini analysis → contextual segments with visual_type/effect/SFX/emphasis decisions (mode-aware density)
- Pexels/Giphy asset resolution with fallbacks + naive fallback segmentation if LLM fails (retry+model fallback on 503)
- Timeline builder (contiguous visuals, caption lines, SFX markers) + 12 synthesized royalty-free SFX
- FFmpeg render: Ken Burns/zoom/pan/shake per clip, mode-based transitions, burned ASS captions, SFX mixing → H.264+AAC MP4
- Editor UI: live preview (effects+captions+SFX playback), transport/scrubber, 5-layer timeline,
  Inspector (clip regenerate, media browser replace, effect change, caption style, SFX add/remove), render overlay + download
- All 4 APIs verified with real requests; full E2E tested (backend 12/12, frontend 100%)

## Backlog / next
- P1: word-level caption highlighting (karaoke) in render
- P1: background music layer (needs a music source/provider)
- P2: per-clip manual trim/drag on timeline; multi-select regenerate for a time range
- P2: render queue for concurrent jobs; deploy with persistent volume for STORAGE_DIR
- P2: additional providers (Unsplash/Pixabay/Tenor) behind the existing modular provider interface
