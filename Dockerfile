# Raqib — single-container image: build the React UI, then serve it with the
# FastAPI app (one process, same origin, WebSocket-capable). Recorded/demo mode
# needs no OCI credentials; set them as host env vars only for a private live run.

# ---- Stage 1: build the React workbench ----
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Stage 2: Python runtime serving the API + the built UI ----
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
# web/dist is gitignored/build-time, so copy it from the Node stage.
COPY --from=web /web/dist ./web/dist
# The host injects PORT (Render does); app.py binds 0.0.0.0:config.PORT.
EXPOSE 8117
CMD ["python", "app.py"]
