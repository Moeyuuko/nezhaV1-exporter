FROM python:3.10-slim

WORKDIR /app

#国内pip源 选一个
# RUN pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple && pip install websockets aiohttp
RUN pip install websockets aiohttp

COPY nezha-exporter.py /app/

CMD ["python", "nezha-exporter.py"]
