FROM python:3.10

LABEL Maintainer="gounux <contact@guilhemallaman.net>"

WORKDIR /app
COPY . /app

ENV MASTODON_INSTANCE https://mastodon.social
ENV MASTODON_ACCESS_TOKEN abcd
ENV OPENTRIPMAP_API_KEY abcd

RUN pip install poetry
RUN poetry install

ENTRYPOINT ["poetry", "run", "python", "prettymaps_bot.py"]
