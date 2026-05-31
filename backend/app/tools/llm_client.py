from app.core.config import settings


class LLMClient:
    def _chat_models(self) -> list[str]:
        models = [settings.llm_model]
        if settings.llm_base_url and "dashscope" in settings.llm_base_url:
            models.extend(["qwen-plus", "qwen-turbo"])
        return list(dict.fromkeys([model for model in models if model]))

    def _deepseek_thinking_kwargs(self, model_name: str) -> dict:
        base_url = (settings.llm_base_url or "").lower()
        model = model_name.lower()
        if "deepseek" not in base_url and "deepseek" not in model:
            return {}
        thinking_type = "enabled" if settings.llm_thinking_enabled else "disabled"
        kwargs: dict = {"extra_body": {"thinking": {"type": thinking_type}}}
        if settings.llm_thinking_enabled and settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = settings.llm_reasoning_effort
        return kwargs

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
                    temperature=0.2 if not settings.llm_thinking_enabled else None,
                    **self._deepseek_thinking_kwargs(model_name),
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
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        api_key = settings.embedding_api_key or settings.llm_api_key
        base_url = settings.embedding_base_url or settings.llm_base_url
        if not api_key:
            return [[] for _ in texts]
        if not texts:
            return []
        model_names = [settings.embedding_model]
        if base_url and "dashscope" in base_url:
            model_names.extend(["text-embedding-v4", "text-embedding-v3"])
        last_error = ""
        for model_name in dict.fromkeys([name for name in model_names if name]):
            try:
                from openai import OpenAI

                client = OpenAI(api_key=api_key, base_url=base_url)
                response = client.embeddings.create(model=model_name, input=[text[:6000] for text in texts])
                ordered = sorted(response.data, key=lambda item: item.index)
                return [list(item.embedding) for item in ordered]
            except Exception as exc:
                last_error = str(exc)
                continue
        raise RuntimeError(f"Embedding failed: {last_error}")
