FROM python:3.12-slim

RUN apt update && apt install -y sqlite3

COPY requirements.txt .

RUN pip --default-timeout=600 install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . /app
WORKDIR /app
CMD ["python", "bot.py"]
