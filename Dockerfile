FROM cr.yandex/mirror/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --timeout 120 \
    -r requirements.txt

COPY . .

RUN mkdir -p logs

CMD ["python", "-m", "src.main"]
