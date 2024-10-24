from config import load_config, load_env_vars
from content_generator import ContentGenerator
from model_manager import ModelManager
from note_manager import NoteManager
from social_media import initialize_platforms
from utils import parse_args, setup_logging


def main() -> None:
    try:
        logger = setup_logging()
        logger.info("Starting the application...")
        args = parse_args()

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

        # Get platforms and note content
        posters = initialize_platforms(args)
        note_content, note_filename = note_manager.get_note_content()

        if not note_content:
            return

        # Generate and post content
        while True:
            tweet_content = content_generator.generate_tweet(note_content)
            if not tweet_content:
                continue

            print("\nGenerated content:")
            print("-----------------")
            print(tweet_content)
            print("-----------------\n")

            choice = input("Do you want to post this content? [Yes/No/Retry]: ").lower()
            if choice == "yes":
                success = True
                for platform_name, poster in posters:
                    logger.info(f"Attempting to post to {platform_name}...")
                    try:
                        if not poster.post_tweet(tweet_content):
                            logger.error(f"Failed to post to {platform_name}")
                            success = False
                        else:
                            logger.info(f"Successfully posted to {platform_name}")
                    except Exception as e:
                        logger.exception(f"Exception while posting to {platform_name}: {str(e)}")
                        success = False
                if success:
                    break
            elif choice == "no":
                break

    except Exception:
        logger.exception("An error occurred")


if __name__ == "__main__":
    main()
