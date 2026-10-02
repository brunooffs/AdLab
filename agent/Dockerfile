# Python 3.11, matching producer/ — not a forced constraint here (unlike
# producer's genuine kafka-python requirement), just kept consistent across
# the project's Python services rather than tracking a third version pin.
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    google-genai==2.27.0 \
    requests==2.34.2
COPY analyst.py ./
CMD ["python", "analyst.py"]
