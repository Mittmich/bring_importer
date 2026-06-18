FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -e .

COPY . .

EXPOSE 8001

CMD ["python3", "run.py"]
