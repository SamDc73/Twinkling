import os

from litellm import completion

from config import load_config
from utils import get_logger


class ModelManager:
    """Manager for handling AI model interactions."""

    def __init__(self) -> None:
        """Initialize the ModelManager with configuration and environment setup."""
        self.logger = get_logger(__name__)
        config = load_config()
        self.config = config.get("ai", {}).get("model", {})
        if not self.config:
            msg = "Model configuration not found in config.yaml"
            raise ValueError(msg)
        self.setup_environment()
        self.logger.info("ModelManager initialized with model: %s", self.config["name"])

    def setup_environment(self) -> None:
        """Set up required environment variables for the model.

        Raises
        ------
        ValueError
            If the required API key is not found.
        """
        sambanova_api_key = os.getenv("SAMBANOVA_API_KEY")
        if not sambanova_api_key:
            self.logger.error("SAMBANOVA_API_KEY not found in environment variables")
            msg = "SAMBANOVA_API_KEY is required"
            raise ValueError(msg)
        os.environ["SAMBANOVA_API_KEY"] = sambanova_api_key

    def generate_content(self, prompt: str, max_tokens: int = 280) -> str | None:
        """Generate content using the AI model.

        Parameters
        ----------
        prompt : str
            The prompt to generate content from.
        max_tokens : int, optional
            Maximum number of tokens to generate, by default 280.

        Returns
        -------
        str | None
            Generated content if successful, None otherwise.
        """
        try:
            self.logger.info("Generating content with prompt: %s...", prompt[:50])
            response = completion(
                model=f"sambanova/{self.config['name']}",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_tokens=max_tokens,
                temperature=self.config.get("temperature", 0.7),
                top_p=self.config.get("top_p", 0.9),
                stop=self.config.get("stop", ["\n\n"]),
                response_format={"type": "json_object"},
                seed=self.config.get("seed", 123),
                tool_choice="auto",
                tools=[],
                user="user",
            )

            self.logger.info("Response received")
            self.logger.debug("Full response: %s", response)

            if isinstance(response.choices, list) and response.choices:
                content = response.choices[0].message.content.strip()
                self.logger.info("Generated content: %s...", content[:50])
                return content

            self.logger.error("No content generated in the response")
        except Exception:
            self.logger.exception("Error generating content")

        return None

    def get_model_info(self) -> str:
        """Get information about the current model.

        Returns
        -------
        str
            Description of the model being used.
        """
        return f"Using Sambanova model: {self.config['name']}"


if __name__ == "__main__":
    manager = ModelManager()
    result = manager.generate_content("Write a short tweet about Python programming.")
