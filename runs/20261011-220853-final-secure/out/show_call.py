import freya, json, sys
def show(call_id):
    c = freya.get_call(call_id)
    print("ended:", c.get("endedReason"))
    for m in c["messages"]:
        if m["role"] in ("assistant", "user"): print(m["role"].upper(), ":", m["message"])
        elif m["role"] == "system":
            try: e = json.loads(m["message"])
            except Exception: continue
            ev = e.get("event")
            if ev == "function_call_start": print("  CALL", json.dumps(e.get("args"), ensure_ascii=False)[:500])
            elif ev == "function_call_complete": print("  RESULT", json.dumps(e.get("result"), ensure_ascii=False)[:200])
            elif ev == "error": print("  ERROR", str(e)[:400])
            elif ev == "node_enter": print("  >", e.get("node"))
if __name__ == "__main__":
    show(sys.argv[1])
