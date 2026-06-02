FROM python:3.11-slim

# libraqm + fribidi/harfbuzz give the best Arabic shaping for Pillow; an Arabic
# system font is a safety net (the repo also bundles Tajawal). ffmpeg itself is
# provided by the imageio-ffmpeg wheel, so no system ffmpeg is required.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libraqm0 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV LOG_LEVEL=INFO

# One run by default; use `schedule` to run continuously.
#   docker run --rm -e ANTHROPIC_API_KEY=... -v "$PWD/output:/app/output" <image>
#   docker run --rm ... <image> python main.py schedule
CMD ["python", "main.py", "run"]
