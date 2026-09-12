# ATLAS -- container image for the Streamlit dashboard.
#
# This is optional: every "Usage" instruction in README.md works without
# Docker. It exists for a reproducible, one-command deployment target
# (e.g. a shared demo machine) once the core application already works
# locally -- see docs/architecture.md's phase roadmap for why Docker was
# deliberately deferred until last.
FROM python:3.11-slim

WORKDIR /app

# System deps: none beyond what pip needs for scientific Python wheels on
# slim Debian. Kept minimal to keep the image small and CPU-only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: the spaCy small English model (Phase 6). If this fails (e.g.
# no network at build time), ATLAS still works via its regex baseline --
# see docs/defense_questions.md Phase 6 section.
RUN python -m spacy download en_core_web_sm || true

COPY . .

RUN mkdir -p data/raw data/processed data/synthetic

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
