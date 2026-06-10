FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
# Default: long-running loop. Voor cron-stijl: override met `python bot.py once`.
CMD ["python", "bot.py", "run"]
