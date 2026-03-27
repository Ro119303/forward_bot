FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt update && apt install -y sqlite3 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip --default-timeout=600 install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . /app
WORKDIR /app
CMD ["python", "-u", "bot.py"]
