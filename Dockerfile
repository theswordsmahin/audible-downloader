FROM python:alpine3.20

LABEL version="2024-08-22"
LABEL description="Downloads and converts audiobooks \
from audible to m4b and saves them in the audiobooks directory"

WORKDIR /app

ENV AUDIBLE_CONFIG_DIR=/config

# Create directories with proper permissions
RUN mkdir -p /audiobooks /config /app /processing

RUN apk update \
	&& apk add --update --no-cache ffmpeg

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apk del gcc musl-dev python3-dev

# Create a non-root user and group
RUN addgroup -g 1000 audible && \
    adduser -D -u 1000 -G audible audible

# Set ownership of directories to the audible user
RUN chown -R audible:audible /audiobooks /config /app /processing

# Switch to non-root user
USER audible

EXPOSE 5000

COPY --chown=audible:audible app/ /app/
CMD ["python", "/app/webui.py"]