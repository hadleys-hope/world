FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir numpy paho-mqtt
COPY hadleys_hope.py .
ENV DATA_DIR=/data
ENV PORT=8000
EXPOSE 8000
CMD ["python3", "hadleys_hope.py", "--speed", "20"]
