"""Module for sending new Instagram posts to Discord."""

import asyncio
import io
import logging
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta
from itertools import dropwhile, takewhile
from time import sleep
from typing import Any, Dict, List

from .parser import parser

try:
    from aiohttp import ClientSession
    from discord import Embed, File, SyncWebhook
    import instaloader.exceptions
    import instaloader.instaloadercontext
    from instaloader.exceptions import LoginException, LoginRequiredException
    from instaloader.instaloader import Instaloader
    from instaloader.structures import Post, Profile
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"{exc.name} not found.\n  pip install [--user] {exc.name}"
    ) from exc


# Monkey patch instaloader with updated user agents
def patched_default_user_agent() -> str:
    """Return a patched user agent string."""
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )


def patched_default_iphone_headers() -> Dict[str, Any]:
    """Return patched iPhone headers."""
    return {
        "User-Agent": (
            "Instagram 361.0.0.35.82 (iPad13,8; iOS 18_0; en_US; en-US; "
            "scale=2.00; 2048x2732; 674117118) AppleWebKit/420+"
        ),
        "x-ads-opt-out": "1",
        "x-bloks-is-panorama-enabled": "true",
        "x-bloks-version-id": (
            "16b7bd25c6c06886d57c4d455265669345a2d96625385b8ee30026ac2dc5ed97"
        ),
        "x-fb-client-ip": "True",
        "x-fb-connection-type": "wifi",
        "x-fb-http-engine": "Liger",
        "x-fb-server-cluster": "True",
        "x-fb": "1",
        "x-ig-abr-connection-speed-kbps": "2",
        "x-ig-app-id": "124024574287414",
        "x-ig-app-locale": "en-US",
        "x-ig-app-startup-country": "US",
        "x-ig-bandwidth-speed-kbps": "0.000",
        "x-ig-capabilities": "36r/F/8=",
        "x-ig-connection-speed": f"{random.randint(1000, 20000)}kbps",
        "x-ig-connection-type": "WiFi",
        "x-ig-device-locale": "en-US",
        "x-ig-mapped-locale": "en-US",
        "x-ig-timezone-offset": str(
            (datetime.now().astimezone().utcoffset() or timedelta(seconds=0)).seconds
        ),
        "x-ig-www-claim": "0",
        "x-pigeon-session-id": str(uuid.uuid4()),
        "x-tigon-is-retry": "False",
        "x-whatsapp": "0",
    }


instaloader.instaloadercontext.default_user_agent = patched_default_user_agent
instaloader.instaloadercontext.default_iphone_headers = patched_default_iphone_headers


# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging.INFO,
)


args = parser.parse_args()

# Set the logger to debug if verbose is enabled
if args.quiet:
    logger.setLevel(logging.CRITICAL)
    logger.debug("Quiet output enabled.")
elif args.verbose:
    logger.setLevel(logging.DEBUG)
    logger.debug("Verbose output enabled.")
else:
    logger.setLevel(logging.INFO)

if args.login or args.interactive_login:
    logger.info("Logging into Instagram...")
    try:
        if args.login:
            Instaloader().login(*args.login)
        if args.interactive_login:
            Instaloader().interactive_login(args.interactive_login)
    except LoginException as login_exc:
        logger.critical("instaloader: error: %s", login_exc)
        raise SystemExit(
            "An error happened during login. Check if the provided username exists."
        ) from login_exc
    except KeyboardInterrupt:
        print("\nLogin interrupted by user.")
        sys.exit(0)

# Log the start of the program
logger.info("Starting InstaWebhooks...")

# Ensure that a message content is provided if no embed is enabled
if args.no_embed and args.message_content == "":
    logger.critical("error: Cannot send an empty message. No message content provided.")
    raise SystemExit(
        "Please provide a message content with the --message-content flag."
    )


def get_memory_path(username: str) -> str:
    """Get path to the memory file for a username"""
    memory_dir = ".memory"
    os.makedirs(memory_dir, exist_ok=True)
    return os.path.join(memory_dir, f"last_post_{username}.txt")


def load_last_shortcode(username: str) -> str | None:
    """Load the last processed shortcode from memory"""
    path = get_memory_path(username)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else None
        except IOError:
            logger.warning("Failed to read memory file.")
    return None


def save_last_shortcode(username: str, shortcode: str):
    """Save the last processed shortcode to memory"""
    path = get_memory_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(shortcode)
    except IOError:
        logger.warning("Failed to write memory file.")


async def create_embed(post: Post):
    """Create a Discord embed object from an Instagram post"""

    logger.debug("Creating post embed...")

    footer_icon_url = (
        "https://www.instagram.com/static/images/ico/favicon-192.png/68d99ba29cc8.png"
    )

    # Download the post image and profile picture
    async with ClientSession() as cs:
        async with cs.get(post.url) as res:
            post_image_bytes = await res.read()

        async with cs.get(post.owner_profile.profile_pic_url) as res:
            profile_pic_bytes = await res.read()

    post_image_file = File(io.BytesIO(post_image_bytes), "post_image.webp")
    profile_pic_file = File(io.BytesIO(profile_pic_bytes), "profile_pic.webp")

    # Format the post caption with clickable links for mentions and hashtags
    post_caption = post.caption or ""
    post_caption = re.sub(
        r"#([a-zA-Z0-9]+\b)",
        r"[#\1](https://www.instagram.com/explore/tags/\1)",
        post_caption,
    )
    post_caption = re.sub(
        r"@([a-zA-Z0-9_]+\b)",
        r"[@\1](https://www.instagram.com/\1)",
        post_caption,
    )

    embed = Embed(
        color=13500529,
        title=post.owner_profile.full_name,
        description=post_caption,
        url=f"https://www.instagram.com/p/{post.shortcode}/",
        timestamp=post.date,
    )
    embed.set_author(
        name=post.owner_username,
        url=f"https://www.instagram.com/{post.owner_username}/",
        icon_url="attachment://profile_pic.webp",
    )
    embed.set_footer(text="Instagram", icon_url=footer_icon_url)
    embed.set_image(url="attachment://post_image.webp")

    return embed, post_image_file, profile_pic_file


