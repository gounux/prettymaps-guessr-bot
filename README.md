# Prettymaps guesser bot

This is a bot designed to post some quizz through [mastodon](https://mastodonpy.readthedocs.io/en/stable/) polls.

The polls offer several answers designating the location of a map image generated thanks to [prettymaps](https://github.com/marceloprates/prettymaps).

The center of the map image is a POI randomly found with [OpenTripMap](https://opentripmap.io/docs) and [nominatim geocoding](https://nominatim.org/).

## Setup

This bot uses poetry, that can be installed using `python3 -m pip install poetry`.

- install project's dependencies: `poetry install`
- install project's pre-commit hooks: `poetry run pre-commit install`

## Configure

Following environment variables must be set:

- `MASTODON_INSTANCE`: URL of the mastodon account that will toot
- `MASTODON_ACCESS_TOKEN`: token to interact with the mastodon account (can be created or retrieved from `Preferences` > `Development`)
- `OPENTRIPMAP_API_KEY`: token to interact with the mastodon account (can be created or retrieved from `Preferences` > `Development`)

## Run

Run the bot using following command:

```bash
poetry run python3 prettymaps_bot.py
```

Several options are available:

```bash
-h, --help            show this help message and exit
-c COUNTRY, --country COUNTRY
                    Country inside which random places are picked (default to 'random')
-n NB_PICKS, --nb_picks NB_PICKS
                    Number of available picks (between 2 and 4, default to 3)
-p PRESET, --preset PRESET
                    Prettymaps preset to use (default to 'random', available: barcelona,cb-bf-f,default,heerhugowaard,macao,minimal,tijuca)
-r RADIUS, --radius RADIUS
                    Radius (km) used to get an OpenTripMap place around a randomly created point
-ho HOURS, --hours HOURS
                    After how many hours the mastodon poll is expired (default to 24)
-v, --verbose         Verbose output
```

### Run using docker image

Create local docker image:

```bash
docker build -t prettymapsguessrbot:$(poetry version --short) -t prettymapsguessrbot:latest .
```

Run local docker image:

```bash
source .env
docker run -e MASTODON_INSTANCE=${MASTODON_INSTANCE} -e MASTODON_ACCESS_TOKEN=${MASTODON_ACCESS_TOKEN} -e OPENTRIPMAP_API_KEY=${OPENTRIPMAP_API_KEY} prettymapsguessrbot:latest
```
