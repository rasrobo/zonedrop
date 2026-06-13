FROM python:3.12-alpine

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY zonedrop/ ./zonedrop/

RUN pip install --no-cache-dir ".[vault]"

ENTRYPOINT ["python3", "-m", "zonedrop"]
CMD ["--help"]
