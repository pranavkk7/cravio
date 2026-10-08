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


@require_GET
@_customers_only
def history(request):
    return JsonResponse({"enabled": agent.is_enabled(), "messages": agent.transcript(request.session)})


@require_POST
@_customers_only
def chat(request):
    if not agent.is_enabled():
        return JsonResponse({"error": "The AI assistant is not set up on this server (no ANTHROPIC_API_KEY)."}, status=503)
    cart_before = len(Cart(request.session))
    try:
        answer = agent.reply(request.session, request.POST.get("message", ""))
    except agent.AssistantError as error:
        return JsonResponse({"error": str(error)}, status=400)
    cart_count = len(Cart(request.session))
    return JsonResponse({"reply": answer, "cart_count": cart_count, "cart_changed": cart_count != cart_before})


@require_POST
@_customers_only
def reset(request):
    agent.reset(request.session)
    return JsonResponse({"ok": True})
