FROM python:3.11-slim
WORKDIR /app
COPY services/websocket-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/websocket-gateway /app
ENV PORT=8000
CMD ["python", "app.py"]
