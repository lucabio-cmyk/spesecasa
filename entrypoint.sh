#!/usr/bin/env sh
# Entrypoint di avvio: rende osservabile ogni fase del boot, così in caso di
# stallo (DB irraggiungibile, porta sbagliata) i log mostrano dove ci si ferma.
set -e

PORT="${PORT:-8000}"

echo "[boot] avvio container — APP_ENV=${APP_ENV:-unset} PORT=${PORT}"
echo "[boot] esecuzione migrazioni (alembic upgrade head)..."
alembic upgrade head
echo "[boot] migrazioni completate."
echo "[boot] avvio uvicorn su 0.0.0.0:${PORT} (imposta la stessa porta nel Generate Domain di Railway)"

# --proxy-headers / --forwarded-allow-ips: necessari dietro il proxy di Railway.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
