import json
import logging
import os
import random
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from typing import Any, Dict, Tuple

import colorlog
import prettymaps
import requests
from mastodon import Mastodon
from requests import Response
from shapely.geometry import Point, Polygon, shape

# logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = colorlog.ColoredFormatter(
    "%(yellow)s%(asctime)s %(log_color)s[%(levelname)s]%(reset)s %(purple)s[%(name)s %(module)s]%(reset)s %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# retrieve environment variables
if "MASTODON_INSTANCE" not in os.environ:
    logger.error("Error: MASTODON_INSTANCE environment variable not set")
    exit(1)
if "MASTODON_ACCESS_TOKEN" not in os.environ:
    logger.error("Error: MASTODON_ACCESS_TOKEN environment variable not set")
    exit(1)
if "OPENTRIPMAP_API_KEY" not in os.environ:
    logger.error("Error: OPENTRIPMAP_API_KEY environment variable not set")
    exit(1)

MASTODON_INSTANCE = os.getenv("MASTODON_INSTANCE")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")
MAX_POLL_OPTION_LENGTH = 50
OPENTRIPMAP_API_KEY = os.getenv("OPENTRIPMAP_API_KEY")
OPENTRIPMAP_URL = "https://api.opentripmap.com/0.1/en/places/radius"
NOMINATIM_URL = "https://nominatim.openstreetmap.org"

PRETTYMAPS_PRESETS = [
    p.strip()
    for p in prettymaps.presets()["preset"].to_string(index=False).split("\n")
    if "barcelona-plotter" not in p
]

IMG_TOOT_TEMPLATE = """🗺 Which place is this ?

📍 Clue: this place is in {country_name}

👇 You can answer in the poll which is in the first reply 👇

#prettymaps"""
POLL_TOOT_TPL = """Which place is this ?"""
ANSWER_TOOT_TPL = """The correct answer is : {answer}"""
ANSWER_TOOT_CW_TPL = "✅ Correct answer"


def pick_country(country: str) -> Dict[str, Any]:
    with open("world_countries.geojson", "r") as file:
        geojson = json.loads(file.read())
        assert geojson["type"] == "FeatureCollection"
        if country == "random":
            return random.choice(geojson["features"])
        countries = {c["properties"]["ADMIN"].upper(): c for c in geojson["features"]}
        return countries[country.upper()]


def generate_random_point(polygon: Polygon) -> Point:
    minx, miny, maxx, maxy = polygon.bounds
    point = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
    if polygon.contains(point):
        return point
    return generate_random_point(polygon)


def get_otm_place(
    polygon: Polygon, radius_km: int, rate: int = 3, limit: int = 50
) -> Dict[str, Any]:
    # generate a random point inside polygon
    rnd_point = generate_random_point(polygon)

    # get a place from OpenTripMap, see https://opentripmap.io/docs
    r: Response = requests.get(
        OPENTRIPMAP_URL,
        params={
            "lon": rnd_point.x,
            "lat": rnd_point.y,
            "radius": radius_km * 1000,
            "rate": rate,
            "src_attr": "osm",
            "limit": limit,
            "apikey": OPENTRIPMAP_API_KEY,
        },
    )
    logger.debug(r.content)
    assert r.status_code == 200
    features = r.json()["features"]

    # retry if no OpenTripMap place around point
    if len(features) == 0:
        return get_otm_place(polygon, radius_km, rate, limit)

    feature = random.choice(features)
    assert feature["geometry"]["type"] == "Point"
    logging.debug(
        f"OpenTripMap feature: {feature['properties']['name']} {feature['geometry']['coordinates']}"
    )
    return feature


