"""OCI Generative AI client for SQL rewriting.

Provides a LangChain-compatible wrapper around Oracle Cloud Infrastructure
Generative AI service.
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


@dataclass
class OCIGenAIConfig:
    """Configuration for OCI Generative AI."""

    config_file: str = "~/.oci/config"
    config_profile: str = "DEFAULT"
    endpoint: str = ""
    endpoint_id: str = ""
    compartment_id: str = ""
    model_id: str = "cohere.command-r-plus"

    # Model parameters
    max_tokens: int = 4096
    temperature: float = 0.0
    top_p: float = 0.75
    top_k: int = -1
    frequency_penalty: float = 1.0
    presence_penalty: float = 0.0


class ChatOCIGenAI(BaseChatModel):
    """LangChain-compatible chat model using OCI Generative AI.

    This wraps the OCI GenAI inference API to provide a familiar interface
    for use with existing LangChain-based tools.

    Example:
        >>> config = OCIGenAIConfig(
        ...     endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        ...     endpoint_id="ocid1.generativeaiendpoint.oc1...",
        ...     compartment_id="ocid1.compartment.oc1...",
        ... )
        >>> llm = ChatOCIGenAI(config=config)
        >>> response = llm.invoke([HumanMessage(content="Hello")])
    """

    config: OCIGenAIConfig
    _client: Any = None

    def __init__(self, config: OCIGenAIConfig, **kwargs):
        """Initialize OCI GenAI client.

        Args:
            config: OCI GenAI configuration
        """
        super().__init__(config=config, **kwargs)
        self._client = None

    @property
    def _llm_type(self) -> str:
        return "oci-genai"

    @property
    def client(self):
        """Lazy initialization of OCI client."""
        if self._client is None:
            try:
                import oci
            except ImportError as e:
                raise ImportError(
                    "oci package is required for OCI GenAI. "
                    "Install with: pip install oci"
                ) from e

            oci_config = oci.config.from_file(
                self.config.config_file,
                self.config.config_profile,
            )

            # Handle security_token auth type (used with OCI session tokens)
            auth_type = oci_config.get("authentication_type", "")
            has_token_file = "security_token_file" in oci_config
            if auth_type == "security_token" or has_token_file:
                token_file = oci_config["security_token_file"]
                with open(token_file) as f:
                    token = f.read()
                private_key = oci.signer.load_private_key_from_file(oci_config["key_file"])
                signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
                self._client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                    config={},
                    signer=signer,
                    service_endpoint=self.config.endpoint,
                    retry_strategy=oci.retry.NoneRetryStrategy(),
                    timeout=(10, 240),
                )
            else:
                self._client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                    config=oci_config,
                    service_endpoint=self.config.endpoint,
                    retry_strategy=oci.retry.NoneRetryStrategy(),
                    timeout=(10, 240),
                )
        return self._client

    def _convert_messages(self, messages: list[BaseMessage]) -> list:
        """Convert LangChain messages to OCI format."""
        import oci

        oci_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                role = "SYSTEM"
            elif isinstance(msg, HumanMessage):
                role = "USER"
            elif isinstance(msg, AIMessage):
                role = "ASSISTANT"
            else:
                role = "USER"

            content = oci.generative_ai_inference.models.TextContent(text=msg.content)
            oci_messages.append(
                oci.generative_ai_inference.models.Message(role=role, content=[content])
            )
        return oci_messages

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs,
    ) -> ChatResult:
        """Generate a response from OCI GenAI.

        Args:
            messages: List of messages in the conversation
            stop: Stop sequences (not supported by OCI GenAI)
            run_manager: Callback manager (unused)

        Returns:
            ChatResult with the model's response
        """
        import oci

        oci_messages = self._convert_messages(messages)

        chat_request = oci.generative_ai_inference.models.GenericChatRequest()
        chat_request.api_format = (
            oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
        )
        chat_request.messages = oci_messages
        chat_request.max_tokens = self.config.max_tokens
        chat_request.temperature = self.config.temperature
        chat_request.top_p = self.config.top_p
        chat_request.top_k = self.config.top_k
        chat_request.frequency_penalty = self.config.frequency_penalty
        chat_request.presence_penalty = self.config.presence_penalty

        chat_detail = oci.generative_ai_inference.models.ChatDetails()
        if self.config.endpoint_id:
            chat_detail.serving_mode = oci.generative_ai_inference.models.DedicatedServingMode(
                endpoint_id=self.config.endpoint_id
            )
        else:
            # Shared service — use on-demand mode with a model ID
            model_id = self.config.model_id if hasattr(self.config, "model_id") and self.config.model_id else "meta.llama-3.1-70b-instruct"
            chat_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
                model_id=model_id
            )
        chat_detail.chat_request = chat_request
        chat_detail.compartment_id = self.config.compartment_id

        response = self.client.chat(chat_detail)
        text = response.data.chat_response.choices[0].message.content[0].text

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters for this model."""
        return {
            "endpoint_id": self.config.endpoint_id,
            "compartment_id": self.config.compartment_id,
            "temperature": self.config.temperature,
        }
