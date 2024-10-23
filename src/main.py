from config import load_config, load_env_vars
from content_generator import ContentGenerator
from model_manager import ModelManager
from note_manager import NoteManager
from social_media.twitter import TwitterPoster
from utils import get_logger, setup_logging

logger = setup_logging(verbose=True)


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
        logger.info(f"User entered tag: '{tag}'")

        note_content, note_filename = (
            note_manager.get_tagged_note(tag)
            if tag
            else note_manager.get_random_tech_note()
        )

        if not note_content or not note_filename:
            logger.warning(f"No{'tagged' if tag else ''} notes found.")
            print(f"No{'tagged' if tag else ''} notes found.")
            return

        logger.info(f"Note content found from file: {note_filename}")
        print(f"\nUsing note from file: {note_filename}\n")

        while True:
            tweet_content = content_generator.generate_tweet(note_content)
            print(f"\nGenerated Tweet:\n{tweet_content}\n")

            choice = input("Do you want to post this tweet? [Yes/No/Retry]: ").lower()
            if choice == "yes":
                if twitter_poster.post_tweet(tweet_content):
                    print("Tweet posted successfully!")
                    break
            elif choice == "no":
                print("Tweet discarded.")
                break
            else:
                print("Generating a new tweet...\n")

    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
