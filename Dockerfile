FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

# Flaskアプリ(app.py)をgunicornで起動
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 app:app