import anthropic

class ClaudeProvider:
    MODEL = "claude-sonnet-4-6"

    def __init__(self, client: anthropic.Anthropic):
        self._client = client

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
