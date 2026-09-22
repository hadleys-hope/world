FROM python:3.12-slim
WORKDIR /app
# Dependencies remain in a separately cached layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Both services use this image. All application assets are shipped with it.
COPY hadleys_hope.py houses_runtime.py ./
COPY hadleys/ ./hadleys/
COPY web/ ./web/
COPY vendor/ ./vendor/
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python3", "hadleys_hope.py", "--speed", "20"]
