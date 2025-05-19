#!/bin/bash
# setup.sh - Script para configurar o ambiente do projeto automaticamente.

# Variáveis
LOG_FILE="setup.log"
LOG_DIR="logs"
PYTHON_ENV_DIR="venv"

# Função para logar mensagens
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Função para verificar se um programa está instalado
check_installed() {
    if ! command -v "$1" &> /dev/null; then
        log_message "$1 não está instalado. Instalando..."
        return 1
    fi
    log_message "$1 já está instalado."
    return 0
}

log_message "Iniciando configuração do sistema."

# Garantir que o diretório de logs exista
[ -d "$LOG_DIR" ] || mkdir "$LOG_DIR"
log_message "Diretório de logs configurado em: $LOG_DIR"

# Atualizando e instalando dependências do sistema
log_message "Atualizando pacotes do sistema..."
sudo apt update -y && sudo apt upgrade -y >> "$LOG_FILE" 2>&1

SYSTEM_PACKAGES=(
    python3
    python3-pip
    python3-venv
    git
    curl
    wget
    net-tools
    build-essential
)

log_message "Verificando pacotes do sistema..."
for package in "${SYSTEM_PACKAGES[@]}"; do
    check_installed "$package" || sudo apt install -y "$package" >> "$LOG_FILE" 2>&1
done

# Criando ambiente virtual Python
log_message "Configurando ambiente virtual Python..."
if [ ! -d "$PYTHON_ENV_DIR" ]; then
    python3 -m venv "$PYTHON_ENV_DIR"
    log_message "Ambiente virtual criado em: $PYTHON_ENV_DIR"
else
    log_message "Ambiente virtual já existe em: $PYTHON_ENV_DIR"
fi
source "$PYTHON_ENV_DIR/bin/activate"

# Atualizando pip
log_message "Atualizando pip..."
pip install --upgrade pip >> "$LOG_FILE" 2>&1

# Instalando dependências Python
PYTHON_DEPENDENCIES=(
    flask
    requests
    python-telegram-bot
    tweepy
    openai
    python-dotenv
)
log_message "Instalando bibliotecas Python..."
for package in "${PYTHON_DEPENDENCIES[@]}"; do
    if ! pip show "$package" &> /dev/null; then
        pip install "$package" >> "$LOG_FILE" 2>&1
        log_message "$package instalado."
    else
        log_message "$package já está instalado."
    fi
done

log_message "Dependências Python instaladas."

log_message "Configuração do sistema concluída."
log_message "Para ativar o ambiente Python, use 'source $PYTHON_ENV_DIR/bin/activate'."
