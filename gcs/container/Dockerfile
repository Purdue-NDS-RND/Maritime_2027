FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY gcs/frontend/package*.json ./
RUN npm ci
COPY gcs/frontend/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY gcs/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY gcs/app /app/app
COPY --from=frontend /frontend/dist /app/static
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8080"]
