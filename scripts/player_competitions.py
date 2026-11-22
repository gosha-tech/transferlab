#!/usr/bin/env python3
"""Per-player competition choices, explicitly season- and club-scoped.

A tournament being *eligible* is not evidence the player appeared or accumulated stats.
Never show another country's league/cup unless this season's authenticated records
for the player explicitly prove an appearance after a transfer.
"""
import re,unicodedata

DOMESTIC={
 'Premier League':[('39','АПЛ'),('45','Кубок Англии (FA Cup)'),('48','Кубок лиги (Carabao Cup)')],
 'La Liga':[('140','Ла Лига'),('143','Кубок Испании')],
 'Bundesliga':[('78','Бундеслига'),('81','Кубок Германии')],
 'Serie A':[('135','Серия А'),('137','Кубок Италии')],
 'Ligue 1':[('61','Лига 1'),('66','Кубок Франции')],
 'Primeira Liga':[('94','Чемпионат Португалии'),('cup-portugal','Кубок Португалии')],
 'Belgian Pro League':[('144','Чемпионат Бельгии'),('cup-belgium','Кубок Бельгии')],
 'Süper Lig':[('203','Суперлига Турции'),('cup-turkey','Кубок Турции')],
 'Saudi Pro League':[('307','Саудовская Про-лига'),('cup-saudi','Кубок короля Саудовской Аравии')],
 'MLS':[('253','MLS')],
 'Brasileirão':[('br-league','Бразилейран'),('cup-brazil','Кубок Бразилии')],
 'Eredivisie':[('nl-league','Эредивизи'),('cup-netherlands','Кубок Нидерландов')],
 'Austrian Bundesliga':[('at-league','Бундеслига Австрии')],
 'Danish Superliga':[('dk-league','Суперлига Дании')],
 'Swiss Super League':[('ch-league','Суперлига Швейцарии')],
 'Greek Super League':[('gr-league','Чемпионат Греции')],
 'Scottish Premiership':[('sco-league','Премьершип Шотландии')],
 'EFL Championship':[('eng-2','Чемпионшип')],
 'Segunda División':[('es-2','Сегунда')],
 '2. Bundesliga':[('de-2','Вторая Бундеслига')],
 'Serie B':[('it-2','Серия B')],
 'Ligue 2':[('fr-2','Лига 2')]
}
# UEFA official league-phase participants (as of 14 Nov 2026).
# https://www.uefa.com/uefachampionsleague/news/02a8-2171a88881a0-c70193b972c6-1000--meet-the-2026-27-champions-league-what-are-the-teams-/
UCL_NAMES=[
 'AEK Athens','Arsenal','Aston Villa','Atletico Madrid','Atletico de Madrid',
 'Barcelona','Bayern Munich','Bayern München','Bodo Glimt','Bodo/Glimt',
 'Borussia Dortmund','Club Brugge','Como','Fenerbahce','Fenerbahçe',
 'Feyenoord','Galatasaray','Inter','Inter Milan','LASK','RB Leipzig','Leipzig',
 'RC Lens','Lens','Lille','Liverpool','Manchester City','Man City',
 'Manchester United','Man United','Napoli','Paris Saint-Germain','Paris SG','PSG',
 'FC Porto','Porto','PSV','Real Betis','Real Madrid','Roma','AS Roma',
 'Sabah','Shakhtar Donetsk','Shakhtar','Slavia Prague','Slavia Praha',
 'Slovan Bratislava','Sporting CP','Sporting Lisbon','VfB Stuttgart',
 'Stuttgart','Viking FK','Villarreal'
]
# Premier League official 2026/27 European qualification as published 23 Jun 2026.
# Brighton had a Conference League playoff place. Whether it progressed is not
# presumed here, so UEFA Conference appears only with actual match evidence.
UEL_NAMES=['AFC Bournemouth','Bournemouth','Sunderland','Crystal Palace']
UCL_SOURCE='https://www.uefa.com/uefachampionsleague/news/02a8-2171a88881a0-c70193b972c6-1000--meet-the-2026-27-champions-league-league-phase-teams/'
PL_SOURCE='https://www.premierleague.com/en/news/4675720/how-do-other-competitions-fixtures-affect-premier-league-and-its-clubs'

