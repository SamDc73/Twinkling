from model_manager import ModelManager
from utils import get_logger


class ContentGenerator:
    """Class responsible for generating content using an AI model."""

    def __init__(
        self, model_manager: ModelManager, prompts: dict[str, str], topics: list[str], topics_to_avoid: list[str],
    ) -> None:
        """Initialize the ContentGenerator.

        Parameters
        ----------
        model_manager : ModelManager
            Manager for interacting with the AI model.
        prompts : dict[str, str]
            Dictionary of prompt templates.
        topics : list[str]
            List of topics to focus on.
        topics_to_avoid : list[str]
            List of topics to avoid.
        """
        self.model_manager = model_manager
        self.prompts = prompts
        self.topics = topics
        self.topics_to_avoid = topics_to_avoid
        self.logger = get_logger(__name__)

    def generate_tweet(self, note_content: str) -> str | None:
        """Generate a tweet from the given note content.

        Parameters
        ----------
        note_content : str
            The content to base the tweet on.

        Returns
        -------
        str | None
            The generated tweet text, or None if generation failed.
        """
        prompt = self.prompts["tweet_generation"].format(
            note_content=note_content,
            topics=", ".join(self.topics),
            topics_to_avoid=", ".join(self.topics_to_avoid),
        )
        self.logger.info("Generating tweet with prompt: %s...", prompt[:50])
        tweet = self.model_manager.generate_content(prompt)
        if tweet is None:
            self.logger.warning("Failed to generate tweet content")
        return tweet
