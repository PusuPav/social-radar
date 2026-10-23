FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
VOLUME ["/data"]
WORKDIR /data
# Mount a folder containing watchlist.yaml and .env at /data
ENTRYPOINT ["social-radar"]
CMD ["run", "--every", "60"]