def get_nominatim_address(feature: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    point: Point = shape(feature["geometry"])
    nominatim_r: Response = requests.get(
        f"{NOMINATIM_URL}/reverse",
        params={"lon": point.x, "lat": point.y, "format": "geojson"},
    )
    assert len(nominatim_r.json()["features"]) == 1
    nmntm_feat = nominatim_r.json()["features"][0]
    return nmntm_feat["properties"]["display_name"], nmntm_feat["properties"]["address"]


def create_poll_option(
    name: str, address: Dict[str, Any], max_length: int = MAX_POLL_OPTION_LENGTH
) -> str:
    city = address.get("municipality", address.get("town", "somewhere"))
    region = address.get("state", address.get("region", "somewhere"))
    opt = f"{name}, {city}, {region}"
    if len(opt) <= max_length:
        return opt
    return f"{opt[:max_length - 2]}.."


def generate_prettymaps_image(address: str, preset: str) -> str:
    path = f"prettymaps_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{preset}.png"
    prettymaps.plot(query=address, preset=preset, save_as=path)
    return path


def build_arguments() -> Namespace:
    """
    Creates CLI arguments needed by the program
    :return: Namespace for CLI arg's definition
    """
    parser = ArgumentParser(description="prettymaps guess mastodon bot cli")
    parser.add_argument(
        "-c",
        "--country",
        default="random",
        help="Country inside which random places are picked (default to 'random')",
    )
    parser.add_argument(
        "-n",
        "--nb_picks",
        default=3,
        help="Number of available picks (between 2 and 4, default to 3)",
    )
    parser.add_argument(
        "-p",
        "--preset",
        default="default",
        help=f"Prettymaps preset to use (default to 'random', available: {','.join(PRETTYMAPS_PRESETS)})",
    )
    parser.add_argument(
        "-r",
        "--radius",
        default=50,
        help="Radius (km) used to get an OpenTripMap place around a randomly created point",
    )
    parser.add_argument(
        "-ho",
        "--hours",
        default=24,
        help="After how many hours the mastodon poll is expired (default to 24)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose output"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = build_arguments()
    logger.info(args)

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for h in logger.handlers:
            h.setLevel(logging.DEBUG)

    nb_picks = int(args.nb_picks)
    radius_km = int(args.radius)
    nb_hours = int(args.hours)
    if nb_picks < 2 or nb_picks > 4:
        logger.error("Number of picks must be between 2 and 4")
        exit(1)

    country = pick_country(args.country)
    country_name = country["properties"]["ADMIN"]
    polygon = shape(country["geometry"])
    logging.info(f"Country: {country_name}")

    # generate picks
    otm_places = [get_otm_place(polygon, radius_km) for _ in range(nb_picks)]
    otm_names = [f["properties"]["name"] for f in otm_places]
    names, addresses = zip(*(get_nominatim_address(f) for f in otm_places))
    poll_options = [
        create_poll_option(otm_names[i - 1], addresses[i - 1])
        for i in range(1, nb_picks + 1)
    ]
    logger.info(f"Random picks: {' -- '.join(poll_options)}")

    # randomly select the correct pick
    idx_pick = random.randint(1, nb_picks) - 1
    place = otm_places[idx_pick]
    logger.info(f"Correct pick: {otm_names[idx_pick]}")

    # generate prettymaps image
    preset = (
        random.choice(PRETTYMAPS_PRESETS) if args.preset == "random" else args.preset
    )
    map_path = generate_prettymaps_image(names[idx_pick], preset)

    # toot on mastodon instance configured with environment variables
    mastodon = Mastodon(
        api_base_url=MASTODON_INSTANCE, access_token=MASTODON_ACCESS_TOKEN
    )

    # toot map image first
    img_toot = mastodon.status_post(
        IMG_TOOT_TEMPLATE.format(country_name=country_name),
        media_ids=[
            mastodon.media_post(
                map_path,
                mime_type="image/png",
                description=f"A map of a place somewhere in {country_name} generated with Prettymaps",
            )
        ],
        visibility="public",
        language="en",
    )
    os.remove(map_path)

    # reply with poll
    poll_toot = mastodon.status_post(
        status=POLL_TOOT_TPL.format(
            account=img_toot.account.acct, country_name=country_name
        ),
        in_reply_to_id=img_toot.id,
        poll=mastodon.make_poll(
            options=random.sample(poll_options, len(poll_options)),
            expires_in=3600 * nb_hours,
            multiple=False,
            hide_totals=False,
        ),
        visibility="unlisted",
        language="en",
    )

    # reply with correct answer
    mastodon.status_post(
        status=ANSWER_TOOT_TPL.format(
            account=img_toot.account.acct, answer=poll_options[idx_pick]
        ),
        in_reply_to_id=poll_toot.id,
        spoiler_text=ANSWER_TOOT_CW_TPL,
        scheduled_at=datetime.now() + timedelta(hours=nb_hours - 1),
        visibility="unlisted",
        language="en",
    )
