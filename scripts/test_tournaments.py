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
        other={**person,'api_id':99999999,'name':'Unique Test Footballer','first':'Unique','last':'Footballer',
               'team':'Example City','team_id':987,
               'competition_id':2,'competition':'UEFA Champions League',
               'games':{'matches':1,'starts':1,'minutes':90,'goals':1,'assists':0}}
        sample=root/'synthetic.json'
        sample.write_text(json.dumps({'updated_at':'2026-11-17T00:00:00+00:00',
            'status':'partial','coverage':[{'id':39,'year':2026,'loaded_pages':1,'total_pages':30}],
            'records':[comp1,comp2,other,{**other,'competition_id':39,'competition':'Premier League'}]}),encoding='utf-8')
        # Free-feed synthetic test data are never written to the published site.
        seed=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',page,re.S)
        original=json.loads(seed.group(1))
        foden_id=next(str(p['id']) for p in original['players'] if p['name']=='Phil Foden' and p['team']=='Manchester City')
        mbappe_id=next(str(p['id']) for p in original['players'] if 'Mbapp' in p['name'] and p['team']=='Real Madrid')
        hakimi_id=next(str(p['id']) for p in original['players'] if p['name']=='Achraf Hakimi' and p['team']=='Paris Saint-Germain')
        (root/'data').mkdir(exist_ok=True)
        (root/'data'/'free_sources.json').write_text(json.dumps({
            'last_success_at':'2026-11-17T00:00:00Z','profiles_verified':1,
            'players_with_current_stats':1,'matches':{
                'Premier League':[{'date':'2026-11-16','home':'Arsenal','away':'Chelsea',
                    'home_goals':2,'away_goals':1,'provider':'OpenFootball','is_player_stat':False}]
            },'players':{foden_id:{'sportsdb_id':'34500',
                'stats':[{'id':'tsdb-5999','name':'Other Competition','season':'2026/27',
                          'source':'thesportsdb_sample','stats':{'goals':2,'minutes':90}}]}}}),
          encoding='utf-8')
        pl_other=next(p for p in original['players']
                      if p.get('league')=='Premier League' and p.get('name')!='Phil Foden')
        other_pid=str(pl_other['id'])
        (root/'data'/'pl_current.json').write_text(json.dumps({
            'published_at':'2026-11-10T10:00:00',
            'players':{other_pid:{'name':pl_other['name'],'team':pl_other['team'],
                'as_of':'2026-11-10T10:00:00','stats':{'minutes':200,'starts':2,'goals':2,'assists':1}}}
        }),encoding='utf-8')
        (root/'data'/'pitchapi.json').write_text(json.dumps({
            'key_configured':True,'updated_at':'2026-11-17T19:00:00Z',
            'matches':{
                'm_B9cD4e':{'id':'m_B9cD4e','date':'2026-11-15',
                  'season':'2026/27','league':'Premier League','league_id':'l_PL1',
                  'competition_id':39,
                  'players':[{'player_id':other_pid,'pitch_id':'p_Xy1abc','team':pl_other['team'],
                              'stats':{'minutes':90,'starts':1,'goals':1,'assists':0}}]},
                'm_H3jK4l':{'id':'m_H3jK4l','date':'2026-11-18',
                  'season':'2026/27','league':'Premier League','league_id':'l_PL1',
                  'competition_id':39,
                  'players':[{'player_id':other_pid,'pitch_id':'p_Xy1abc','team':pl_other['team'],
                              'stats':{'minutes':35,'goals':0,'assists':0}}]},
                'm_C8pQ7r':{'id':'m_C8pQ7r','date':'2026-11-05',
                  'season':'2026/27','league':'Premier League','league_id':'l_PL1',
                  'competition_id':39,
                  'players':[{'player_id':other_pid,'pitch_id':'p_Xy1abc','team':pl_other['team'],
                              'stats':{'minutes':75,'goals':3,'assists':1}}]},
                'm_D1eF2g':{'id':'m_D1eF2g','date':'2026-11-16',
                  'season':'2026/27','league':'Bundesliga','league_id':'l_BUND',
                  'competition_id':78,
                  'players':[{'player_id':foden_id,'pitch_id':'p_BAD123',
                              'team':'Bayern Munich','stats':{'minutes':90,'goals':8}}]},
                'm_E1fG2h':{'id':'m_E1fG2h','date':'2026-11-16',
                  'season':'2026/27','league':'Bundesliga','league_id':'l_BUND',
                  'competition_id':78,
                  'players':[{'player_id':foden_id,'pitch_id':'p_BAD234',
                              'team':'Manchester City','stats':{'minutes':90,'goals':8}}]},
                'm_F1gH2i':{'id':'m_F1gH2i','date':'2026-11-18',
                  'season':'2026/27','league':'La Liga','league_id':'l_LL',
                  'competition_id':140,
                  'players':[{'player_id':mbappe_id,'pitch_id':'p_Mba123',
                              'team':'Real Madrid','stats':{'minutes':90,'goals':2}}]},
                'm_G2hJ3k':{'id':'m_G2hJ3k','date':'2026-11-19',
                  'season':'2026/27','league':'UEFA Champions League','league_id':'l_CL',
                  'competition_id':2,
                  'players':[{'player_id':mbappe_id,'pitch_id':'p_Mba123',
                              'team':'Real Madrid','stats':{'minutes':90,'goals':1,'xg':0.9}}]},
                'm_A1b2C3':{
                'id':'m_A1b2C3','date':'2026-11-16','season':'2026/27','league':'FA Cup',
                'league_id':'l_aB32dq','competition_id':45,'source':'PitchAPI',
                'players':[{'player_id':foden_id,'pitch_id':'p_xx0aB1',
                            'team':'Manchester City','stats':{'minutes':80,'goals':1,'xg':0.38}}]
            }}}),encoding='utf-8')
        # A trusted external season total can supply the single-match 2026
        # UEFA/French super cups, even if PitchAPI does not index the cups.
        (root/'data'/'verified_competition_totals.json').write_text(json.dumps({
          'as_of':'2026-11-22','source_primary':'https://www.besoccer.com/player/achraf-hakimi-mouh',
          'players':[{'name':'Achraf Hakimi','club':'Paris Saint-Germain',
          'season':'2026/27','competition_totals':[
            {'id':61,'name':'Ligue 1','stats':{'matches':9,'minutes':659,'goals':3,'assists':3}},
            {'id':2,'name':'UEFA Champions League',
             'stats':{'matches':4,'minutes':318,'goals':0,'assists':1}},
            {'id':'uefa-super-cup','name':'UEFA Super Cup',
             'stats':{'matches':1,'minutes':90,'goals':0,'assists':0}},
            {'id':'fr-super-cup','name':'Trophée des Champions',
             'stats':{'matches':1,'minutes':90,'goals':0,'assists':0}}
          ]}]}),encoding='utf-8')
        old=tournaments_build.DATA_PATH
        old_root=tournaments_build.ROOT
        try:
            tournaments_build.DATA_PATH=sample
            tournaments_build.ROOT=root
            result=tournaments_build.embed(page)
        finally:
            tournaments_build.DATA_PATH=old
            tournaments_build.ROOT=old_root
        item=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',
                       result,re.S)
        assert item
        d=json.loads(item.group(1))
        foden=[p for p in d['players'] if p.get('name')=='Phil Foden' and p.get('team')=='Manchester City']
        assert len(foden)==1,'Must match a single existing player'
        pid=foden[0]['id']
        loaded=d['liveTournamentStats']['2026/27'][pid]
        assert {t['id'] for t in loaded}=={2,39,45,'tsdb-5999','eng-community-shield'},loaded
        shield=next(x for x in loaded if x['id']=='eng-community-shield')
        assert shield['stats']['matches']==1 and shield['stats']['goals']==0
        assert shield['stats']['assists']==0 and shield['source']=='official_club_match_report'
        # Every City/Arsenal player has this tournament. Never show a dash
        # when the official squad proves the individual did not take part.
        contenders=[p for p in d['players'] if p.get('league')=='Premier League'
                    and p.get('team') in ('Manchester City','Arsenal')]
        assert len(contenders)>=20
        for athlete in contenders:
            cup=[x for x in d['liveTournamentStats']['2026/27'][str(athlete['id'])]
                 if str(x['id'])=='eng-community-shield']
            assert len(cup)==1,athlete['name']
            assert all(cup[0]['stats'].get(k) is not None
                       for k in ('matches','goals','assists')),athlete['name']
            assert any(x['id']=='eng-community-shield'
                       for x in d['currentCompetitionByPlayer'][str(athlete['id'])])
        assert d['verifiedClubFixtures']['city_players']>=1
        assert d['verifiedClubFixtures']['arsenal_players']>=1
        assert next(x for x in loaded if x['id']==45)['stats']['minutes']==80
        assert next(x for x in loaded if x['id']==2)['stats']['goals']==2
        assert not any(str(x['id'])=='78' for x in loaded), 'Foden must not show Bundesliga'
        hakimi=d['liveTournamentStats']['2026/27'][hakimi_id]
        assert {str(x['id']) for x in hakimi}=={'61','2','uefa-super-cup','fr-super-cup'},hakimi
        assert sum(x['stats']['matches'] for x in hakimi)==15,hakimi
        assert sum(x['stats']['minutes'] for x in hakimi)==1157,hakimi
        assert {str(x['id']) for x in hakimi if x['stats']['matches']==1}=={'uefa-super-cup','fr-super-cup'}
        assert {str(x['id']) for x in d['currentCompetitionByPlayer'][hakimi_id]} >= {'61','2','uefa-super-cup','fr-super-cup'}
        assert "$('statStarts').textContent=nf(s?.matches)" in result
        assert "'uefa-super-cup':'Суперкубок УЕФА'" in result
        assert "'fr-super-cup':'Суперкубок Франции'" in result
        madrid=d['liveTournamentStats']['2026/27'][mbappe_id]
        assert {x['id'] for x in madrid}=={2,140},madrid
        assert next(x for x in madrid if x['id']==2)['stats']['goals']==1
        assert next(x for x in madrid if x['id']==140)['stats']['goals']==2
        pl_after=next(x for x in d['liveTournamentStats']['2026/27'][other_pid] if x['id']==39)
        assert pl_after['source']=='pl_catalogue_plus_pitch'
        assert pl_after['stats']['minutes']==325,pl_after
        assert pl_after['stats']['goals']==3,pl_after
        assert pl_after['matches_loaded']==2
        assert pl_after['stats'].get('starts') is None,pl_after
        assert pl_after['stats']['starts_min']==3,pl_after
        assert 'localizeComp(id,name,ru)' in result
        # A missing present-season stat can show a clearly dated previous
        # season, but never a fabricated zero or mislabeled current season.
        assert "stats?.archived" in result and "Архив " in result
        assert "function cardStatEvidence(p)" in result
        # Position normalization is global, sample-gated and never a
        # player-specific fixed index.
        assert "function peerNormalizedIndex(p,actual,adjusted)" in result
        assert "peers.length<25" in result
        assert "Number(actual.coverage||0)<60" in result
        assert "score:calibrated.score" in result
        # Official portraits have deterministic precedence; retries do not
        # race photographic styles between page loads.
        assert "const batch=options.slice(0,1);" in result
        assert "Premier League ID portrait" in result

        # Advanced match metrics survive the Python aggregation and JS
        # tournamentSum conversion rather than disappearing from indices.
        assert d['liveIndexStats']['2026/27'][pid]['xg']==0.38
        assert 'eligibleRows(p,state.season)' in result
        assert 'verifiedProfileMeta' in result
        # The 8-role index must not equate a fullback's quality with only
        # the availability of tackle/recovery event feeds. All 100 weight
        # points remain normalized for every player at LB/RB.
        assert '"LB/RB":{"goals":9,"xg":10,"creation":37,"minutes":12,"defense":32}' in result
        assert 9+10+37+12+32==100
        assert 'const factor=share;' in result, 'Tennis-style: season gets full in-window weight'
        assert 'const sampleStrength=Math.min(1,Math.sqrt(sample/180));' in result
        assert 'return Math.max(0,Math.min(1,(dt-start)/(end-start)));' not in result
        assert '[100,100,100,0].map((n,i)=>' in result

        assert d['profileCoverage']['with_current_player_stats']>=1
        assert 'advancedCoverageNote' in result and 'advanced_metric_coverage' in result
        assert 'competitionSelect' in result and 'renderTournamentSelector' in result
        assert 'freeMatchesPanel' in result
        assert d['freeMatchResults']['Premier League'][0]['home_goals']==2
        assert d['freeSourcePlayerStats']==1
        assert len([p for p in d['players'] if p['id']=='api-football-99999999'])==1
        assert len(d['liveTournamentStats']['2026/27']['api-football-99999999'])==2
        assert len({p['id'] for p in d['players']})==len(d['players'])
    print('Competition integration tests: synthetic UCL + Premier League, identity, dedup OK')
if __name__=='__main__':main()
