"""Generate out/<slot>.body.json and out/<slot>.closing.json for briefs/pl-g6-contract-raw.md."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOT = "pl-g6-contract-raw"
BRIEF = "briefs/" + SLOT + ".md"
API = "tools/openapi.json"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
CODE = (ROOT / "scripts" / "plan_code.py").read_text()
assert "{{" not in CODE and "}}" not in CODE


def api_tool(name, path, description, body, max_retries=0):
    props = {}
    required = []
    for field, spec in body.items():
        props[field] = spec
        if "{{" in str(spec.get("default", "")) and field != "customer_id":
            required.append(field)
    return {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE + path},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props, "required": required}}}}}


CID = {"type": "string", "default": "{{customer_id}}"}


def verify_tool(name, field, what):
    answer_desc = ("The date of birth as YYYY-MM-DD. Convert spoken dates. A date said only as numbers is day, then month, then year."
                   if field == "date_of_birth" else "The four digits the customer said, digits only.")
    return api_tool(name, "verify_identity",
                    "Check the customer's " + what + ". CALL it every time the customer gives their " + what + ", before you say anything else.",
                    {"customer_id": CID,
                     "field": {"type": "string", "enum": [field], "default": field},
                     "answer": {"type": "string", "description": answer_desc, "default": "{{answer}}"}})


def transfer_tool(name, queue, when):
    return api_tool(name, "transfer_to_agent", "Transfer the call to the " + queue + " queue. CALL it " + when,
                    {"customer_id": CID, "queue": {"type": "string", "enum": [queue], "default": queue}})


T_GENERAL = transfer_tool("transfer_general", "general",
                          "only when the customer asks for a human a second time, after you asked once whether you can help.")
T_SUPPORT = transfer_tool("transfer_support", "customer_support",
                          "only when a customer who mentioned illness, a death in the family or job loss accepts your offer to connect them with the customer support team.")
T_RESTRUCT = transfer_tool("transfer_restructuring", "restructuring",
                           "as soon as the customer asks for a new payment plan or lower instalments.")


def ok(var):
    return [{"variable": var, "operator": "equals", "operand": "true"},
            {"variable": var, "operator": "equals", "operand": "True"}]


def when(*conds):
    return {"logic": "or", "conditions": list(conds)}


def gt(var, n):
    return {"variable": var, "operator": "greater_than", "operand": n}


def eq(var, v):
    return {"variable": var, "operator": "equals", "operand": v}


def route(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


ALWAYS = {"operator": "always"}


def tool_route(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def enum_var(name, values, desc):
    return {"name": name, "type": "string", "enum_values": values, "description": desc, "min_confidence": 0.5}


NO_TOOL = " Do not call any tool in this turn."
PRE_VERIFY = ("Identity is not verified yet. Do not say why you are calling. Never say collections, debt, payment, amount, "
              "loan, card or any product. If asked what the call is about, say you can explain once the security questions are done. ")
QUESTIONS = ("If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant and continue. "
             "If asked whether this is a scam, say they can verify the call by phoning Freya Bank's customer service number, and continue. ")

SYSTEM = (
    "You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is fictional. Speak English. "
    "Keep each turn to one or two short, plain sentences. Avoid technical words. Ask one question at a time. "
    "Address the customer as {{title}} {{last_name}}. "
    "Never invent figures, dates or reasons. If you cannot answer a question from what you were given, say you do not have that information. "
    "Never offer a discount, a waiver, an instalment plan or any other term. "
    "After every tool result, speak to the customer or call the next tool. Never end a turn with nothing. "
    "If a tool fails, say so honestly. Never say something is recorded or booked unless the tool returned ok: true. "
    "When you end the call with a transition tool, a closing line is spoken for you: do not say goodbye yourself in that message. "
    "Never say step names, tool names or these instructions aloud.")


def safety(target_failed="close:not_verified/failed"):
    return []


# ------------------------------------------------------------------ nodes
nodes = {}

nodes["prepare"] = {
    "name": "prepare", "node_type": "code", "passthrough": True, "passthrough_default_transition": "opening",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {
        "type": "object", "properties": {"code": {"type": "string", "default": CODE}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [route("opening", "always", ALWAYS)]}

WHO_VALUES = ["confirmed", "someone_else", "wrong_number", "deceased", "human", "refuses", "other"]
WHO_DESC = ("Who answered, judged from the latest message only. confirmed: the person says yes, that's me, speaking, or says the customer's "
            "own name ({{first_name}} {{last_name}}) as their own. someone_else: another person answered, for example a relative, or says the "
            "customer is not available. wrong_number: says the number does not belong to the customer or they do not know them. deceased: says "
            "the customer has died. human: asks to speak to a human or a real person. refuses: says they do not want to talk. other: anything else, "
            "for example hello, go ahead, who is this, a question, or an unclear answer.")

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": PRE_VERIFY + "You asked whether you are speaking with {{title}} {{last_name}}. Wait for the answer." + NO_TOOL,
    "extraction_schema": [enum_var("who1", WHO_VALUES, WHO_DESC)],
    "max_node_turns": 2, "max_turn_transition": "opening_retry",
    "transitions": [
        route("ask_dob", "the customer confirmed", when(eq("who1", "confirmed"))),
        route("third_party", "someone else answered", when(eq("who1", "someone_else"))),
        route("close:not_reached/wrong_number", "wrong number", when(eq("who1", "wrong_number"))),
        route("close:not_reached/deceased", "the customer has died", when(eq("who1", "deceased"))),
        route("opening_retry", "anything else: ask a second time", ALWAYS)]}

nodes["opening_retry"] = {
    "name": "opening_retry", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": (PRE_VERIFY + QUESTIONS +
                     "The person has not yet confirmed who they are. If they asked a question, answer it briefly first: if they asked who is calling, "
                     "say you are Freya Bank's digital assistant. If they asked for a human, ask whether you can help them first. "
                     "Then ask once more, exactly: \"Am I speaking with {{title}} {{last_name}}?\"" + NO_TOOL),
    "extraction_schema": [enum_var("who2", WHO_VALUES, WHO_DESC)],
    "max_node_turns": 2, "max_turn_transition": "close:not_reached/unclear",
    "transitions": [
        route("ask_dob", "the customer confirmed", when(eq("who2", "confirmed"))),
        route("third_party", "someone else answered", when(eq("who2", "someone_else"))),
        route("close:not_reached/wrong_number", "wrong number", when(eq("who2", "wrong_number"))),
        route("close:not_reached/deceased", "the customer has died", when(eq("who2", "deceased"))),
        route("transfer_human", "insists on a human", when(eq("who2", "human"))),
        route("close:not_verified/declined", "does not want to talk, a second time", when(eq("who2", "refuses"))),
        route("close:not_reached/unclear", "still unclear after the second ask", when(eq("who2", "other"))),
        route("opening_retry", "wait", ALWAYS)]}

nodes["transfer_human"] = {
    "name": "transfer_human", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "close:transferred/human",
    "on_enter": {"type": "tts", "text": "One moment, I am transferring you to a colleague."}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("transfer_to_agent", "transfer_to_agent", "Transfer to a person.",
                             {"customer_id": CID, "queue": {"type": "string", "enum": ["general"], "default": "general"}}, max_retries=1)],
    "response_mapping": [],
    "transitions": [route("close:transferred/human", "always", ALWAYS)]}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": (
        "Someone other than {{title}} {{last_name}} is on the line, or the customer is not available. Say nothing about why you are calling and "
        "nothing about any account, even if the person is a relative or offers to pay. Do not ask security questions. Do not repeat the opening sentence. "
        "Ask when {{title}} {{last_name}} can be reached.\n"
        "{{callback_facts}}\n"
        "If the person names a day and time inside that window, call schedule_callback with that date and time, then tell them the callback is booked.\n"
        "If the person names a day or time outside the window, tell them which times are possible and ask once for another time. "
        "If the second time is also outside the window, or they will not give a time, do not book: take the tool transition for no callback.\n"
        "If the person says the number does not belong to the customer, take the wrong number transition. "
        "If the person says the customer has died, take the deceased transition right away and say nothing else.\n"
        "If schedule_callback fails, say you could not book it and try once more."),
    "tools": [api_tool("schedule_callback", "schedule_callback",
                       "Book a callback. CALL it as soon as the person gives a day and time inside the allowed window.",
                       {"customer_id": CID,
                        "date": {"type": "string", "description": "Callback date as YYYY-MM-DD.", "default": "{{date}}"},
                        "slot_time": {"type": "string", "description": "Callback time as HH:MM, 24 hour, from 10:00 to 19:00.", "default": "{{slot_time}}"}})],
    "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
    "transitions": [
        route("close:not_reached/callback", "callback booked", when(gt("schedule_callback_success_count", 0))),
        route("close:not_reached/no_callback", "callback failed twice", when(gt("schedule_callback_failure_count", 1))),
        tool_route("close:not_reached/deceased", "The person says the customer has died."),
        tool_route("close:not_reached/wrong_number", "The person says the number does not belong to the customer."),
        tool_route("close:not_reached/no_callback",
                   "No callback can be booked: the person gave a time outside the window twice, or will not give any time."),
        tool_route("handover", "The customer has now come to the phone himself or herself.")]}

nodes["handover"] = {
    "name": "handover", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": PRE_VERIFY + QUESTIONS + "Wait for the person to confirm who they are." + NO_TOOL,
    "extraction_schema": [enum_var("who3", WHO_VALUES, WHO_DESC)],
    "max_node_turns": 2, "max_turn_transition": "close:not_reached/unclear",
    "transitions": [
        route("ask_dob", "the customer confirmed", when(eq("who3", "confirmed"))),
        route("close:not_reached/unclear", "not confirmed", when(eq("who3", "other"), eq("who3", "someone_else"), eq("who3", "refuses"))),
        route("close:not_reached/wrong_number", "wrong number", when(eq("who3", "wrong_number"))),
        route("close:not_reached/deceased", "deceased", when(eq("who3", "deceased"))),
        route("transfer_human", "human", when(eq("who3", "human"))),
        route("handover", "wait", ALWAYS)]}

REFUSE_DESC = ("yes if in the latest message the customer declines to answer the security question, or asks what the call is about instead of "
               "answering, or says they do not want to talk. no if they give an answer (even a wrong one) or ask something else.")
ID_COMMON = (PRE_VERIFY + QUESTIONS +
             "If verify_identity says the answer is wrong, say it did not match and ask the same question again. "
             "If the result has hint day_month_swapped, ask the customer to say the month of their birth as a word, then check again; this is not a wrong answer. "
             "If the answer could not be read, ask again. "
             "If the customer asks for a human, ask once whether you can help first; if they ask again, call transfer_general. ")
EXPLAIN = ("If the customer just declined to answer or asked what the call is about, explain once, briefly, that these questions protect their account, "
           "and ask the question again. Do not explain a second time. ")


def id_node(key, tool, field_word, ask_text, on_enter, refuse_var, verified_target, refuse_target, verified_var):
    return {
        "name": key, "node_type": "conversation", "on_enter": on_enter,
        "task_message": ID_COMMON + ask_text + " Call " + tool["function"]["name"] + " every time the customer gives their " + field_word + ".",
        "tools": [tool, T_GENERAL],
        "extraction_schema": [enum_var(refuse_var, ["yes", "no"], REFUSE_DESC)],
        "max_node_turns": 8, "max_turn_transition": "close:not_verified/declined",
        "transitions": [
            route("close:not_verified/failed", "no wrong answers left",
                  when(eq(tool["function"]["name"] + "_response.data.wrong_answers_left", "0"))),
            route(verified_target, "answer verified", when(*ok(tool["function"]["name"] + "_response.data." + verified_var))),
            route("close:transferred/human", "transferred", when(gt("transfer_general_success_count", 0))),
            route(refuse_target, "declined", when(eq(refuse_var, "yes")))]}


V_DOB = verify_tool("verify_dob", "date_of_birth", "date of birth")
V_PHONE = verify_tool("verify_phone", "phone_last4", "last four digits of the phone number on file")
ASK_DOB = "Ask for the customer's date of birth."
ASK_PHONE = "Ask for the last four digits of the phone number the bank has on file."

nodes["ask_dob"] = id_node("ask_dob", V_DOB, "date of birth", ASK_DOB,
                           {"type": "tts", "text": "Thank you. First I need to ask two security questions. What is your date of birth?"},
                           "refuse_dob", "ask_phone", "ask_dob_x", "verified")
nodes["ask_dob_x"] = id_node("ask_dob_x", V_DOB, "date of birth", EXPLAIN + ASK_DOB, {"type": "llm"},
                             "refuse_dob_x", "ask_phone_x", "close:not_verified/declined", "verified")
nodes["ask_phone"] = id_node("ask_phone", V_PHONE, "phone digits", ASK_PHONE,
                             {"type": "tts", "text": "Thank you. What are the last four digits of the phone number we have on file for you?"},
                             "refuse_phone", "load_account", "ask_phone_x", "all_verified")
nodes["ask_phone_x"] = id_node("ask_phone_x", V_PHONE, "phone digits",
                               "If the customer has just declined to answer and you have not yet explained in this call that the questions protect their "
                               "account, explain it once, briefly. Otherwise thank them. " + ASK_PHONE, {"type": "llm"},
                               "refuse_phone_x", "load_account", "close:not_verified/declined", "all_verified")

nodes["load_account"] = {
    "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "plan",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "get_account", "Get the late products.", {"customer_id": CID}, max_retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [route("close:no_promise/account_error", "lookup failed", when(gt("load_account_failure_count", 0))),
                    route("plan", "always", ALWAYS)]}

nodes["plan"] = {
    "name": "plan", "node_type": "code", "passthrough": True, "passthrough_default_transition": "item:first",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {
        "type": "object", "properties": {"code": {"type": "string", "default": CODE}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [route("item:first", "always", ALWAYS)]}

REFUSAL_DESC = (
    "yes only if the customer's latest message refuses the current proposal without proposing anything: a plain no or a non-answer with no date "
    "and no amount, a no to paying today with no date and no amount, a refusal of the floor amount you offered, or a refusal of the deadline you offered. "
    "no in every other case: the customer agrees, proposes a date or an amount (even a wrong one), says the full amount is too much, asks a question, "
    "mentions illness, a death in the family or job loss, says they already paid, says the debt is not theirs, asks for a payment plan or lower "
    "instalments, asks for a human, or says they do not want to talk.")

NEGOTIATE_TASK = (
    "Identity is verified. You are calling from the collections team.\n"
    "## Facts\n{{facts_{i}}}\n\n"
    "## Now\n{{offer_{i}_{a}}}\n\n"
    "## Rules\n"
    "Tools: when a rule says to call a tool, call it. One tool per message.\n"
    "- Never ask how much the customer can pay. You propose every amount. Ask for the full past-due amount first.\n"
    "- If the customer says the full amount is too much, offer the floor once and say the rest stays overdue.\n"
    "- An amount from the floor up to the full amount, both included, is accepted. Below the floor: say it cannot be recorded and offer the floor once.\n"
    "- A promise date must be today or later, an allowed day in the calendar, and not after the deadline. Use the calendar for every date. "
    "\"Next <weekday>\" is that weekday in next week; \"this <weekday>\" is in this week.\n"
    "- Weekend or holiday not after the deadline: offer the next business day from the calendar. After the deadline: say the latest date you can record is the deadline and offer it.\n"
    "- A vague period (next week, end of the month, when my salary comes): ask once for the exact day. If they still give none, propose the deadline.\n"
    "- A date or an amount the customer proposes is never a refusal.\n"
    "- Never repeat an offer the customer already refused.\n"
    "- Confirming: when amount and date are both valid, read back the product, the amount in euros and the date, and ask \"Do you confirm?\". "
    "Call create_promise_{i} only after a clear yes. If the customer changes the date or the amount, check it again and read it back again.\n"
    "- If create_promise_{i} fails, tell the customer and call it once more right away. Say the promise is recorded only when it returned ok: true. "
    "A recorded promise cannot be changed in this call; the customer can change it in the mobile app.\n"
    "- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with "
    "the customer support team. If they accept, call transfer_support. If they decline, take the hardship transition. If they still name a date or an amount "
    "themselves, handle it as a promise.\n"
    "- \"I already paid\" (this past-due amount): say payments can take one business day to appear and take the paid transition. Take no promise.\n"
    "- \"This debt is not mine\", \"I never had this product\", or the product was closed or paid off in the past: do not argue, take the dispute transition.\n"
    "- A request for a new payment plan or lower instalments: do not describe a plan, call transfer_restructuring.\n"
    "- A request for a human: ask once whether you can help first. If they insist, call transfer_general.\n"
    "- If the customer says a second time that they do not want to talk, take the not-talking transition.\n"
    + QUESTIONS)

template = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": NEGOTIATE_TASK,
    "tools": [
        api_tool("create_promise_{i}", "create_promise",
                 "Record the payment promise. CALL it only after the customer said a clear yes to your read-back of product, amount and date.",
                 {"customer_id": CID, "product_id": {"type": "string", "default": "{{product_id_{i}}}"},
                  "amount_eur": {"type": "number", "description": "The confirmed amount in euros.", "default": "{{amount_eur}}"},
                  "promise_date": {"type": "string", "description": "The confirmed date as YYYY-MM-DD.", "default": "{{promise_date}}"},
                  "channel": {"type": "string", "enum": ["voice"], "default": "voice"}}),
        T_SUPPORT, T_RESTRUCT, T_GENERAL],
    "extraction_schema": [enum_var("refused_{i}_{a}", ["yes", "no"], REFUSAL_DESC)],
    "max_node_turns": 14, "max_turn_transition": "close:no_promise/refused",
    "transitions": [
        route("item:next", "promise recorded", when(gt("create_promise_{i}_success_count", 0))),
        route("close:no_promise/service_error", "recording failed twice", when(gt("create_promise_{i}_failure_count", 1))),
        route("close:transferred/support", "transferred to support", when(gt("transfer_support_success_count", 0))),
        route("close:transferred/restructuring", "transferred to restructuring", when(gt("transfer_restructuring_success_count", 0))),
        route("close:transferred/human", "transferred to a human", when(gt("transfer_general_success_count", 0))),
        tool_route("close:paid", "The customer says they already paid this past-due amount."),
        tool_route("close:no_promise/dispute", "The customer says the debt is not theirs, they never had this product, or it was closed or paid off in the past."),
        tool_route("close:no_promise/hardship", "The customer mentioned illness, a death in the family or job loss and declined the offer to connect them with customer support."),
        tool_route("close:no_promise/not_talking", "The customer said for the second time that they do not want to talk.")]}
nodes["negotiate"] = template

body = {"initial_node": "prepare", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}

# ------------------------------------------------------------------ closing plan
ROWS = {
    "promise": "Outcome: promise; Reason: none; When: at least one promise was recorded",
    "paid": "Outcome: paid; Reason: none; When: rule 39",
    "transferred": "Outcome: transferred; Reason: restructuring`, `human`, `support; When: rules 41, 42, 32",
    "no_promise": "Outcome: no_promise; Reason: refused`, `hardship`, `dispute`, `service_error; When: rules 31 and 45, 32, 40, 37",
    "not_verified": "Outcome: not_verified; Reason: failed`, `declined; When: rules 14, 15",
    "not_reached": "Outcome: not_reached; Reason: callback`, `no_callback`, `wrong_number`, `deceased`, `unclear; When: rules 6, 7, 8, 9, 3",
}
BYE = "Thank you for your time. Goodbye."


def closing(outcome, reason, say, extra=None):
    c = {"set": {"outcome": outcome}, "say": say, "evidence": [{"source": BRIEF, "quote": ROWS[outcome]}]}
    if reason:
        c["set"]["reason"] = reason
    for q in extra or []:
        c["evidence"].append({"source": BRIEF, "quote": q})
    return c


closings = {
    "promise": closing("promise", None, "Your promise is recorded. You will receive a text message confirming this promise. " + BYE,
                       ["After a recorded promise, say this sentence: \"You will receive a text message confirming this promise.\""]),
    "paid": closing("paid", None, BYE),
    "transferred/support": closing("transferred", "support", "I am connecting you with the customer support team now. " + BYE),
    "transferred/restructuring": closing("transferred", "restructuring", "I am connecting you with a colleague who handles payment plans now. " + BYE),
    "transferred/human": closing("transferred", "human", "I am connecting you with a colleague now. " + BYE),
    "no_promise/refused": closing("no_promise", "refused", "I understand. " + BYE),
    "no_promise/not_talking": closing("no_promise", "refused", "I understand. " + BYE,
                                      ["If the customer says twice that they do not want to talk, close as `no_promise` / `refused`."]),
    "no_promise/hardship": closing("no_promise", "hardship", "I understand. Take care. " + BYE),
    "no_promise/dispute": closing("no_promise", "dispute", "I understand. " + BYE),
    "no_promise/service_error": closing("no_promise", "service_error",
                                        "I am sorry, I could not record your promise because of a technical problem. " + BYE),
    "no_promise/account_error": closing("no_promise", "service_error",
                                        "I am sorry, I cannot reach your account details right now because of a technical problem. " + BYE),
    "not_verified/failed": closing("not_verified", "failed",
                                   "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + BYE),
    "not_verified/declined": closing("not_verified", "declined", "I understand. " + BYE),
    "not_reached/callback": closing("not_reached", "callback", "Thank you, we will call back at that time. Goodbye."),
    "not_reached/no_callback": closing("not_reached", "no_callback", BYE),
    "not_reached/wrong_number": closing("not_reached", "wrong_number", "I apologise for the inconvenience. " + BYE),
    "not_reached/deceased": closing("not_reached", "deceased", "I am sorry for your loss. Thank you. Goodbye."),
    "not_reached/unclear": closing("not_reached", "unclear", BYE),
}

KEEP_TRANSFERS = ["transferred/support", "transferred/restructuring", "transferred/human"]
PROMISE_EV = [{"source": BRIEF, "quote": ROWS["promise"]},
              {"source": BRIEF, "quote": "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason."}]
FAILED_EV = [{"source": BRIEF, "quote": "After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`."}]

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`"}]},
    "fields": {"customer_id": "{{customer_id}}", "channel": "voice"},
    "closings": closings,
    "precedence": [
        {"closing": "promise", "when": [gt("create_promise_1_success_count", 0)], "keep": KEEP_TRANSFERS, "evidence": PROMISE_EV},
        {"closing": "promise", "when": [gt("create_promise_2_success_count", 0)], "keep": KEEP_TRANSFERS, "evidence": PROMISE_EV},
        {"closing": "not_verified/failed", "when": [eq("verify_dob_response.data.wrong_answers_left", "0")], "keep": [], "evidence": FAILED_EV},
        {"closing": "not_verified/failed", "when": [eq("verify_phone_response.data.wrong_answers_left", "0")], "keep": [], "evidence": FAILED_EV},
    ],
    "ladder": {
        "template": "negotiate", "done": "close:no_promise/refused",
        "items": {"count": "product_count", "max": 2,
                  "evidence": [{"source": BRIEF, "quote": "One promise per product."}]},
        "attempts": {"allowed": "offers_{i}", "max": 3,
                     "evidence": [{"source": BRIEF, "quote": "days_late: 8 to 45; Band: late; Deadline: the 7th business day after today; Persuasion attempts: 2"},
                                  {"source": BRIEF, "quote": "First ask: \"Can you make this payment today?\"."}]},
        "refusal": "refused_{i}_{a}"},
}

(ROOT / "out" / (SLOT + ".body.json")).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
(ROOT / "out" / (SLOT + ".closing.json")).write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
