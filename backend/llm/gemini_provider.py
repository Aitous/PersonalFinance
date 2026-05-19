import google.generativeai as genai

class GeminiProvider:
    def __init__(self, model=None):
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text

    def complete_json(self, prompt: str) -> str:
        response = self._model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            ),
        )
        return response.text
