from argparse import Namespace

from .bluesky import BlueskyPoster
from .twitter import TwitterPoster


def initialize_platforms(args: Namespace) -> list[tuple[str, BlueskyPoster | TwitterPoster]]:
    """Initialize social media platforms based on command line arguments.

    Parameters
    ----------
    args : Namespace
        Parsed command line arguments

    Returns
    -------
    List[Tuple[str, BlueskyPoster | TwitterPoster]]
        List of tuples containing platform name and poster instance
    """
    posters = []
    if args.platform:
        if "twitter" in args.platform:
            posters.append(("Twitter", TwitterPoster()))
        if "bluesky" in args.platform:
            posters.append(("Bluesky", BlueskyPoster()))
    elif args.all:
        posters.extend([("Twitter", TwitterPoster()), ("Bluesky", BlueskyPoster())])
    return posters
