# Bonsai Ternary — llama.cpp Docker stack

Run PrismML's [Ternary Bonsai](https://huggingface.co/prism-ml) models (1.58-bit / 2-bit GGUF) locally via the [PrismML llama.cpp fork](https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b10709-9a9394a), served as an OpenAI-compatible API with a built-in web UI.

## Stack

| Service | Image | Port | Notes |
| --- | --- | --- | --- |
| `proxy` | `bonsai-proxy` | 8080 (host) | Fixes sampler params rejected by the llama.cpp schema (e.g. `dry_penalty_last_n: -1` sent by Open WebUI) |
| `llama-server` | `bonsai-llama-server` | 8081 (internal) | CUDA build of the PrismML fork; GPU offload via `--n-gpu-layers` |

## Prerequisites

- Docker Desktop with **NVIDIA Container Toolkit**
- An NVIDIA GPU (developed/tested on a laptop RTX 4xxx, 8 GB VRAM)
- `hf` CLI (`pip install -U "huggingface_hub[cli]"`)

## Quick start

```powershell
Copy-Item .env.example .env

# Download the model (7.2 GB PQ2_0 pack, or swap to PTQ1_0 for a faster 5.9 GB)
hf download prism-ml/Ternary-Bonsai-2-27B-gguf Ternary-Bonsai-2-27B-PQ2_0.gguf --local-dir models

docker compose up -d --build
```

Then:

- Web UI: http://localhost:8080
- API: `POST /v1/chat/completions` on http://localhost:8080/v1
- Health: `GET /health`

Example call:

```powershell
$b = @{
  model    = "Ternary-Bonsai-2-27B"
  messages = @(@{ role = "user"; content = "Hello" })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://localhost:8080/v1/chat/completions -Method Post -ContentType "application/json" -Body $b
```

## Configuration (`.env`)

| Variable | Default | Description |
| --- | --- | --- |
| `LLAMA_RELEASE` | `prism-b10709-9a9394a` | PrismML fork release tag |
| `LLAMA_TARGET` | `linux-cuda-12.4-x64` | Pre-built asset: CUDA (12.4/12.8/13.3), `ubuntu-x64`, `ubuntu-vulkan-x64`, ... |
| `BASE_IMAGE` | `nvidia/cuda:12.4.1-runtime-ubuntu22.04` | Base image; must match the CUDA version of the asset |
| `MODEL_FILE` | `Ternary-Bonsai-2-27B-PQ2_0.gguf` | GGUF filename inside `./models/` |
| `PORT` | `8080` | Host port for the API/UI |
| `CONTEXT_LENGTH` | `8192` | KV cache size; keep modest on 8 GB GPUs |
| `NGPU` | `99` | Layers offloaded to GPU; lower it (e.g. 40–60) on CUDA OOM |

### Model options

Larger models than your VRAM can hold will partially offload to CPU. Trade-offs for the 27B on 8 GB:

- `PQ2_0` (7.2 GB) — recommended, higher quality, slower
- `PTQ1_0` (5.9 GB) — faster, slightly lower quality

Vision (multimodal): also download `Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf` and append `--mmproj /models/<file>` to the `llama-server` command in `docker-compose.yml`.

### CPU-only fallback

Set `LLAMA_TARGET=ubuntu-x64`, `BASE_IMAGE=ubuntu:22.04`, and remove the `deploy` block from `llama-server` in `docker-compose.yml`.

## How the proxy works

Open WebUI (and other clients) send `dry_penalty_last_n: -1` ("penalize all tokens"), which the llama.cpp server schema rejects with HTTP 400. The proxy:

1. Proactively rewrites known negative sentinels to valid values (`dry_penalty_last_n`, `repeat_last_n`, `dry_allowed_length`).
2. For any *other* field rejected with a `Field 'X': Value must be between ...` error, clamps the offending value to its minimum and retries the request transparently.

Point any OpenAI-compatible client at `http://localhost:8080/v1`.

## Troubleshooting

- **CUDA out of memory** — lower `NGPU` in `.env` (e.g. 60) and/or `CONTEXT_LENGTH` (e.g. 4096), then `docker compose up -d`.
- **`libcuda.so.1` errors if running without `--gpus`** — expected; the server needs the NVIDIA runtime. The compose file passes the GPU via `deploy.resources.reservations.devices`.
- **Slow generation** — the 27B does not fit in 8 GB VRAM; expect ~9 t/s with partial offload. A Bonsai 4B/8B fits fully and runs several times faster.

## Repository layout

```
Dockerfile            CUDA llama-server image (downloads fork release binary)
docker-compose.yml    proxy + llama-server stack
proxy/
  Dockerfile          python:3.12-alpine image
  proxy.py            reverse proxy with sampler-param fixing
.env.example          configuration template (copy to .env)
models/               mount point for GGUF weights (gitignored)
```