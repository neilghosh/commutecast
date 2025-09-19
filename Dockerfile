FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy code and install Python deps
WORKDIR /app
COPY . .
RUN pip install --upgrade pip \
    && pip install -e .

# Metering (Azure Speech containers requirement)
ENV AZURE_SPEECH_KEY="<Your-Speech-Resource-Key>"
ENV AZURE_SPEECH_REGION="<Your-Region>"

EXPOSE 5000
CMD ["uvicorn", "vibevoice.api:app", "--host", "0.0.0.0", "--port", "5000"]

