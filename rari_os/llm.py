"""The AI brain. Uses Claude through the Anthropic API when ANTHROPIC_API_KEY is set."""
import os

DEFAULT_MODEL = "claude-sonnet-5-5"


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def ask(system: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """messages: [{"role": "user"|"assistant", "content": str}, ...]"""
    if not available():
        return (
            "The AI brain is offline: add your ANTHROPIC_API_KEY to the .env file "
            "and restart Rari OS."
        )
    import anthropic

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=os.getenv("RARI_OS_MODEL", DEFAULT_MODEL),
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
    except anthropic.AuthenticationError:
        return "The AI brain couldn't sign in: check the ANTHROPIC_API_KEY in your .env file."
    except anthropic.APIError as e:
        return f"The AI brain hit an error talking to Claude: {e}"
    return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
