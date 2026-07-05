FROM python:3.11-slim
WORKDIR /app
COPY services/analytics-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/analytics-service /app
ENV PORT=8006
CMD ["python", "app.py"]
