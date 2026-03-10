import json
import logging
import re


def extract_json_schema(text: str, json_encl_expr: list):
    """
    Extracts the JSON schema from a given text. The JSON schema is enclosed within the start expression and end expression

    :param str text: The text containing the JSON schema
    :param str json_encl_expr: The list of tuples containing start and end expression between which JSON schema is stored.
    :return dict: The extracted JSON schema
    """
    # Initialize the logger
    logger = logging.getLogger(__name__)

    # Intialize schema
    schema = None

    # Check if the response only contains the JSON object
    try:
        schema = json.loads(text.strip())
        return schema
    except Exception:
        logger.debug("The LLM's response does not contains only the JSON Schema")
        logger.debug("Now, Extracting the JSON Schema enclosed within the start expression and end expression")

    # Trying every start and end expression combination to extract JSON object
    for expr in json_encl_expr:
        # Formatting the regex
        json_extract_pattern = rf"{expr[0]}(.*?){expr[1]}"

        # Extracting the JSON schema
        matches = re.findall(json_extract_pattern, text, re.DOTALL)
        if matches:
            try:
                schema = json.loads("".join(matches))
                break
            except Exception:
                logger.debug(f"Exception occured while trying {expr} as the start and end expression")

    # Fallback: try to extract the largest JSON-looking object by curly braces
    if schema is None:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start : end + 1]
                schema = json.loads(candidate)
        except Exception:
            logger.debug("Failed to extract JSON via curly-brace fallback")

    # Returning the extracted schema or if not found: None
    return schema
