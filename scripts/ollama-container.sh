#!/bin/sh
# Ollama próprio do ditado: contêiner jrwhisper-ollama em 127.0.0.1:11435, GPU e reinício automático
# (sobe com o Docker no boot). Independe de outros Ollama da máquina (ex.: o do Moorcheh/Hermes na 11434).
# Idempotente: se o contêiner já existe, só garante que está rodando.
NAME=jrwhisper-ollama
PORT=11435

command -v docker >/dev/null 2>&1 || { echo "Docker ausente: IA local do ditado fica sem Ollama próprio"; exit 0; }

if docker container inspect "$NAME" >/dev/null 2>&1; then
    docker start "$NAME" >/dev/null && echo "$NAME já existe (porta $PORT)"
    exit 0
fi

# Reaproveita os modelos já baixados (volume do Moorcheh, se existir): nada para baixar de novo.
# Volume em uso por um contêiner rodando não pode ser apagado (nem por "compose down -v").
VOLUME=jrwhisper_ollama
docker volume inspect compose_ollama_data >/dev/null 2>&1 && VOLUME=compose_ollama_data

GPU="--device nvidia.com/gpu=all"  # CDI (Docker 25+); sem placa NVIDIA, roda na CPU
docker info 2>/dev/null | grep -q "nvidia.com/gpu" || GPU=""

docker run -d --name "$NAME" --restart unless-stopped $GPU \
    -p "127.0.0.1:$PORT:11434" -v "$VOLUME:/root/.ollama" \
    -e OLLAMA_KEEP_ALIVE=30m \
    ollama/ollama:latest >/dev/null || exit 1
echo "$NAME criado (porta $PORT, modelos em $VOLUME)"
[ "$VOLUME" = jrwhisper_ollama ] && echo "Baixe o modelo: docker exec $NAME ollama pull qwen2.5"
exit 0
