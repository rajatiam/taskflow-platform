FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py api.py run.py manage.py project.json ./
COPY backend ./backend
COPY --from=frontend /build/dist/portfolio/browser ./frontend/dist/portfolio/browser
RUN useradd --uid 10001 --create-home appuser && mkdir /app/data && chown appuser /app/data
USER appuser
ENV HOST=0.0.0.0 PORT=8101 PYTHONUNBUFFERED=1
EXPOSE 8101
CMD ["python", "run.py"]
