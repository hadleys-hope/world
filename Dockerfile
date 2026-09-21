FROM python:3.12-slim
WORKDIR /app
# dependencies first: this layer is rebuilt only when this line changes
RUN pip install --no-cache-dir numpy paho-mqtt
# code last: a code change rebuilds only this layer, about a second
COPY hadleys_hope.py houses_runtime.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python3", "hadleys_hope.py", "--speed", "20"]
