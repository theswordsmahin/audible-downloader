FROM python:alpine3.20

LABEL version="2024-08-22"
LABEL description="Downloads and converts audiobooks \
from audible to m4b and saves them in the audiobooks directory"

WORKDIR /app

ENV AUDIBLE_CONFIG_DIR=/config

RUN mkdir -p /audiobooks /config /app

RUN apk update \
	&& apk add --update --no-cache ffmpeg

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apk del gcc musl-dev python3-dev

EXPOSE 5000

COPY app/ /app/
CMD ["python", "/app/webui.py"]