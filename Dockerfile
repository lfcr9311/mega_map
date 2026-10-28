# fmsnav: API + frontend num container so, tudo sob /map (ver deploy/README.md).

# ---- frontend
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- API
FROM python:3.12-slim
RUN useradd --create-home --uid 1000 fmsnav
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=web /web/dist ./frontend/dist
USER fmsnav
# o grafo nao vem do Git: volume ./data/build -> /data (make deploy-data)
ENV FMSNAV_GRAPH=/data/navgraph.json.gz \
    FMSNAV_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8001
CMD ["fmsnav", "serve", "--host", "0.0.0.0", "--port", "8001"]
