FROM python:3.11-alpine
RUN pip install --no-cache-dir psycopg2-binary
WORKDIR /app
COPY server.py .
CMD ["python", "server.py"]