def format_message(post: Post):
    """Format the message content with placeholders"""

    logger.debug("Formatting message for placeholders...")
    placeholders: Dict[str, str] = {
        "{post_url}": f"https://www.instagram.com/p/{post.shortcode}/",
        "{owner_url}": f"https://www.instagram.com/{post.owner_username}/",
        "{owner_name}": post.owner_profile.full_name,
        "{owner_username}": post.owner_username,
        "{post_caption}": post.caption or "",
        "{post_shortcode}": post.shortcode,
        "{post_image_url}": post.url,
    }

    # Replace placeholders in the message content
    for placeholder, value in placeholders.items():
        args.message_content = args.message_content.replace(placeholder, value)


async def send_to_discord(post: Post):
    """Send a new Instagram post to Discord using a webhook"""

    webhook = SyncWebhook.from_url(args.discord_webhook_url)

    if args.message_content:
        format_message(post)

    logger.debug("Sending post sent to Discord...")

    if not args.no_embed:
        embed, post_image_file, profile_pic_file = await create_embed(post)
        webhook.send(
            content=args.message_content,
            embed=embed,
            files=[post_image_file, profile_pic_file],
        )
    else:
        webhook.send(content=args.message_content)

    logger.info("New post sent to Discord successfully.")


def fetch_new_posts(
    posts, last_shortcode: str, posts_to_send: List[Post], limit: int = 50
) -> None:
    """Fetch new posts until the last known shortcode is found."""
    count = 0
    # Safety cut-off: Don't look back further than 7 days when resuming.
    # This prevents the bot from spamming if the 'last_shortcode' post was deleted
    # or if logic fails, avoiding re-sending years of history.
    cutoff_date = datetime.now() - timedelta(days=7)

    try:
        for post in posts:
            # First check if we hit the date limit
            if post.date < cutoff_date:
                logger.warning(
                    "Reached posts older than 7 days without "
                    "finding last shortcode. Stopping."
                )
                break

            if post.shortcode == last_shortcode:
                break

            # Skip pinned posts, as they are not the newest posts
            if post.is_pinned:
                continue

            posts_to_send.append(post)
            count += 1
            if count >= limit:
                logger.warning(
                    "Last known post not found within limit. Stopping fetch."
                )
                break
    except (
        instaloader.exceptions.ConnectionException,
        instaloader.exceptions.QueryReturnedBadRequestException,
    ) as error:
        logger.warning(
            "Connection error while fetching posts "
            "(likely rate limit or end of stream): %s",
            error,
        )
        logger.warning(
            "Stopping fetch for %s and processing gathered posts.",
            args.instagram_username,
        )


async def check_for_new_posts(catchup: int = args.catchup):
    """Check for new Instagram posts and send them to Discord"""

    logger.info("Checking for new posts")

    try:
        posts = Profile.from_username(
            Instaloader().context, args.instagram_username
        ).get_posts()
    except (
        instaloader.exceptions.ConnectionException,
        instaloader.exceptions.QueryReturnedBadRequestException,
        instaloader.exceptions.ProfileNotExistsException,
        LoginRequiredException,
    ) as e:
        logger.error(
            "Error collecting profile info for %s: %s. Skipping this run.",
            args.instagram_username,
            e,
        )
        return

    last_shortcode = load_last_shortcode(args.instagram_username)
    posts_to_send: List[Post] = []

    if last_shortcode:
        logger.info("Resuming from last known post: %s", last_shortcode)
        fetch_new_posts(posts, last_shortcode, posts_to_send)
    else:
        since = datetime.now()
        until = datetime.now() - timedelta(seconds=args.refresh_interval)

        if catchup > 0:
            logger.info("Sending last %s posts on startup...", catchup)
            for post in takewhile(lambda _: catchup > 0, posts):
                posts_to_send.append(post)
                catchup -= 1
        else:
            for post in takewhile(
                lambda p: p.date > until, dropwhile(lambda p: p.date > since, posts)
            ):
                posts_to_send.append(post)

    if not posts_to_send:
        logger.info("No new posts found.")
        return

    async def send_post(post: Post):
        logger.info("New post found: https://www.instagram.com/p/%s", post.shortcode)
        await send_to_discord(post)

    # Reverse the posts to send oldest first
    for post in reversed(posts_to_send):
        await send_post(post)
        # Save progress immediately after sending to prevent duplicates if script crashes
        save_last_shortcode(args.instagram_username, post.shortcode)
        sleep(2)  # Avoid 30 requests per minute rate limit


def main():
    """Check for new Instagram posts and send them to Discord"""
    logger.info("InstaWebhooks started successfully.")
    logger.info(
        "Monitoring '%s' every %s seconds on ̀%s.",
        args.instagram_username,
        args.refresh_interval,
        args.discord_webhook_url,
    )

    try:
        while True:
            asyncio.run(check_for_new_posts())
            if args.once:
                logger.info("Run-once mode enabled. Exiting.")
                break
            sleep(args.refresh_interval)
    except LoginRequiredException as login_exc:
        logger.critical("instaloader: error: %s", login_exc)
        raise SystemExit(
            "Not logged in. Please login with the --login flag."
        ) from login_exc
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
