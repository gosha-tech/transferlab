#!/usr/bin/env python3
"""Pure synthetic tests: never publish fabricated test statistics."""
import json, pathlib, re, subprocess, sys, tempfile
import tournaments_build

ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        (root/'TransferLab_RESTORED_2026-11-16.zip').symlink_to(
          ROOT/'TransferLab_RESTORED_2026-11-16.zip')
        subprocess.check_call([sys.executable,str(ROOT/'scripts'/'prepare.py')],cwd=root,
                              stdout=subprocess.DEVNULL)
        page=(root/'_site'/'index.html').read_text(encoding='utf-8')
        person={'api_id':12345678,'name':'Phil Foden','first':'Phil','last':'Foden',
                'team':'Manchester City','team_id':50,'photo':None,
                'birth':'2000-05-28','position':'Midfielder',
                'season':'2026/27','season_year':2026}
        comp1={**person,'competition_id':39,'competition':'Premier League',
               'games':{'matches':3,'starts':2,'minutes':240,'goals':1,'assists':0}}
        comp2={**person,'competition_id':2,'competition':'UEFA Champions League',
               'games':{'matches':2,'starts':1,'minutes':100,'goals':2,'assists':1}}
        sample=root/'synthetic.json'
        sample.write_text(json.dumps({'updated_at':'2026-11-17T00:00:00+00:00',
            'status':'partial','coverage':[{'id':39,'year':2026,'loaded_pages':1,'total_pages':30}],
            'records':[comp1,comp2]}),encoding='utf-8')
        old=tournaments_build.DATA_PATH
        try:
            tournaments_build.DATA_PATH=sample
            result=tournaments_build.embed(page)
        finally:tournaments_build.DATA_PATH=old
        item=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',
                       result,re.S)
        assert item
        d=json.loads(item.group(1))
        foden=[p for p in d['players'] if p.get('name')=='Phil Foden' and p.get('team')=='Manchester City']
        assert len(foden)==1,'Must match a single existing player'
        pid=foden[0]['id']
        loaded=d['liveTournamentStats']['2026/27'][pid]
        assert {t['id'] for t in loaded}=={2,39},loaded
        assert next(x for x in loaded if x['id']==2)['stats']['goals']==2
        assert 'competitionSelect' in result and 'renderTournamentSelector' in result
        assert len({p['id'] for p in d['players']})==len(d['players'])
    print('Competition integration tests: synthetic UCL + Premier League, identity, dedup OK')
if __name__=='__main__':main()
