"""Local dry run of the workflow's hooks and code steps on the bank's test data (no platform, no model)."""
import json, sys

wf = json.load(open("out/BRIEF.workflow.json"))
data = {c["customerNo"]: c for c in json.load(open("briefs/test-environment__test-customers.json"))["customers"]}
N = wf["nodes"]

def bank(op, d):
    c = data.get(str(d.get("customerNo") or V["customerNumber"]))
    s = c["services"].get(op)
    if s is None:
        return 404, {"result": {"returnCode": "X"}}
    if op in ("cards.balance", "statement.week.get"):
        s = s.get(d.get("cardNumber"))
    elif op in ("statement.week.decide", "statement.week.change"):
        s = (s.get(d.get("cardNumber")) or {}).get(str(d.get("newStatementWeek")))
    if s is None:
        return 404, {"result": {"returnCode": "NF"}}
    return s["http"], json.loads(json.dumps(s["response"]))

def run_api(name):
    tool = N[name]["pre_actions"][0]
    url = tool["function"]["parameters"]["properties"]["url"]["default"]
    config = {"url": url, "body": {}}
    exec(tool["pre_process_code"], {"vars": V, "config": config})
    if "blocked" in config["url"]:
        print("   BLOCKED", name, config["body"]); V[name + "_failure_count"] = 1; return
    op = url.rsplit("/", 1)[-1]
    sc, body = bank(op, config["body"]["data"])
    print("   CALL", op, config["body"]["data"], "->", sc)
    result = {"status": "success" if sc == 200 else "error", "data": body, "status_code": sc, "header": {}}
    if tool.get("post_process_code"):
        exec(tool["post_process_code"], {"vars": V, "result": result})
    for m in N[name].get("response_mapping", []):
        cur = result
        for p in m["path"].split("."):
            cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is not None:
            V[m["variable"]] = cur
    def flat(prefix, o):
        if isinstance(o, dict):
            for k, v in o.items(): flat(prefix + "." + k, v)
        else:
            V[prefix] = o
    flat(name + "_response", {"data": body, "status_code": sc})

def run_code(name):
    code = N[name]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    exec(code, {"vars": V})

def ok(c):
    if c.get("operator") == "always": return True
    if "conditions" in c:
        return any(ok(x) for x in c["conditions"]) if c.get("logic") == "or" else all(ok(x) for x in c["conditions"])
    v = V.get(c["variable"])
    if c["operator"] == "equals": return str(v) == str(c["operand"])
    if c["operator"] == "not_equals": return str(v) != str(c["operand"])
    raise Exception(c)

def route(name):
    for t in N[name]["transitions"]:
        if ok(t["condition"]): return t["target_node"]
    return None

def go(name):
    """run passthrough chain until a waiting step"""
    while True:
        n = N[name]
        oe = n.get("on_enter", {})
        if oe.get("type") == "tts":
            txt = oe["text"]
            for k, v in V.items():
                txt = txt.replace("{{" + str(k) + "}}", str(v))
            print(" SAY[%s]: %s" % (name, txt))
        if n["node_type"] == "end_call":
            print(" END:", n["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"]); return None
        if n["node_type"] == "api_request": run_api(name)
        if n["node_type"] == "code": run_code(name)
        if not n.get("passthrough"):
            return name
        name = route(name)

def user(node, **ex):
    V.update(ex)
    nxt = route(node)
    print(" USER", ex, "->", nxt)
    return go(nxt) if nxt else node

def call(cust, now, steps):
    global V
    V = {"customerNumber": cust, "now": now}
    print("=====", cust, now)
    node = go(wf["initial_node"])
    for ex in steps:
        if node is None: break
        node = user(node, **ex)

NOW = "2026-10-12T10:30:00+03:00"
call("95004361", NOW, [dict(action="main_menu")])
call("96158684", NOW, [dict(action="week"), dict(week_want="yes"), dict(week_choice="3"), dict(confirm_answer="belirsiz"), dict(confirm_answer="evet"), dict(after_kind="third_party")])
call("97526380", NOW, [dict(wants_all="yes"), dict(wants_all="yes"), dict(card_pick="Yıldız Premium"), dict(oc_reply="no"), dict(action="main_menu")])
call("92460108", NOW, [dict(action="email"), dict(send_answer="evet")])
call("96125950", NOW, [dict(action="email"), dict(action="main_menu")])
call("92030487", NOW, [dict(card_pick="Yıldız Pratik"), dict(card_pick="dört iki beş üç"), dict(card_pick="iki iki dört iki beş üç"), dict(card_pick="5450 0012 3456 4253"), dict(oc_reply="no"), dict(action="main_menu")])
call("97631186", NOW, [])
call("92311921", NOW, [])
call("92220795", NOW, [dict(card_pick="Pratik"), dict(oc_reply="yes"), dict(action="week"), dict(week_want="yes"), dict(week_choice="1"), dict(confirm_answer="evet")])
call("95813998", NOW, [dict(card_pick="Prestij"), dict(card_pick="Miles"), dict(oc_reply="no"), dict(action="main_menu")])
call("93075404", NOW, [dict(card_pick="bir dört sıfır iki")])
call("96451507", NOW, [dict(card_pick="1303")])
call("93821776", NOW, [])
call("97073972", NOW, [])
call("94907600", "2026-10-19T09:00:00+03:00", [])
call("94907600", "2026-10-25T09:00:00+03:00", [])
call("95004361", "2026-11-05T09:00:00+03:00", [])
call("93261864", NOW, [dict(card_pick="Miles"), dict(oc_reply="no"), dict(action="email"), dict(send_answer="evet")])
call("97526380", NOW, [dict(card_pick="Yıldız Premium 2000")])
call("93635512", NOW, [dict(card_pick="Platinum"), dict(oc_reply="no"), dict(action="email"), dict(send_answer="evet")])
call("98390128", NOW, [])
