FROM python:3.11-slim
WORKDIR /app
COPY services/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/api-gateway /app
ENV PORT=8080
CMD ["python", "app.py"]
