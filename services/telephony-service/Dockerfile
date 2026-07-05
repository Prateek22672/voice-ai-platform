FROM python:3.11-slim
WORKDIR /app
COPY services/telephony-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/telephony-service /app
ENV PORT=8004
CMD ["python", "ari_app.py"]
