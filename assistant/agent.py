"""The agent loop behind "Ask Cravio".

One customer message can take several model calls: Claude asks for a tool (search dishes, read a menu,
add to cart), this code runs it and sends the result back, and that repeats until Claude writes its
answer. The conversation is kept in the visitor's session and only ever appended to, exactly as the API
returned it (including thinking blocks), because editing earlier turns invalidates them.
"""
import anthropic
from django.conf import settings

from . import tools

SESSION_KEY = "assistant_messages"
MAX_TOOL_ROUNDS = 6  # model calls per customer message; stops a confused loop from running up a bill
MAX_TURNS = 15  # customer messages per conversation, then "start a new chat"
MAX_MESSAGE_LENGTH = 500

SYSTEM_PROMPT = """You are Ask Cravio, the food-ordering assistant inside Cravio, a food delivery website \
for Kozhikode, Kannur and Bengaluru.

Help the customer decide what to eat and build their order:
- Use the tools to look things up. Only recommend restaurants and dishes that a tool returned, with the \
exact names and prices it gave. Never invent dishes, prices, offers or delivery times.
- When you recommend, give 1-3 options with the restaurant, price (₹), and the delivery time when known. \
Mention when a dish is vegetarian if that matters to the customer.
- Add dishes to the cart only when the customer asks or clearly agrees. After adding, say what is in the \
cart and that they can review it and pay from the Cart page.
- You cannot place orders, take payments, change prices or see other customers' data. Checkout is always \
done by the customer on the Cart page.
- If no delivery location is set, ask the customer to set it with the "Set location" button at the top so \
you can show what delivers to them.
- If a tool returns an error, explain it simply (for example the restaurant is too far) and offer an \
alternative.
- Stay on food and ordering. Politely decline unrelated requests.

Write short, friendly plain text (under 90 words): no tables or headings. You may put dish names in \
**bold**. The restaurants are real brands used as demo data; prices are approximate."""

FRIENDLY_ERRORS = {
    anthropic.AuthenticationError: "That Claude API key was not accepted. Check it and try again.",
    anthropic.RateLimitError: "The assistant is busy right now. Please try again in a minute.",
    anthropic.APIConnectionError: "The assistant could not reach the AI service. Please try again.",
}


class AssistantError(Exception):
    """A problem to show the customer as a friendly message."""


class KeyProblem(AssistantError):
    """The API key was refused or its account has no credit: the visitor should enter another key."""


def is_enabled():
    """True when the server has its own key. Without one, visitors can bring their own (see client_for)."""
    return bool(settings.ANTHROPIC_API_KEY)


_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60.0, max_retries=2)
    return _client


def visitor_key(raw):
    """Checks the shape of a key a visitor pasted in. The key is used for their request only: it is
    never written to the session, the database or the logs."""
    key = (raw or "").strip()
    if not key:
        return ""
    if not key.startswith("sk-ant-") or not 20 <= len(key) <= 300 or any(c.isspace() for c in key):
        raise AssistantError("That doesn't look like a Claude API key. It starts with sk-ant-.")
    return key


def client_for(key):
    """A client that bills the visitor's own Anthropic account, made fresh for this one request."""
    return anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=1)


def conversation(session):
    return session.get(SESSION_KEY, [])


def reset(session):
    session.pop(SESSION_KEY, None)


def transcript(session):
    """The visible chat: the customer's own messages and Claude's text, without tool calls or thinking."""
    lines = []
    for message in conversation(session):
        if message["role"] == "user" and isinstance(message["content"], str):
            lines.append({"role": "user", "text": message["content"]})
        elif message["role"] == "assistant":
            text = _text_of(message["content"])
            if text:
                lines.append({"role": "assistant", "text": text})
    return lines


def _text_of(content):
    return "\n\n".join(block["text"] for block in content if block.get("type") == "text" and block.get("text")).strip()


def _create(client, messages):
    return client.beta.messages.create(
        model=settings.CRAVIO_AI_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=tools.TOOLS,
        messages=messages,
        output_config={"effort": settings.CRAVIO_AI_EFFORT},
        cache_control={"type": "ephemeral"},  # tools + system + earlier turns are re-read from cache
        # If the model declines on safety grounds, the API retries on a suitable fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )


def reply(session, user_text, client=None):
    """Sends one customer message, runs any tools Claude asks for, and returns Claude's answer."""
    user_text = (user_text or "").strip()[:MAX_MESSAGE_LENGTH]
    if not user_text:
        raise AssistantError("Type a message first.")
    history = list(conversation(session))
    if sum(1 for m in history if m["role"] == "user" and isinstance(m["content"], str)) >= MAX_TURNS:
        raise AssistantError("This chat is full. Start a new chat to keep going.")

    client = client or get_client()
    history.append({"role": "user", "content": user_text})
    answer = ""
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = _create(client, history).to_dict()
            content = response["content"]
            history.append({"role": "assistant", "content": content})  # unchanged, thinking blocks included

            if response["stop_reason"] == "refusal":
                answer = "Sorry, I can't help with that. I can help you find something to eat, though!"
                break
            calls = [block for block in content if block.get("type") == "tool_use"]
            if response["stop_reason"] != "tool_use" or not calls:
                answer = _text_of(content)
                break
            # All results go back together, in one message, matched to their call ids.
            results = []
            for call in calls:
                output, failed = tools.run_tool(session, call["name"], call.get("input"))
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": output, "is_error": failed})
            history.append({"role": "user", "content": results})
    except anthropic.APIError as error:
        message = next((text for kind, text in FRIENDLY_ERRORS.items() if isinstance(error, kind)), None)
        if "credit balance" in str(error).lower():
            raise KeyProblem("That Anthropic account has no credit left. Add credit in the Anthropic console and try again.") from error
        if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            raise KeyProblem(message or "That Claude API key cannot be used. Check it and try again.") from error
        raise AssistantError(message or "Something went wrong with the assistant. Please try again.") from error

    session[SESSION_KEY] = history
    session.modified = True
    return answer or "Sorry, I couldn't finish that. Could you ask again in a simpler way?"
