#!/usr/bin/env bash
#
# Сборка и подготовка окружения Keitaro Wrapper (Linux / macOS / Git Bash).
#
# Скрипт создаёт виртуальное окружение .venv, устанавливает зависимости из
# requirements.txt, при необходимости создаёт .env из .env.example, применяет
# миграции Alembic и (опционально) запускает приложение.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN=0
RELOAD=0
RECREATE=0
SKIP_MIGRATIONS=0
PORT=8001
BIND_HOST="127.0.0.1"

usage() {
    cat <<'EOF'
Сборка и подготовка окружения Keitaro Wrapper.

Использование: ./build.sh [опции]

Опции:
  --run               после сборки запустить сервер (uvicorn)
  --reload            запустить uvicorn с автоперезагрузкой (вместе с --run)
  --recreate          удалить и заново создать .venv
  --skip-migrations   не применять миграции Alembic
  --port <номер>      порт приложения (по умолчанию 8001)
  --host <адрес>      адрес привязки сервера (по умолчанию 127.0.0.1)
  -h, --help          показать эту справку
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run) RUN=1 ;;
        --reload) RELOAD=1 ;;
        --recreate) RECREATE=1 ;;
        --skip-migrations) SKIP_MIGRATIONS=1 ;;
        --port)
            [[ $# -ge 2 ]] || { echo "Ошибка: --port требует значение." >&2; exit 1; }
            PORT="$2"
            shift
            ;;
        --host)
            [[ $# -ge 2 ]] || { echo "Ошибка: --host требует значение." >&2; exit 1; }
            BIND_HOST="$2"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестная опция: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

if [[ -t 1 ]]; then
    C_CYAN=$'\033[36m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_RESET=$'\033[0m'
else
    C_CYAN=""
    C_GREEN=""
    C_YELLOW=""
    C_RESET=""
fi

step() { printf '\n%s==> %s%s\n' "$C_CYAN" "$1" "$C_RESET"; }
ok()   { printf '    %s%s%s\n' "$C_GREEN" "$1" "$C_RESET"; }
warn() { printf '    %s%s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }

step "Проверка окружения"
ok "Папка проекта: $SCRIPT_DIR"

PYTHON=""
for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "Ошибка: не найден Python 3.11+. Установите Python и повторите." >&2
    exit 1
fi
ok "$("$PYTHON" --version 2>&1)"

VENV_DIR=".venv"

if [[ "$RECREATE" -eq 1 && -d "$VENV_DIR" ]]; then
    step "Удаление существующего .venv"
    rm -rf "$VENV_DIR"
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
    VENV_PY="$VENV_DIR/bin/python"
elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
    VENV_PY="$VENV_DIR/Scripts/python.exe"
else
    step "Создание виртуального окружения .venv"
    "$PYTHON" -m venv "$VENV_DIR"
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        VENV_PY="$VENV_DIR/bin/python"
    elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
        VENV_PY="$VENV_DIR/Scripts/python.exe"
    else
        echo "Ошибка: не удалось найти python в $VENV_DIR." >&2
        exit 1
    fi
    ok ".venv создано"
fi

step "Обновление pip"
"$VENV_PY" -m pip install --quiet --disable-pip-version-check --upgrade pip

step "Установка зависимостей"
"$VENV_PY" -m pip install --disable-pip-version-check -r requirements.txt
ok "Зависимости установлены"

if [[ ! -f .env && -f .env.example ]]; then
    step "Создание .env из .env.example"
    cp .env.example .env
    warn "Укажите KEITARO_URL и KEITARO_API_KEY в .env или через страницу /admin."
fi

if [[ "$SKIP_MIGRATIONS" -eq 0 ]]; then
    step "Применение миграций Alembic"
    ALEMBIC_BIN="$VENV_DIR/bin/alembic"
    if [[ ! -x "$ALEMBIC_BIN" ]]; then
        ALEMBIC_BIN="$VENV_DIR/Scripts/alembic.exe"
    fi

    if [[ -x "$ALEMBIC_BIN" ]]; then
        ALEMBIC_CMD=("$ALEMBIC_BIN")
    else
        ALEMBIC_CMD=("$VENV_PY" -m alembic)
    fi

    if "${ALEMBIC_CMD[@]}" upgrade head; then
        ok "Схема БД актуальна"
    else
        warn "Миграции не применились."
        warn "Если база уже создана, это нормально: при старте приложение выполнит create_all()."
    fi
else
    ok "Миграции пропущены (--skip-migrations)"
fi

if [[ "$RUN" -eq 1 ]]; then
    step "Запуск приложения: http://$BIND_HOST:$PORT"
    printf '    Остановка: Ctrl+C\n'

    UVICORN_ARGS=(-m uvicorn app.main:app --host "$BIND_HOST" --port "$PORT")
    if [[ "$RELOAD" -eq 1 ]]; then
        UVICORN_ARGS+=(--reload)
    fi

    exec "$VENV_PY" "${UVICORN_ARGS[@]}"
fi

step "Сборка завершена"
printf '%sЗапустить сервер:%s\n' "$C_GREEN" "$C_RESET"
printf '    ./build.sh --run\n'
printf '    (или: %s -m uvicorn app.main:app --host %s --port %s)\n' "$VENV_PY" "$BIND_HOST" "$PORT"
printf '\n'
printf 'После запуска откройте http://%s:%s/admin и укажите Keitaro URL и Admin API key.\n' "$BIND_HOST" "$PORT"
