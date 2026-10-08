"""Razorpay integration. Falls back to a simulated payment when API keys are not configured."""
import razorpay
from django.conf import settings


def razorpay_enabled() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_payment_order(order) -> str:
    """Create a Razorpay order for `order` and return its id."""
    data = {"amount": order.amount_in_paise, "currency": "INR", "receipt": f"cravio-{order.pk}"}
    return _client().order.create(data)["id"]


def verify_payment(razorpay_order_id: str, payment_id: str, signature: str) -> bool:
    """Verify the checkout signature server-side; never trust the browser's success callback alone."""
    try:
        _client().utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
