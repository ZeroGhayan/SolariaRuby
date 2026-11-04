#!/usr/bin/env bash
# setup.sh - prepara o Solaria Ruby (no Orange Pi: /home/orangepi/dgsManager/SolariaRuby) no Orange Pi 5 / Raspberry Pi (ARM64) ou qualquer Linux.
# Não faz "apt upgrade"; instala só o mínimo e cria um venv.
set -euo pipefail
cd "$(dirname "$0")/.."

need=()
for pkg in python3 python3-venv python3-pip; do
    dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
done
if [ ${#need[@]} -gt 0 ]; then
    echo "Instalando: ${need[*]}"
    sudo apt-get update && sudo apt-get install -y "${need[@]}"
fi

[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    cp env.example .env
    chmod 600 .env
    echo "Criei .env a partir do env.example — preencha as chaves (DRY_RUN=true por padrão)."
fi
mkdir -p logs
echo "Pronto. Teste com: $(pwd)/venv/bin/python main.py"
echo "Serviço: use o serviço systemd que já existe e aponte-o para $(pwd) (veja o README)."
