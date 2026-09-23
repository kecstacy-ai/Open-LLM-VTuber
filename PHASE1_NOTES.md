# Phase 1 notes: Desktop AI Companion on kecstacy

Date: 2026-09-24 · Branch: `phase-1` · Upstream base: `992309c` (Open-LLM-VTuber v1.2.1)

## Result
All "done when" checks passed, tested by Bobby on kecstacy:
- Voice in → reply out with lip-sync in pet mode ✅
- Mandarin ✅ and English ✅
- Voice interruption without headphones ✅
- Pet mode: transparent, always-on-top, mouse-passthrough toggle (tray/right-click) ✅
- No secrets in git (key is `${OPENROUTER_API_KEY}` in config, substituted at load)

## Machine
- Windows 11 (NT 10.0.26200), RTX 2070 SUPER 8 GB, driver 617.14
- No system CUDA toolkit: CUDA 12 cuBLAS + cuDNN 9 come from pip wheels inside `.venv`

## Installed (winget, user scope)
| Tool | Version |
|---|---|
| uv | 0.12.18 |
| ffmpeg (Gyan) | 9.0.2 |
| GitHub CLI | 2.101.0 |
| 1Password CLI | 2.39.0 |
| git / node / npm (pre-existing) | 2.55.0 / 24.20.0 / 11.19.0 |

## Python env (`uv sync` + `uv add`)
Python 3.10.21 (uv-managed; system 3.14 is too new for `requires-python <3.13`)
- faster-whisper 1.2.1, ctranslate2 4.8.2
- nvidia-cublas-cu12, nvidia-cudnn-cu12 9.10.2.21 (added to `pyproject.toml`, non-macOS only)
- sherpa-onnx 1.10.46, onnxruntime 1.23.2 (CPU)
- torch 2.10.0+cpu (not used by the chosen engines; left as upstream resolves it)

## Config choices (`conf.yaml`, gitignored; tracked copy at `config_templates/conf.kecstacy.yaml`)
- **LLM**: `openai_compatible_llm` → `https://openrouter.ai/api/v1`, model `qwen/qwen3-235b-a22b-2507`
  (non-thinking, ~0.5 s to first reply, $0.09 in / $0.35 out per 1M tokens). Dev spend is cents/day.
  Rejected `qwen/qwen3.7-flash`: it's a reasoning model, spent the whole token budget thinking and returned empty content.
- **ASR**: faster-whisper `large-v3-turbo` (local copy at `models/whisper/large-v3-turbo`, SHA-256 verified),
  `device: cuda`, `compute_type: float16`, language auto-detect, bilingual initial prompt.
  (Config schema only allows int8/float16/float32.)
- **TTS**: sherpa-onnx `vits-melo-tts-zh_en` (Mandarin + English, single speaker `sid: 0`), CPU, 4 threads.
  Test: 3 s of audio in ~1.2 s (incl. warm-up).
- **VAD**: server `vad_model: null` (upstream default). Interruption runs on the client's VAD + browser echo cancellation.
- **Character**: `Lin (林)`, adult woman in late twenties; bilingual, replies in the user's language; says she's an AI when asked;
  no guilt-tripping, no pressure to pay. `human_name: Boss`.
- **Live2D**: `mao_pro` sample model as a **dev-only placeholder**. It's under the Live2D sample licence, so it must not ship in any paid build.

## How to run
```powershell
# server (reads OPENROUTER_API_KEY from your user env; adds CUDA DLLs from .venv to PATH)
powershell -ExecutionPolicy Bypass -File scripts\start-kecstacy.ps1
# desktop client (separate repo: ..\Open-LLM-VTuber-Web)
cmd /c "set NODE_ENV=development& npm run dev"
```
Right-click the character → Pet Mode. Tray → Toggle Mouse Passthrough.

## VRAM
- Idle desktop baseline: ~1.8 GB
- Server running (Whisper large-v3-turbo fp16 loaded) + Electron: ~4.3 GB of 8 GB
- Whisper therefore takes about 2.4 GB, leaving roughly 3.7 GB free

## Open issues
1. **TTS is on CPU, not GPU.** The sherpa-onnx CUDA wheels documented upstream pin onnxruntime-gpu 1.17.1 (CUDA 11.8 / cuDNN 8),
   which clashes with CTranslate2's CUDA 12 / cuDNN 9. CPU latency is acceptable for now. Options: find a sherpa-onnx CUDA 12 wheel,
   or move to a GPU TTS (CosyVoice2 / GPT-SoVITS as a separate service) in Phase 2 alongside the custom voice.
2. **Global `NODE_ENV=production`** on kecstacy makes npm skip devDependencies. Worked around per-process
   (`set NODE_ENV=development`); the system variable was left alone.
3. **Flaky TLS on kecstacy downloads** ("bad record MAC" in both Python and Node). ProtonVPN was running; likely cause.
   Large downloads needed curl with resume. Pause the VPN for big pulls.
4. Electron client is running in dev mode (`npm run dev`), not packaged. Packaging comes in Phase 3.
5. The Electron repo (`Open-LLM-VTuber-Web`) is cloned from upstream, not forked, since it's unmodified. Fork it once Phase 2 changes it.
6. HF Hub symlinks are unsupported without Windows Developer Mode, which only matters for cache disk usage.
7. MCP tools `time` and `ddg-search` are enabled (upstream default). Review before any paid or public build.
