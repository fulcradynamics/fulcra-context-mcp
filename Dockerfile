FROM python:3.14-slim-bookworm

ARG FULCRA_VERSION="unknown"
ENV FULCRA_VERSION=${FULCRA_VERSION}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN useradd -m -u 31337 service

RUN apt-get -y update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y upgrade \
    && apt-get install -y locales \
    && rm -rf /var/lib/apt/lists/* \
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
    && export LANG=en_US.utf8

ENV LANG en_US.utf8

USER service

COPY --chown=31337:31337 . /app

WORKDIR /app
RUN uv sync --locked


ENTRYPOINT ["uv"]
CMD ["run", "fulcra-context-mcp"]

