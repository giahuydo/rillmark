FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 app && chown app:app /app
COPY --chown=app:app main.py ./
COPY --chown=app:app rillmark/ ./rillmark/
COPY --chown=app:app config/selection.json ./config/selection.json

USER app
ENTRYPOINT ["python"]
CMD ["main.py"]
