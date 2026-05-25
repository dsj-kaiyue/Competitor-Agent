from app.core.config import settings


class LLMClient:
    def _chat_models(self) -> list[str]:
        models = [settings.llm_model]
        if settings.llm_base_url and "dashscope" in settings.llm_base_url:
            models.extend(["qwen-plus", "qwen-turbo"])
        return list(dict.fromkeys([model for model in models if model]))

    def complete(self, prompt: str, system: str | None = None) -> str:
        if not settings.llm_api_key:
            return ""
        last_error = ""
        for model_name in self._chat_models():
            try:
                from langchain_openai import ChatOpenAI

                model = ChatOpenAI(
                    model=model_name,
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    timeout=90,
                    temperature=0.2,
                )
                messages = []
                if system:
                    messages.append(("system", system))
                messages.append(("human", prompt))
                return str(model.invoke(messages).content)
            except Exception as exc:
                last_error = str(exc)
                continue
        raise RuntimeError(f"LLM completion failed: {last_error}")

    def embed_text(self, text: str) -> list[float]:
        if not settings.llm_api_key:
            return []
        model_names = [settings.embedding_model]
        if settings.llm_base_url and "dashscope" in settings.llm_base_url:
            model_names.extend(["text-embedding-v4", "text-embedding-v3"])
        last_error = ""
        for model_name in dict.fromkeys([name for name in model_names if name]):
            try:
                from openai import OpenAI

                client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
                response = client.embeddings.create(model=model_name, input=text[:6000])
                return list(response.data[0].embedding)
            except Exception as exc:
                last_error = str(exc)
                continue
        raise RuntimeError(f"Embedding failed: {last_error}")
