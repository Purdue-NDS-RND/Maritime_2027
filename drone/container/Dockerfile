# CPU-only development/replay image. This is not a validated Jetson GPU image.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/
WORKDIR /app/drone
RUN uv venv --python /usr/local/bin/python /opt/perception-venv
COPY requirements.txt requirements-test.txt ./
RUN uv pip install --python /opt/perception-venv/bin/python --no-cache -r requirements-test.txt
COPY . .
RUN uv pip install --python /opt/perception-venv/bin/python --no-cache --no-deps .
CMD ["uv", "run", "--no-project", "--python", "/opt/perception-venv/bin/python", "python", "-m", "perception_synthetic.demo", "--adapter", "synthetic", "--scenario", "stationary", "--output", "/output/run"]
