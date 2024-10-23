import os

from litellm import completion

from config import load_config
from utils import get_logger


class ModelManager:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        config = load_config()
        self.config = config.get("ai", {}).get("model", {})
        if not self.config:
            raise ValueError("Model configuration not found in config.yaml")
        self.setup_environment()
        self.logger.info(f"ModelManager initialized with model: {self.config['name']}")

    def setup_environment(self) -> None:
        sambanova_api_key = os.getenv("SAMBANOVA_API_KEY")
        if not sambanova_api_key:
            self.logger.error("SAMBANOVA_API_KEY not found in environment variables")
            raise ValueError("SAMBANOVA_API_KEY is required")
        os.environ["SAMBANOVA_API_KEY"] = sambanova_api_key

    def generate_content(self, prompt: str, max_tokens: int = 280) -> str:
        try:
            self.logger.info(f"Generating content with prompt: {prompt[:50]}...")
            response = completion(
                model=f"sambanova/{self.config['name']}",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
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
            self.logger.debug(f"Full response: {response}")

            if isinstance(response.choices, list) and len(response.choices) > 0:
                content = response.choices[0].message.content.strip()
                self.logger.info(f"Generated content: {content[:50]}...")
                return content
            else:
                self.logger.error("No content generated in the response")
                return None
        except Exception as e:
            self.logger.exception(f"Error generating content: {str(e)}")
            return None

    def get_model_info(self) -> str:
        return f"Using Sambanova model: {self.config['name']}"


if __name__ == "__main__":
    manager = ModelManager()
    print(manager.get_model_info())
    result = manager.generate_content("Write a short tweet about Python programming.")
    print(f"Generated content: {result}")
