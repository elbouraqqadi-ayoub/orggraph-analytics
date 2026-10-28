FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY orgkg ./orgkg
RUN pip install --no-cache-dir '.[pdf]'
COPY config ./config
COPY evaluation ./evaluation
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "orgkg"]
CMD ["serve"]
