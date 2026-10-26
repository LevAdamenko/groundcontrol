FROM python:3.12-slim

RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app
RUN mkdir -p /data && chown user:user /home/user/app /data

COPY --chown=user:user pyproject.toml README.md LICENSE ./
COPY --chown=user:user groundcontrol/ ./groundcontrol/
COPY --chown=user:user fixtures/ ./fixtures/

USER user
RUN pip install --no-cache-dir .

ENV PATH="/home/user/.local/bin:${PATH}" \
    LIVE=1 PORT=7860 DATA_DIR=/data \
    GROUNDCONTROL_FIXTURES_DIR=/home/user/app/fixtures
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn groundcontrol.web:app --host 0.0.0.0 --port ${PORT:-7860} --no-access-log"]
