FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . .
WORKDIR /srv/backend
ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
