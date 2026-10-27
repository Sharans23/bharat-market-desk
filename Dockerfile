FROM node:22-bookworm-slim AS frontend
WORKDIR /build/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/index.html ui/vite.config.js ./
COPY ui/src ./src
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY india_trader ./india_trader
COPY data ./data
COPY examples ./examples
COPY docs ./docs
COPY LICENSE ./LICENSE
COPY --from=frontend /build/ui/dist ./ui/dist
COPY ui/THIRD-PARTY-NOTICES.txt ./ui/THIRD-PARTY-NOTICES.txt
CMD ["sh", "-c", "exec gunicorn 'india_trader.cloud:create_app()' --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 --error-logfile - --log-level warning"]
