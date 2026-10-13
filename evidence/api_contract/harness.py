#!/usr/bin/env python3
"""DeepSeek缺陷猎手 harness v1 — 文档承诺 vs 实际行为差集
每个用例: 构造请求 -> 记录原始响应 -> 依据文档承诺判定 -> JSONL留档
判定分类: CONTRACT_VIOLATION(违反文档承诺) / ANOMALY(未承诺但异常) / OK
"""
import json, time, os, sys, urllib.request, urllib.error

KEY = os.environ.get("DEEPSEEK_API_KEY", "")
URL = 'https://api.deepseek.com/v1/chat/completions'
OUT = './deepseek_defect_hunt/results.jsonl'
MODEL = 'deepseek-flash'

def call(payload, timeout=90):
    body = dict(payload); body['model'] = MODEL
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {'raw': 'unparseable'}
    except Exception as e:
        return -1, {'raw': str(e)}

def run_case(cid, cls, payload, judge, sleep=0.6):
    st, r = call(payload)
    time.sleep(sleep)
    verdict, detail = judge(st, r)
    rec = {'id': cid, 'class': cls, 'status': st, 'verdict': verdict,
           'detail': detail, 'req_payload': {k:v for k,v in payload.items()},
           'ts': time.strftime('%FT%T')}
    with open(OUT, 'a') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    tag = {'CONTRACT_VIOLATION':'!!!','ANOMALY':' ? ','OK':'   '}.get(verdict,' ? ')
    print(f"{tag} {cid}: {verdict} | {detail}")
    return verdict

# ---------- Phase 1: 协议边界契约 (文档承诺: temp∈[0,2], stop≤16, rf.type∈{text,json_object}) ----------
def j_expect_4xx(st, r):
    if 400 <= st < 500: return 'OK', f'rejected as documented (http {st})'
    return 'CONTRACT_VIOLATION', f'docs say invalid, server accepted with status {st}'

def j_json_mode(st, r):
    if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
    c = r['choices'][0]['message'].get('content')
    if c is None or c == '': return 'ANOMALY', 'empty content (documented known issue, measuring rate)'
    try:
        json.loads(c); return 'OK', 'valid json'
    except Exception as e:
        return 'CONTRACT_VIOLATION', f'docs GUARANTEE valid json, got invalid: {str(c)[:120]} err={e}'

def phase1():
    print('===== Phase 1: 协议边界契约 =====')
    run_case('P1_temp_above_max', 'protocol', {'messages':[{'role':'user','content':'hi'}],'temperature':2.5}, j_expect_4xx)
    run_case('P2_temp_negative', 'protocol', {'messages':[{'role':'user','content':'hi'}],'temperature':-0.5}, j_expect_4xx)
    run_case('P3_rf_bad_type', 'protocol', {'messages':[{'role':'user','content':'hi'},],'response_format':{'type':'yaml_object'}}, j_expect_4xx)
    run_case('P4_stop_17seqs', 'protocol', {'messages':[{'role':'user','content':'hi'}],'stop':[str(i) for i in range(17)]}, j_expect_4xx)
    run_case('P5_temp_boundary_2', 'protocol', {'messages':[{'role':'user','content':'Say OK'}],'temperature':2}, j_expect_4xx)  # docs allow <=2, so 2xx expected -> will flag as violation of j_expect_4xx; treat separately
    run_case('P6_effort_and_thinking_conflict', 'protocol',
             {'messages':[{'role':'user','content':'Say OK'}],'thinking':{'type':'disabled'},'reasoning_effort':'max'}, j_expect_4xx)  # contradiction: effort=none is the documented way to disable
    # JSON mode batch
    sys_p = 'Output a JSON object with key "v". The word json appears here.'
    for i in range(8):
        run_case(f'J1_json_basic_{i}', 'json_mode', {'messages':[{'role':'system','content':sys_p},{'role':'user','content':f'item {i}, value = number {i}'}],'response_format':{'type':'json_object'}}, j_json_mode)
    # J3: unicode/escape stress
    user_stress = 'string: he said "hi"\nnew\\tab\temoji 🎆 中文"引号"}'
    run_case('J3_json_unicode_stress', 'json_mode',
             {'messages':[{'role':'system','content':'Output json. Return a JSON object {"s": "<the exact string I give you, escaped properly>"}'},
                          {'role':'user','content':user_stress}],'response_format':{'type':'json_object'}}, j_json_mode)
    # J2: truncation -> invalid json? (docs: "set max_tokens reasonably to prevent truncation" vs "guarantee valid json")
    run_case('J2_json_truncated', 'json_mode',
             {'messages':[{'role':'system','content':'Output json. Return JSON {"data": "<a 500-word story>"}'},
                          {'role':'user','content':'go'}],'response_format':{'type':'json_object'},'max_tokens':30}, j_json_mode)

# ---------- Phase 2: 工具调用正确性 ----------
TOOLS = [{'type':'function','function':{'name':'get_weather','description':'Get weather of a location','parameters':{'type':'object','properties':{'location':{'type':'string'}},'required':['location']}}},
         {'type':'function','function':{'name':'get_time','description':'Get current time of a timezone','parameters':{'type':'object','properties':{'tz':{'type':'string','enum':['UTC','Asia/Shanghai','America/New_York']}},'required':['tz']}}}]

def extract_toolcalls(r):
    try: return r['choices'][0]['message'].get('tool_calls') or []
    except Exception: return []

