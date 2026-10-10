import json, sys, freya
r = json.load(open(sys.argv[1]))
for pid in sys.argv[2].split(','):
    row = [x for x in r['rows'] if x['id']==pid][0]
    print('=====', pid)
    c = freya.get_call(row['call_id'])
    for m in c.get('messages', []):
        s = m.get('message') or ''
        if m.get('role') != 'system':
            print(m.get('role').upper(), '|', s); continue
        try: e = json.loads(s)
        except Exception: continue
        ev = e.get('event')
        if ev == 'variable_extracted': print('   x', e['name'], '=', e['value'], round(e.get('confidence',0),2), '| raw', e.get('raw_response','')[:200])
        elif ev == 'node_enter': print('   >', e['node'])
        elif ev == 'function_call_complete': print('   f', e.get('function'), json.dumps(e.get('result',{}).get('data') if isinstance(e.get('result'),dict) else e.get('result'))[:200])
        elif ev == 'function_call_start' and e.get('function') != 'code_exec': print('   call', e.get('function'), json.dumps(e.get('args',{}).get('body', e.get('args')))[:200])
        elif ev in ('tool_call_routing','max_turns_exceeded'): print('   !', ev, e.get('target') or e.get('tool_name'))
        elif ev not in ('route_evaluated','function_call_start'): print('   ?', json.dumps({k:v for k,v in e.items() if k!='variable_table'})[:300])
