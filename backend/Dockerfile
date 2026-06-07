FROM python:3.12-slim-bookworm

ARG APT_DEBIAN_MIRROR=http://mirrors.tencentyun.com/debian
ARG APT_DEBIAN_SECURITY_MIRROR=http://mirrors.tencentyun.com/debian-security
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /app

RUN sed -i \
        -e "s|http://deb.debian.org/debian|${APT_DEBIAN_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian-security|${APT_DEBIAN_SECURITY_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