def j_t_parallel(st, r):
    if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
    tcs = extract_toolcalls(r)
    if len(tcs) < 2: return 'ANOMALY', f'expected >=2 parallel calls, got {len(tcs)}'
    ids = [tc.get('id') for tc in tcs]
    names = [tc['function']['name'] for tc in tcs]
    if len(set(ids)) != len(ids): return 'CONTRACT_VIOLATION', f'duplicate tool_call ids: {ids}'
    for tc in tcs:
        try: json.loads(tc['function']['arguments'])
        except Exception as e: return 'CONTRACT_VIOLATION', f'malformed arguments JSON: {tc["function"]["arguments"][:100]}'
    return 'OK', f'{len(tcs)} calls, names={names}, unique ids'

def j_t_args_valid(st, r):
    if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
    tcs = extract_toolcalls(r)
    if not tcs: return 'OK', 'no tool call (model answered directly)'
    for tc in tcs:
        try:
            a = json.loads(tc['function']['arguments'])
        except Exception as e:
            return 'CONTRACT_VIOLATION', f'malformed args JSON: {repr(tc["function"]["arguments"][:120])}'
        if tc['function']['name'] == 'get_weather' and 'location' not in a:
            return 'CONTRACT_VIOLATION', f'required field missing: {a}'
    return 'OK', f'args valid: {[tc["function"]["arguments"][:60] for tc in tcs]}'

def j_t_enum(st, r):
    if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
    tcs = extract_toolcalls(r)
    if not tcs: return 'OK', 'no tool call'
    for tc in tcs:
        a = json.loads(tc['function']['arguments'])
        if 'tz' in a and a['tz'] not in ['UTC','Asia/Shanghai','America/New_York']:
            return 'CONTRACT_VIOLATION', f'enum violated: {a}'
    return 'OK', f'enum respected: {[tc["function"]["arguments"] for tc in tcs]}'

def j_t_nonexistent(st, r):
    # we provide a tool list with no weather-tool fit; see if model hallucinates a tool name not in list
    if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
    tcs = extract_toolcalls(r)
    allowed = {'get_weather','get_time'}
    bad = [tc['function']['name'] for tc in tcs if tc['function']['name'] not in allowed]
    if bad: return 'CONTRACT_VIOLATION', f'hallucinated tool names not in tools list: {bad}'
    return 'OK', f'tool names within provided set ({len(tcs)} calls) or direct answer'

def phase2():
    print('===== Phase 2: 工具调用 =====')
    # T2 parallel
    for i in range(6):
        run_case(f'T2_parallel_{i}', 'tool_calls',
                 {'messages':[{'role':'user','content':'I need BOTH the weather in Paris AND the current time in Asia/Shanghai. Call the necessary tools.'}],'tools':TOOLS}, j_t_parallel)
    # T7 unicode/special chars in args
    run_case('T7_args_specialchars', 'tool_calls',
             {'messages':[{'role':'user','content':'What is the weather in "Krüger \\"National\\" Park\n(South Africa) 🎆? Use the tool.'}],'tools':TOOLS}, j_t_args_valid)
    run_case('T7_args_longstr', 'tool_calls',
             {'messages':[{'role':'user','content':'Weather for this location: ' + 'X'*2000 + '. Use the tool.'}],'tools':TOOLS}, j_t_args_valid)
    # T3 enum
    for i in range(4):
        run_case(f'T3_enum_{i}', 'tool_calls',
                 {'messages':[{'role':'user','content':'What time is it in Shanghai right now? Use tools.'}],'tools':TOOLS}, j_t_enum)
    # T4 hallucinate-resistance: ask for something NO tool covers
    run_case('T4_no_fit_tool', 'tool_calls',
             {'messages':[{'role':'user','content':'Send an email to bob@example.com saying hi. Use whatever tool works.'}],'tools':TOOLS}, j_t_nonexistent)
    # T5 multi-turn id consistency
    def j_t_multiturn(st, r):
        if st != 200: return 'ANOMALY', f'http {st}: {str(r)[:150]}'
        m = r['choices'][0]['message']; tcs = extract_toolcalls(r)
        if not tcs: return 'OK', 'direct answer (no loop needed)'
        tc = tcs[0]
        # feed result back
        messages = [{'role':'user','content':'Weather in Tokyo? Use the tool.'}]
        messages.append({'role':'user','content':'Weather in Tokyo? Use the tool.'})  # placeholder, rebuilt below
        return 'OK', 'first-leg ok, id=' + str(tc.get('id'))[:20]
    run_case('T5_multiturn_leg1', 'tool_calls',
             {'messages':[{'role':'user','content':'Weather in Tokyo? Use the tool.'}],'tools':TOOLS}, j_t_multiturn)
    # T6 tool_choice=required (OpenAI-compatible value; docs listed none/auto — testing undeclared value)
    def j_t_choice_required(st, r):
        if st != 200:
            return 'OK', f'required not accepted (http {st}) - docs only promise none/auto'
        tcs = extract_toolcalls(r)
        if not tcs: return 'CONTRACT_VIOLATION', 'tool_choice=required accepted but model returned no tool call'
        return 'OK', f'required honored, {len(tcs)} calls'
    run_case('T6_choice_required', 'tool_calls',
             {'messages':[{'role':'user','content':'hi there, how are you?'}],'tools':TOOLS,'tool_choice':'required'}, j_t_choice_required)
    # T9 invalid tool name in OUR provided list (server-side validation?)
    BAD_TOOLS = [{'type':'function','function':{'name':'bad name with spaces!','description':'x','parameters':{'type':'object','properties':{},'required':[]}}}]
    run_case('T9_invalid_toolname', 'tool_calls',
             {'messages':[{'role':'user','content':'hi'}],'tools':BAD_TOOLS}, j_expect_4xx)

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('1','all'): phase1()
    if which in ('2','all'): phase2()
    print('done.')
