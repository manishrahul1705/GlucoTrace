"""Explicit private HTTP smoke; run separately AFTER bundle verification. No exports."""
import argparse
from urllib.parse import urlparse
import httpx


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True)
    args=p.parse_args();u=urlparse(args.url)
    if u.hostname not in ('localhost','127.0.0.1','::1'):p.error('Loopback only')
    with httpx.Client(base_url=args.url,timeout=120) as client:
        response=client.get('/api/replay/sources');response.raise_for_status()
        local=[s for s in response.json()['sources'] if s['mode']=='local' and s['available']]
        if len(local)!=14:raise ValueError('Fourteen available local sources required')
        response=client.post('/api/replay/sessions',json=dict(source_id=local[0]['id'],scenario='clean',start='warm'))
        response.raise_for_status();session=response.json()
        if session['mode']!='local':raise ValueError('Local session required')
        identifier=session['session_id'] if 'session_id' in session else session['id']
        try:
            response=client.get(f'/api/replay/sessions/{identifier}/snapshot');response.raise_for_status()
            print('Private local HTTP creation/snapshot PASS; no accuracy or full replay claim.')
        finally:
            client.delete(f'/api/replay/sessions/{identifier}').raise_for_status()


if __name__=='__main__':main()
