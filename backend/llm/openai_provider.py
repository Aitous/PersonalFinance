from openai import OpenAI


class OpenAIProvider:
    MODEL = "gpt-6-luna"

    def __init__(self, client: OpenAI):
        self._client = client

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    def complete_json(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
