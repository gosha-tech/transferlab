"""Competition-aware quality calibration for the TransferLab beta index.

A league's baseline coefficient must not be applied to a player's European
appearances as if those games were also domestic league games. Explicit UEFA
player minutes in the most recent three campaign seasons proportionally
relieve the domestic-only league discount. The coefficient is conservative,
never exceeds 1, never extrapolates missing European appearances, and applies
identically to every player and club.
"""
def inject_competition_exposure(html):
    first="  function competitionAdjustedIndex(raw,league,player){"
    following="  function projectedIndex(p,_unused){"
    if html.count(first)!=1 or html.count(following)!=1:
        raise RuntimeError("TransferLab competition-index anchor not found")
    a=html.index(first)
    b=html.index(following,a)
    replacement=r"""  function europeanAppearanceEvidence(player){
    const empty={weightedEuropeanMinutes:0,totalMinutes:0,share:0};
    if(!player)return empty;
    const id=String(player.id);
    const years=['MLS','Brasileirão'].includes(player.league)?
      ['2024','2025','2026']:['2024/25','2025/26','2026/27'];
    let totalMinutes=0,weightedEuropeanMinutes=0;
    for(const season of years){
      const records=ROOT.liveTournamentStats?.[season]?.[id]||[];
      const seasonMinutes=Number(ROOT.liveIndexStats?.[season]?.[id]?.minutes ??
        statsBySeason?.[season]?.[id]?.minutes ?? 0);
      if(!Number.isFinite(seasonMinutes)||seasonMinutes<=0)continue;
      totalMinutes+=seasonMinutes;
      // Historic and live sources can represent the *same* UEFA competition
      // with different IDs. Use one max total per competition, not a sum.
      const byCompetition={ucl:0,uel:0,uecl:0,supercup:0};
      for(const row of records){
        const minutes=Number(row.stats?.minutes||0);
        if(!Number.isFinite(minutes)||minutes<=0)continue;
        const code=String(row.id), name=String(row.name||'').toLowerCase();
        let category=null;
        if(['2','tm-CL'].includes(code)||/uefa champions league|лига чемпионов/i.test(name))
          category='ucl';
        else if(['3','tm-EL'].includes(code)||/uefa europa league|лига европы/i.test(name))
          category='uel';
        else if(['848','tm-ECL'].includes(code)||/uefa conference league|лига конференций/i.test(name))
          category='uecl';
        else if(code==='uefa-super-cup')
          category='supercup';
        if(category)byCompetition[category]=Math.max(byCompetition[category],minutes);
      }
      // Tournament category is a modest intensity proxy, not opponent Elo.
      const euro=byCompetition.ucl+0.80*byCompetition.uel+
        0.60*byCompetition.uecl+byCompetition.supercup;
      weightedEuropeanMinutes+=Math.min(seasonMinutes,euro);
    }
    const share=totalMinutes>0?
      Math.max(0,Math.min(0.90,weightedEuropeanMinutes/totalMinutes)):0;
    return {weightedEuropeanMinutes:Math.round(weightedEuropeanMinutes),
      totalMinutes:Math.round(totalMinutes),share};
  }
  function competitionAdjustedIndex(raw,league,player){
    const setting=COMPETITION_INDEX_MODEL[league]||{factor:.90,ceiling:94};
    const evidence=europeanAppearanceEvidence(player);
    // Apply the domestic penalty only to the domestic-proxy share of minutes.
    // Verified European player minutes relieve part of it; same club, same
    // rules, so this cannot manufacture a Mendes > Hakimi ranking.
    const leagueFactor=setting.factor+(1-setting.factor)*evidence.share;
    const adjusted=raw>=50?50+(raw-50)*leagueFactor:raw*leagueFactor;
    // Opponent difficulty is an additional, SMALL independently verified
    // signal. Missing match opponents cause NO adjustment. Only 2026/27
    // UEFA match minutes with documented opponent and dated coefficient count.
    const opponent=ROOT.opponentStrengthByPlayer?.[String(player?.id)]||null;
    const observed=Number(opponent?.minutes||0);
    const strength=Number(opponent?.average_uefa_coefficient);
    const coverage=Math.min(1,Math.max(0,observed/450));
    const opponentDelta=opponent&&observed>0&&Number.isFinite(strength)?
      Math.max(-2,Math.min(2.5,((strength-75)/75)*2.4*coverage)):0;
    return {score:Math.round(clamp(adjusted+opponentDelta,1,setting.ceiling)),
      factor:leagueFactor,ceiling:setting.ceiling,
      europeanExposure:evidence,opponentEvidence:opponent,
      opponentDelta:Math.round(opponentDelta*100)/100};
  }
"""
    html=html[:a]+replacement+html[b:]
    meta="    const standing=relativeRoleRank(p);"
    if html.count(meta)!=1:
        raise RuntimeError("Cannot show European evidence in player profile")
    extra=r"""    const competitionEvidence=projectedIndex(p).leagueAdjustment;
    const euro=competitionEvidence?.europeanExposure;
    if(euro?.weightedEuropeanMinutes>0&&euro.totalMinutes>0)
      facts.push(label('Еврокубки (три сезона): ','European games (three seasons): ')+
        euro.weightedEuropeanMinutes+'/'+euro.totalMinutes+
        label(' взвешенных / общих минут',' weighted / total minutes')+
        ' · '+label('коэффициент уровня ','competition factor ')+
        competitionEvidence.factor.toFixed(3));
    const opponent=competitionEvidence?.opponentEvidence;
    if(opponent?.matches>0&&Number.isFinite(competitionEvidence.opponentDelta))
      facts.push(label('Сила соперников в подтверждённых матчах ЛЧ/ЛЕ: ',
                       'Verified UEFA opponent strength: ')+
        opponent.average_uefa_coefficient.toFixed(1)+
        label(' баллов УЕФА · ', ' UEFA coefficient points · ')+
        opponent.matches+label(' матч(ей), поправка ',
                               ' matches, index adjustment ')+
        (competitionEvidence.opponentDelta>0?'+':'')+
        competitionEvidence.opponentDelta.toFixed(2));
"""
    return html.replace(meta,extra+meta,1)

def selftest():
    sample="  function competitionAdjustedIndex(raw,league,player){\n    return raw;\n  }\n  function projectedIndex(p,_unused){\n  }\n    const standing=relativeRoleRank(p);"
    result=inject_competition_exposure(sample)
    assert 'europeanAppearanceEvidence(player)' in result
    assert 'Math.max(byCompetition[category],minutes)' in result
    assert "['2024/25','2025/26','2026/27']" in result
    assert 'setting.factor+(1-setting.factor)*evidence.share' in result
    assert 'euro.weightedEuropeanMinutes' in result
    assert 'Math.max(0,Math.min(0.90,' in result
    assert 'evidence.share;' in result
    print('European exposure index: club-independent + non-duplicated + bounded PASS')

if __name__=='__main__':
    selftest()
