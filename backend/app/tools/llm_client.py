from app.core.config import settings


class LLMClient:
    def complete(self, prompt: str) -> str:
        if not settings.llm_api_key:
            return ""
        try:
            from langchain_openai import ChatOpenAI

            model = ChatOpenAI(model=settings.llm_model, api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            return model.invoke(prompt).content
        except Exception:
            return ""
