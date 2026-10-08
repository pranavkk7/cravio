from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from orders.cart import Cart

from . import agent


def _customers_only(view):
    """Visitors and customers may chat; vendor and admin accounts have no cart, so they get 403."""
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role != "customer":
            return JsonResponse({"error": "The assistant is for customers."}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


# Visitors may bring their own Claude API key. The browser keeps it for the tab and sends it in this
# header with each chat message; the server uses it for that request and never stores it.
KEY_HEADER = "HTTP_X_ANTHROPIC_KEY"


@require_GET
@_customers_only
def history(request):
    return JsonResponse({"enabled": agent.is_enabled(), "messages": agent.transcript(request.session)})


@require_POST
@_customers_only
def chat(request):
    try:
        key = agent.visitor_key(request.META.get(KEY_HEADER))
    except agent.AssistantError as error:
        return JsonResponse({"error": str(error), "need_key": True}, status=400)
    if not key and not agent.is_enabled():
        return JsonResponse({"error": "Add your Claude API key to chat with Ask Cravio.", "need_key": True}, status=401)
    cart_before = len(Cart(request.session))
    try:
        answer = agent.reply(request.session, request.POST.get("message", ""), client=agent.client_for(key) if key else None)
    except agent.AssistantError as error:
        return JsonResponse({"error": str(error), "need_key": isinstance(error, agent.KeyProblem)}, status=400)
    cart_count = len(Cart(request.session))
    return JsonResponse({"reply": answer, "cart_count": cart_count, "cart_changed": cart_count != cart_before})


@require_POST
@_customers_only
def reset(request):
    agent.reset(request.session)
    return JsonResponse({"ok": True})
