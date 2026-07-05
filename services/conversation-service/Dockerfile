FROM python:3.11-slim
WORKDIR /app
COPY services/conversation-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/conversation-service /app
ENV PORT=8003
CMD ["python", "app.py"]
