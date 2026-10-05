"""Temporary localhost HTTP/SSE validation; save aggregates, never question details."""

import argparse
import json
import re
import urllib.error
import urllib.request

from medkg.config import ROOT


def request(path,payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('http://127.0.0.1:8000'+path,data=body,
                                 headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=150) as response:
            return response.status,response.headers.get('Content-Type',''),response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code,exc.headers.get('Content-Type',''),exc.read().decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-retrieval',action='store_true')
    args = parser.parse_args()
    checks = {}
    code,_,body = request('/health')
    checks['health_alive'] = code==200 and json.loads(body)['status']=='alive'
    code,_,body = request('/ready')
    checks['ready_graph_and_configuration'] = code==200 and json.loads(body)['neo4j']
    code,_,body = request('/ask',{'question':'I want to kill myself'})
    crisis = json.loads(body)
    checks['crisis_fixed_no_llm'] = code==200 and crisis['safety']=='crisis' and crisis['usage']['calls']==0
    code,content,body = request('/ask/stream',{'question':'I want to kill myself'})
    events = []
    for block in body.strip().split('\n\n'):
        kind = re.search(r'^event: (.+)$',block,re.M).group(1)
        data = json.loads(re.search(r'^data: (.+)$',block,re.M).group(1))
        events.append((kind,data))
    final = events[-1][1]
    streamed = ''.join(data['text'] for kind,data in events if kind=='answer')
    checks['sse_final_verified_contract'] = (code==200 and content.startswith('text/event-stream')
        and events[0][0]=='status' and events[-1][0]=='result' and streamed==final['answer']
        and all(data['trace_id']==final['trace_id'] for kind,data in events if kind=='answer'))
    code,_,_ = request('/ask',{'question':'q','history':[{}]*5})
    checks['history_bound_422'] = code==422
    code,_,body = request('/ask',{'question':'\u4f60\u597d'})
    language = json.loads(body)
    checks['english_only_no_llm'] = code==200 and language['route']=='language' and language['usage']['calls']==0
    trace_ids = [crisis['trace_id'],final['trace_id'],language['trace_id']]
    if args.include_retrieval:
        cases = [json.loads(line) for line in (ROOT/'eval/datasets/structured_v1.jsonl').read_text().splitlines()]
        case = next(c for c in cases if c['category']=='aggregation' and c['split']=='dev')
        code,_,body = request('/ask',{'question':case['question']})
        result = json.loads(body)
        checks['real_retrieval_response'] = code==200 and not result['failure_stage'] and bool(result['contexts'])
        checks['real_retrieval_source_notice'] = 'Sources:' in result['answer']
        trace_ids.append(result['trace_id'])
    records = [json.loads(line) for file in (ROOT/'runs/traces').glob('*.jsonl')
               for line in file.read_text(encoding='utf8').splitlines()]
    roots = {r['trace_id']:r for r in records if r.get('name')=='ask'}
    checks['sdk_trace_ids_match_results'] = all(t in roots and len(t)==32 for t in trace_ids)
    checks['sdk_root_route_and_tokens'] = all('route' in roots[t]['attributes']
        and 'prompt_tokens' in roots[t]['attributes'] for t in trace_ids if t in roots)
    summary = {'checks':checks,'passed':all(checks.values()),'bind':'127.0.0.1:8000',
               'real_retrieval_checked':args.include_retrieval,'clinical_validation':False}
    (ROOT/'eval/runs/api_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))
    if not summary['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
