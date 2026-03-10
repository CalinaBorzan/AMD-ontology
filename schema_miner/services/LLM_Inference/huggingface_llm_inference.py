import os

from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEndpoint

from schema_miner.services.LLM_Inference.LLM_inference import LLM_Inference


class HuggingFace_LLM_Inference(LLM_Inference):
    """
    HuggingFace_LLM_Inference is a subclass of LLM_Inference which has a task of doing inference from the specific Large Language Model(LLM) giving a specified prompt.
    """

    def __init__(self, model_name: str, temperature: float = 0.3):
        """
        Initialize the object with HuggingFace configuration (Model name etc.)
        """
        super().__init__(model_name=model_name, temperature=temperature)

        # DEBUG: Print what we're getting
        print(f"🔍 DEBUG: self.config.HUGGINGFACE_access_token = {self.config.HUGGINGFACE_access_token}")

        # HuggingFace Access Token
        if self.config.HUGGINGFACE_access_token is None:
            raise ValueError(
                "❌ HUGGINGFACE_access_token is None!\n"
                "Fix: Create .env file with HuggingFace_Access_Token=hf_...\n"
                f"Or hardcode in envConfig.py"
            )

        self.access_token = self.config.HUGGINGFACE_access_token

        # Set environment variable
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = self.access_token

        print(f"✓ Token set: {self.access_token[:20]}...")
        print(f"✓ Env var set: {os.environ.get('HUGGINGFACEHUB_API_TOKEN')[:20]}...")

        # The Large Language Model to use for Inference
        try:
            # NOTE: Many free Inference API backends cap tokens around 512–1024.
            # Using a conservative default to avoid 4xx/5xx quota errors.
            self.model = HuggingFaceEndpoint(
                repo_id=self.model_name,
                huggingfacehub_api_token=self.access_token,  # ← EXPLICITLY PASS TOKEN
                task="text-generation",
                max_new_tokens=1024,
                temperature=self.temperature,
                truncate=True,
            )
            print("✓ HuggingFaceEndpoint created successfully!")
        except Exception as e:
            print(f"❌ Failed to create HuggingFaceEndpoint: {e}")
            raise

    def __str__(self):
        """
        Returns a human-readable representation of an object
        """
        return f"HuggingFace - LLM Inference with Model: {self.model_name}"

    def completion(self, prompt_template, var_dict):
        """
        Requests the completion endpoint of the HuggingFace with the specified prompt/message. Returns the parsed output from the model.

        :param prompt_template: The prompt template with placeholders for dynamic values.
        :param dict var_dict: The dictionary containing variable name and its corresponding value to format the prompt.
        :returns model_output: The parsed LLM output
        """
        try:
            # Formatting the prompt
            prompt = super().format_prompt_template(prompt_template, var_dict)

            # HuggingFaceEndpoint expects a single string input for text-generation.
            # Convert chat prompt value to a flat string instead of messages.
            input_text = prompt.to_string()

            # Invoking the model's completion API with the prompt
            model_output = self.model.invoke(input_text)

            # Parsing the LLM's output to extract the final output
            model_output = StrOutputParser().invoke(model_output)

            # Returns the LLM's output
            return model_output
        except Exception as e:
            self.logger.debug(
                f"Exception Occurred while calling the Completion API of model: {self.model_name}"
            )
            self.logger.debug(f"Exception: {e}")
            return None
