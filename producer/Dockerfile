# Click event producer. Pinned to Python 3.11 because kafka-python==2.0.2
# fails to import on Python 3.12+ (No module named 'kafka.vendor.six.moves').
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    kafka-python==2.0.2 \
    psycopg2-binary==2.9.9 \
    sqlalchemy==2.0.30 \
    python-dotenv==1.0.1
COPY producer.py db.py ./
CMD ["python", "producer.py", "--events", "500", "--rate", "5"]
