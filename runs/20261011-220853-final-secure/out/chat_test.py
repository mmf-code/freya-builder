import sys, json, time
sys.path.insert(0, "out"); sys.path.insert(0, ".")
import freya, show_call
WF = "f26dfb7e-617b-4e33-95fe-67f6d117d507"
def chat(cust, lines, now="2026-10-12T10:30:00+03:00"):
    print("=" * 20, cust)
    cid = None
    for line in lines:
        body = {"workflowId": WF, "message": line, "customerVariables": {"customerNumber": cust, "now": now}}
        if cid: body["callId"] = cid
        for attempt in range(2):
            try:
                r = freya.api("POST", "/api/v2/chat/message", body); break
            except Exception as e:
                print("  HTTP ERR", str(e)[:200]); r = None
        if not r: break
        cid = r.get("callId") or cid
        print("USER>", line); print("BOT >", r.get("response"))
    try: freya.api("POST", "/api/v2/chat/end", {"callId": cid})
    except Exception as e: print("end err", str(e)[:100])
    print("--- call", cid); show_call.show(cid)
tests = json.loads(sys.argv[1])
for t in tests:
    chat(t["c"], t["l"], t.get("now", "2026-10-12T10:30:00+03:00"))
