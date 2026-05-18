import google.generativeai as genai

class GeminiProvider:
    def __init__(self, model=None):
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text
