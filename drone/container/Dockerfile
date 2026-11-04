# CPU-only development/replay image. This is not a validated Jetson GPU image.
FROM python:3.12-slim
WORKDIR /app/drone
COPY requirements.txt requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements-test.txt
COPY . .
RUN pip install --no-cache-dir --no-deps .
CMD ["python", "-m", "perception_synthetic.demo", "--adapter", "synthetic", "--scenario", "stationary", "--output", "/output/run"]
