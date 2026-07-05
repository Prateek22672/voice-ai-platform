FROM python:3.11-slim
WORKDIR /app
COPY services/recording-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/recording-service /app
ENV PORT=8005
CMD ["python", "app.py"]
