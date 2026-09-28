# Bonsai (ternary) llama.cpp server – CUDA build
# Uses the PrismML fork pre-built binary:
#   https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b10709-9a9394a
ARG BASE_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04
FROM ${BASE_IMAGE}

ARG LLAMA_RELEASE=prism-b10709-9a9394a
ARG LLAMA_TARGET=linux-cuda-12.4-x64
ARG LLAMA_ASSET=llama-${LLAMA_RELEASE}-bin-${LLAMA_TARGET}.tar.gz

ENV MODEL_FILE=/models/Ternary-Bonsai-2-27B-PQ2_0.gguf

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Download the exact pre-built server from the PrismML fork release.
ADD https://github.com/PrismML-Eng/llama.cpp/releases/download/${LLAMA_RELEASE}/${LLAMA_ASSET} /tmp/llama-bin.tar.gz

RUN mkdir -p /opt/llama \
    && tar -xzf /tmp/llama-bin.tar.gz -C /opt/llama \
    && rm /tmp/llama-bin.tar.gz \
    && cp -a /opt/llama/llama-prism-*/. /opt/llama/ \
    && rm -rf /opt/llama/llama-prism-* \
    && cp -aL "$(find /opt/llama -type f -name llama-server | head -1)" /usr/local/bin/llama-server \
    && chmod +x /usr/local/bin/llama-server

ENV LD_LIBRARY_PATH=/opt/llama

WORKDIR /models

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/llama-server"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--jinja", "-c", "8192", "--n-gpu-layers", "99", "-m", "/models/Ternary-Bonsai-2-27B-PQ2_0.gguf"]