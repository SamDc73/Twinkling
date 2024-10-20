import os

import yaml
from dotenv import load_dotenv

from content_generator import ContentGenerator
from model_manager import ModelManager
from note_manager import NoteManager
from social_media.twitter import TwitterPoster
from utils import get_logger, setup_logging

# Setup logging
logger = setup_logging(verbose=True)


def load_config() -> dict[str, any]:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(config_path) as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config file: {e}")
        raise


def get_user_input() -> str:
    while True:
        choice = input("Do you want to post this tweet? [Yes/No/Retry]: ").lower()
        if choice in ["yes", "no", "retry"]:
            return choice
        logger.warning("Invalid input. Please enter Yes, No, or Retry.")


def main() -> None:
    try:
        logger.info("Starting the application...")
        load_dotenv()
        config = load_config()
        logger.info("Config loaded successfully")

        note_manager = NoteManager(config["notes_directory"])
        logger.info("Note manager initialized")
        model_manager = ModelManager()
        logger.info("Model manager initialized")
        content_generator = ContentGenerator(model_manager, config["prompts"])
        logger.info("Content generator initialized")
        twitter_poster = TwitterPoster()
        logger.info("Twitter poster initialized")

        user_info = twitter_poster.get_user_info()
        if user_info:
            logger.info(f"Successfully retrieved info for user: @{user_info.username}")
        else:
            logger.error("Failed to retrieve user info")
            return

        tag: str | None = input(
            "Enter a tag for the note (leave empty for random): "
        ).strip()
        logger.info(f"User entered tag: '{tag}'")

        while True:
            logger.info("Fetching note content...")
            note_content = (
                note_manager.get_tagged_note(tag)
                if tag
                else note_manager.get_random_tech_note()
            )

            if note_content:
                logger.info("Note content found, generating tweet...")
                tweet_content = content_generator.generate_tweet(note_content)
                logger.info(f"Generated tweet content: {tweet_content}")

                choice = get_user_input()
                logger.info(f"User choice: {choice}")

                if choice == "yes":
                    # Optionally, you can add image posting here if needed
                    # image_path = "path/to/your/image.png"
                    # success = twitter_poster.post_tweet(tweet_content, image_path)
                    success = twitter_poster.post_tweet(tweet_content)
                    if success:
                        logger.info("Tweet posted successfully!")
                    else:
                        logger.error("Failed to post tweet.")
                    break
                elif choice == "no":
                    logger.info("Tweet discarded.")
                    break
                else:  # retry
                    logger.info("Generating a new tweet...")
            else:
                logger.warning(f"No{'tagged' if tag else ''} notes found.")
                break

    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
