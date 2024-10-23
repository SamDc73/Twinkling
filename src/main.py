from config import load_config, load_env_vars
from content_generator import ContentGenerator
from model_manager import ModelManager
from note_manager import NoteManager
from social_media.twitter import TwitterPoster
from utils import setup_logging


logger = setup_logging()


def main() -> None:
    try:
        logger.info("Starting the application...")

        # Load environment variables and config
        load_env_vars()
        config = load_config()
        logger.info("Config loaded successfully")

        # Initialize components
        note_manager = NoteManager(config["notes_directory"])
        model_manager = ModelManager()
        content_generator = ContentGenerator(
            model_manager,
            config["prompts"],
            config["topics"],
            config["topics_to_avoid"],
        )
        twitter_poster = TwitterPoster()

        # Get note content
        tag = input("Enter a tag for the note (leave empty for random): ").strip()
        logger.info("User entered tag: '%s'", tag)

        note_content, note_filename = note_manager.get_tagged_note(tag) if tag else note_manager.get_random_tech_note()

        if not note_content or not note_filename:
            tag_status = "tagged " if tag else ""
            logger.warning("No %snotes found.", tag_status)
            return

        logger.info("Note content found from file: %s", note_filename)

        while True:
            tweet_content = content_generator.generate_tweet(note_content)

            choice = input("Do you want to post this tweet? [Yes/No/Retry]: ").lower()
            if choice == "yes":
                if twitter_poster.post_tweet(tweet_content):
                    break
            elif choice == "no":
                break
            else:
                pass

    except Exception:
        logger.exception("An error occurred")


if __name__ == "__main__":
    main()