def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '').casefold())
    return re.sub('[^a-z0-9а-я]','', ''.join(c for c in t if not unicodedata.combining(c)))
UCL={norm(s) for s in UCL_NAMES}
UEL={norm(s) for s in UEL_NAMES}

def choices_for(p):
    if (p.get('origin')=='transfermarkt_archived_2026' and
        not p.get('clubSource')):
        # July archive cannot assert this club participates in 2026/27.
        return []
    league=p.get('league') or ''
    club=norm(p.get('team'))
    items=[]
    for key,name in DOMESTIC.get(league,[]):
        items.append({'id':key,'name':name,'reason':'домашний турнир клуба',
                      'data_available':False})
    if league not in ('MLS','Brasileirão') and club in UCL:
        items.append({'id':'2','name':'Лига чемпионов',
                      'reason':'участник ЛЧ 2026/27 по UEFA',
                      'source':UCL_SOURCE,'data_available':False})
    elif league=='Premier League' and club in UEL:
        items.append({'id':'3','name':'Лига Европы',
                      'reason':'участник ЛЕ 2026/27 по Премьер-лиге',
                      'source':PL_SOURCE,'data_available':False})
    # 2026 FA Community Shield: Arsenal and Manchester City played on 16 August.
    # Club participation is independent of the individual player's appearance.
    if league=='Premier League' and club in {norm('Arsenal'),norm('Manchester City'),norm('Man City')}:
        items.append({'id':'eng-community-shield','name':'Суперкубок Англии',
             'reason':'официальный матч 16.08.2026, участие клуба подтверждено',
             'source':'https://www.mancity.com/news/mens/arsenal-manchester-city-community-shield-match-report-63922483',
             'data_available':True,'club_fixture_completed':True})
    # PSG took part in both 2026/27 super cups, confirmed by official
    # UEFA and PSG fixtures, not from general UCL qualification.
    if league=='Ligue 1' and club in {norm('Paris Saint-Germain'),norm('Paris SG'),norm('PSG')}:
        items.append({'id':'uefa-super-cup','name':'Суперкубок УЕФА',
             'reason':'официальный матч 12.08.2026',
             'source':'https://www.uefa.com/uefasupercup/clubs/52747--paris-sg/matches/',
             'data_available':True})
        items.append({'id':'fr-super-cup','name':'Суперкубок Франции',
             'reason':'официальный матч 16.08.2026',
             'source':'https://www.psg.fr/en/mens-football/fixtures/season/2026-2027?competition=French_Champions%27_Trophy',
             'data_available':True})
    return items

def add_choices(root):
    root['currentCompetitionByPlayer']={
       str(p['id']):choices_for(p) for p in root.get('players',[])
       if p.get('id') is not None
    }
    root['competitionRulesAsOf']='2026-11-14'
    root['competitionRulesSource']=[UCL_SOURCE,PL_SOURCE]
    return root

def selftest():
    foden={'id':'209244','name':'Phil Foden','team':'Manchester City','league':'Premier League'}
    x=choices_for(foden)
    assert [v['id'] for v in x]==['39','45','48','2','eng-community-shield'],x
    assert not any(v['id'] in ('3','61','66') for v in x)
    hazard=choices_for({'id':'h','name':'Achraf Hakimi','team':'Paris Saint-Germain','league':'Ligue 1'})
    assert [v['id'] for v in hazard]==['61','66','2','uefa-super-cup','fr-super-cup'],hazard
    west=choices_for({'id':'x','team':'West Ham United','league':'Premier League'})
    assert [v['id'] for v in west]==['39','45','48'],west
    arsenal=choices_for({'id':'x','team':'Arsenal','league':'Premier League'})
    assert [v['id'] for v in arsenal]==['39','45','48','2','eng-community-shield'],arsenal
    le=choices_for({'id':'x','team':'Sunderland','league':'Premier League'})
    assert [v['id'] for v in le]==['39','45','48','3'],le
    la=choices_for({'id':'x','team':'FC Barcelona','league':'La Liga'})
    assert [v['id'] for v in la]==['140','143'],la
    print('Player season/club tournament eligibility PASS: Foden, Hakimi, clubs and competitions')

if __name__=='__main__':selftest()
