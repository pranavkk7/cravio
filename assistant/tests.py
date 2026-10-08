import json
from decimal import Decimal
from unittest import mock

import anthropic
import httpx2
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from restaurants.models import MenuItem, Restaurant

from . import agent, tools


class FakeResponse:
    def __init__(self, content, stop_reason):
        self._data = {"content": content, "stop_reason": stop_reason}

    def to_dict(self):
        return json.loads(json.dumps(self._data))  # a fresh copy, like a real API response


class FakeClient:
    """Plays back scripted Claude responses and records every request, so no API key or network is needed."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = mock.Mock()
        self.beta.messages.create.side_effect = self._create

    def _create(self, **params):
        # Copy the messages: the loop keeps appending to the same list after this call returns.
        self.requests.append({**params, "messages": json.loads(json.dumps(params["messages"]))})
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response


def text(message, stop_reason="end_turn"):
    return FakeResponse([{"type": "text", "text": message}], stop_reason)


def tool_call(name, tool_input, call_id="toolu_1", thinking=True):
    content = [{"type": "thinking", "thinking": "", "signature": "sig-abc"}] if thinking else []
    content.append({"type": "tool_use", "id": call_id, "name": name, "input": tool_input})
    return FakeResponse(content, "tool_use")


class AssistantTestData(TestCase):
    def setUp(self):
        def outlet(username, name, area, dishes, radius=6):
            owner = User.objects.create_user(username, password="pass12345!", role=User.Role.VENDOR)
            restaurant = Restaurant.objects.create(owner=owner, name=name, area=area, delivery_radius_km=radius,
                                                   cuisine="Biryani", prep_minutes=20)
            for dish, price, veg in dishes:
                MenuItem.objects.create(restaurant=restaurant, name=dish, price=Decimal(price), is_veg=veg, category="Mains")
            return restaurant

        self.meghana = outlet("v1", "Meghana Foods", "koramangala",
                              [("Chicken Biryani", "360", False), ("Veg Biryani", "270", True)])
        self.paradise = outlet("v2", "Biryani House", "hsr-layout", [("Mutton Biryani", "420", False)])
        self.paragon = outlet("v3", "Paragon", "nadakkavu", [("Malabar Biryani", "280", False)])
        self.chicken_biryani = MenuItem.objects.get(name="Chicken Biryani")

    def deliver_to(self, area):
        self.client.post(reverse("restaurants:set_location"), {"area": area})

    @property
    def session(self):
        return self.client.session


class ToolTests(AssistantTestData):
    def test_list_restaurants_without_a_location_uses_kannur_and_says_so(self):
        result = tools.list_restaurants(self.session)
        self.assertEqual(result["delivering_to"], "Kannur")
        self.assertEqual(result["restaurants"], [])  # the test outlets are in Bengaluru and Kozhikode
        self.assertIn("Kannur, the default", result["note"])

    def test_list_restaurants_with_a_location_lists_only_reachable_ones_nearest_first(self):
        self.deliver_to("koramangala")
        result = tools.list_restaurants(self.session)
        self.assertEqual([r["name"] for r in result["restaurants"]], ["Meghana Foods", "Biryani House"])
        self.assertIn("delivery_minutes", result["restaurants"][0])

    def test_get_menu_refuses_restaurants_that_cannot_deliver(self):
        self.deliver_to("koramangala")
        self.assertIn("error", tools.get_menu(self.session, self.paragon.pk))
        menu = tools.get_menu(self.session, self.meghana.pk)
        self.assertEqual([d["name"] for d in menu["dishes"]], ["Chicken Biryani", "Veg Biryani"])

    def test_search_filters_by_price_and_veg_and_location(self):
        self.deliver_to("koramangala")
        names = lambda **kw: [d["name"] for d in tools.search_dishes(self.session, **kw)["dishes"]]
        self.assertEqual(names(query="biryani"), ["Veg Biryani", "Chicken Biryani", "Mutton Biryani"])  # Paragon is too far
        self.assertEqual(names(query="biryani", max_price=300), ["Veg Biryani"])
        self.assertEqual(names(query="biryani", veg_only=True), ["Veg Biryani"])

    def test_add_to_cart_follows_the_same_rules_as_the_add_button(self):
        self.deliver_to("fort-road")  # Kannur
        session = self.session
        self.assertIn("does not deliver", tools.add_to_cart(session, self.chicken_biryani.pk)["error"])

        self.deliver_to("koramangala")
        session = self.session
        result = tools.add_to_cart(session, self.chicken_biryani.pk, quantity=50)
        self.assertEqual(result["cart"]["items"], [{"name": "Chicken Biryani", "quantity": 10, "subtotal_rupees": 3600.0}])

    def test_run_tool_turns_bad_input_into_an_error_result(self):
        output, failed = tools.run_tool(self.session, "get_menu", {"restaurant_id": "abc"})
        self.assertTrue(failed)
        self.assertIn("Invalid input", output)
        self.assertTrue(tools.run_tool(self.session, "delete_database", {})[1])
        self.assertTrue(tools.run_tool(self.session, "view_cart", {"surprise": 1})[1])


@override_settings(ANTHROPIC_API_KEY="test-key", CRAVIO_AI_MODEL="claude-opus-5-5", CRAVIO_AI_EFFORT="low")
class AgentLoopTests(AssistantTestData):
    def setUp(self):
        super().setUp()
        self.deliver_to("koramangala")
        self.store = self.client.session  # a session object the loop can write to

    def test_runs_the_tool_claude_asks_for_and_returns_the_final_answer(self):
        client = FakeClient(tool_call("search_dishes", {"query": "biryani", "max_price": 300}),
                            text("Try the **Veg Biryani** at Meghana Foods for ₹270."))
        answer = agent.reply(self.store, "biryani under 300", client=client)

        self.assertEqual(answer, "Try the **Veg Biryani** at Meghana Foods for ₹270.")
        second_request = client.requests[1]["messages"]
        tool_result = second_request[-1]["content"][0]
        self.assertEqual(tool_result["tool_use_id"], "toolu_1")
        self.assertFalse(tool_result["is_error"])
        self.assertEqual([d["name"] for d in json.loads(tool_result["content"])["dishes"]], ["Veg Biryani"])

    def test_history_is_append_only_and_keeps_thinking_blocks_unchanged(self):
        client = FakeClient(tool_call("view_cart", {}), text("Your cart is empty."))
        agent.reply(self.store, "what's in my cart?", client=client)
        history = self.store[agent.SESSION_KEY]
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "user", "assistant"])
        self.assertEqual(history[1]["content"][0], {"type": "thinking", "thinking": "", "signature": "sig-abc"})

        client = FakeClient(text("Sure!"))
        agent.reply(self.store, "thanks", client=client)
        self.assertEqual(client.requests[0]["messages"][:4], history)  # earlier turns sent back exactly

    def test_sends_the_configured_model_tools_and_safety_fallback(self):
        client = FakeClient(text("Hello!"))
        agent.reply(self.store, "hi", client=client)
        params = client.requests[0]
        self.assertEqual(params["model"], "claude-opus-5-5")
        self.assertEqual(params["output_config"], {"effort": "low"})
        self.assertEqual(params["fallbacks"], "default")
        self.assertEqual({t["name"] for t in params["tools"]}, set(tools.HANDLERS))

    def test_adding_through_the_assistant_fills_the_real_cart(self):
        client = FakeClient(tool_call("add_to_cart", {"item_id": self.chicken_biryani.pk, "quantity": 2}),
                            text("Added 2 Chicken Biryani."))
        agent.reply(self.store, "add two chicken biryani", client=client)
        self.assertEqual(self.store["cart"]["items"], {str(self.chicken_biryani.pk): 2})

    def test_a_refusal_gets_a_polite_answer(self):
        client = FakeClient(FakeResponse([], "refusal"))
        self.assertIn("can't help with that", agent.reply(self.store, "something unsafe", client=client))

    def test_stops_after_the_maximum_number_of_tool_rounds(self):
        client = FakeClient(*[tool_call("view_cart", {}, call_id=f"toolu_{n}") for n in range(agent.MAX_TOOL_ROUNDS)])
        answer = agent.reply(self.store, "loop forever", client=client)
        self.assertEqual(len(client.requests), agent.MAX_TOOL_ROUNDS)
        self.assertIn("couldn't finish", answer)

    def test_api_errors_become_friendly_messages_and_nothing_is_saved(self):
        error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
        with self.assertRaisesMessage(agent.AssistantError, "could not reach the AI service"):
            agent.reply(self.store, "hi", client=FakeClient(error))
        self.assertNotIn(agent.SESSION_KEY, self.store)

    def test_long_conversations_must_start_a_new_chat(self):
        self.store[agent.SESSION_KEY] = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": []}] * agent.MAX_TURNS
        with self.assertRaisesMessage(agent.AssistantError, "Start a new chat"):
            agent.reply(self.store, "one more", client=FakeClient())

    def test_transcript_shows_only_the_visible_conversation(self):
        client = FakeClient(tool_call("view_cart", {}), text("Your cart is empty."))
        agent.reply(self.store, "cart?", client=client)
        self.assertEqual(agent.transcript(self.store),
                         [{"role": "user", "text": "cart?"}, {"role": "assistant", "text": "Your cart is empty."}])


class AssistantPageTests(AssistantTestData):
    def test_without_any_api_key_the_visitor_is_asked_for_their_own(self):
        self.assertFalse(self.client.get(reverse("assistant:history")).json()["enabled"])
        response = self.client.post(reverse("assistant:chat"), {"message": "hi"})
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json()["need_key"])

    def test_a_visitor_key_is_used_for_their_request_and_never_stored(self):
        key = "sk-ant-visitor-test-key-123456"
        client = FakeClient(text("Try the chicken biryani!"))
        with mock.patch.object(agent, "client_for", return_value=client) as made:
            response = self.client.post(reverse("assistant:chat"), {"message": "biryani?"}, HTTP_X_ANTHROPIC_KEY=key)
        self.assertEqual(response.json()["reply"], "Try the chicken biryani!")
        made.assert_called_once_with(key)
        session = self.client.session
        self.assertNotIn(key, json.dumps({k: session[k] for k in session.keys()}, default=str))

    def test_a_badly_shaped_visitor_key_is_refused_before_any_api_call(self):
        with mock.patch.object(agent, "client_for") as made:
            response = self.client.post(reverse("assistant:chat"), {"message": "hi"}, HTTP_X_ANTHROPIC_KEY="hello")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["need_key"])
        made.assert_not_called()

    def test_a_rejected_visitor_key_asks_for_another(self):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        error = anthropic.AuthenticationError("invalid x-api-key", response=httpx2.Response(401, request=request), body=None)
        with mock.patch.object(agent, "client_for", return_value=FakeClient(error)):
            response = self.client.post(reverse("assistant:chat"), {"message": "hi"}, HTTP_X_ANTHROPIC_KEY="sk-ant-wrong-key-1234567890")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "That Claude API key was not accepted. Check it and try again.", "need_key": True})

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_chat_endpoint_returns_the_reply_and_the_new_cart_count(self):
        self.deliver_to("koramangala")
        client = FakeClient(tool_call("add_to_cart", {"item_id": self.chicken_biryani.pk}), text("Added it!"))
        with mock.patch.object(agent, "get_client", return_value=client):
            data = self.client.post(reverse("assistant:chat"), {"message": "add chicken biryani"}).json()
        self.assertEqual(data, {"reply": "Added it!", "cart_count": 1, "cart_changed": True})
        self.assertEqual(self.client.get(reverse("assistant:history")).json()["messages"][-1]["text"], "Added it!")

        self.client.post(reverse("assistant:reset"))
        self.assertEqual(self.client.get(reverse("assistant:history")).json()["messages"], [])

    def test_vendors_cannot_use_the_assistant_and_do_not_see_it(self):
        self.client.force_login(User.objects.get(username="v1"))
        self.assertEqual(self.client.get(reverse("assistant:history")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("restaurants:list")), "data-assistant")

    def test_customers_see_the_assistant_button(self):
        self.assertContains(self.client.get(reverse("restaurants:list")), "Ask Cravio")
