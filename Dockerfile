FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    COURTIQ_ENV=production \
    COURTIQ_ALLOW_DEMO=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY outputs/tennis-ai-app/index.html outputs/tennis-ai-app/app.js outputs/tennis-ai-app/styles.css outputs/tennis-ai-app/responsive-fixes.css ./outputs/tennis-ai-app/
COPY outputs/tennis-ai-app/favicon.svg outputs/tennis-ai-app/robots.txt ./outputs/tennis-ai-app/
COPY outputs/tennis-ai-app/js ./outputs/tennis-ai-app/js
COPY outputs/tennis-ai-app/assets/player-stats.js ./outputs/tennis-ai-app/assets/player-stats.js
COPY output/models/courtiq_model_atp.json output/models/courtiq_model_wta.json ./output/models/

RUN useradd --create-home --uid 10001 courtiq \
    && mkdir -p /tmp/matplotlib \
    && chown -R courtiq:courtiq /tmp/matplotlib \
    && chown -R courtiq:courtiq /app
USER courtiq

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').getenv('PORT', '8000') + '/api/health', timeout=4)"

CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
