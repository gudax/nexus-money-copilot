FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi
COPY fleet/ fleet/
COPY service/ service/
COPY launcher.sh .
RUN chmod +x launcher.sh
ENV GOOGLE_GENAI_USE_VERTEXAI=1 \
    GOOGLE_CLOUD_LOCATION=global \
    PYTHONUNBUFFERED=1
CMD ["./launcher.sh"]
