"""Cross-role calibration plus conservative reliability of a 36-month rating.

Do not change any observed match stat, manufacture an advanced metric, or
adjust sporting quality because of the player's identity or market value.
Only the displayed index is shrunk toward a neutral prior when recent sample
size and measured advanced-metric denominators cannot support an elite grade.
The calibration parameters are experimental and require out-of-sample tests.
"""
def inject_role_calibration(html):
    start="  function projectedIndex(p,_unused){"
    if html.count(start)!=1:
        raise RuntimeError('Unique projectedIndex not found')
    calibration=r"""  // Data-evidence shrinkage across ALL 36-month player histories.
  // One burst of cup goals or a partial feed must not guarantee an elite grade.
  // Never use market value or player identity to modify sporting ability.
  function indexEvidenceConfidence(p,actual,calibrated){
    // Never discount sporting ability because of market value, nationality,
    // player name or membership in Hidden Gems.
    const id=String(p.id);
    const calendar=['MLS','Brasileirão'].includes(p.league);
    const currentSeason=calendar?'2026':'2026/27';
    const previousSeason=calendar?'2025':'2025/26';
    const olderSeason=calendar?'2024':'2024/25';
    const row=season=>ROOT.liveIndexStats?.[season]?.[id]||
      statsBySeason?.[season]?.[id]||null;
    const minutes=r=>{
      const value=Number(r?.minutes);
      return Number.isFinite(value)?Math.max(0,value):0;
    };
    const current=row(currentSeason);
    const previous=row(previousSeason);
    const older=row(olderSeason);
    const source=String(current?.source||'');
    const verifiedCurrent=minutes(current)>0&&source.length>0&&
      source!=='transfermarkt_historical'&&source!=='historical_appearances';
    const currentMinutes=verifiedCurrent?minutes(current):0;
    const previousMinutes=minutes(previous);
    const olderMinutes=minutes(older);
    const sampleMinutes=Math.max(0,Number(actual.rolling?.weightedMinutes||0));
    if(!sampleMinutes)return {score:calibrated.score,
      provisional:false,confidence:1,sampleMinutes:0,
      reasons:['no measured 36-month minutes']};
    // A single productive cup spell cannot substitute for sustained
    // first-team output. Use past seasons as actual match evidence, but
    // demand more recent volume before claiming an elite overall score.
    // This shrinks only the confidence in the RATING, not match totals.
    const recentEvidence=currentMinutes+
      .60*previousMinutes+.15*olderMinutes;
    const recentFactor=Math.min(1,Math.sqrt(recentEvidence/2300));
    const sampleFactor=.80+.20*Math.min(1,Math.sqrt(sampleMinutes/3600));
    // Metric availability in a partial feed is not the same as a complete
    // 36-month observation. metricMinutes is the actually observed
    // denominator; missing xG/xA cannot be treated as full coverage.
    const measuredMinutes=r=>{
      const m=r?.metricMinutes||{};
      const keys=['xg','xa','npxg','shots','key_passes','tackles',
        'interceptions','recoveries','progressive_carries','saves'];
      return Math.max(0,...keys.map(k=>{
        const value=Number(m[k]);
        return Number.isFinite(value)?Math.max(0,value):0;
      }));
    };
    const recentMeasured=currentMinutes+
      .50*measuredMinutes(current)+measuredMinutes(previous)+
      .20*measuredMinutes(older);
    const metricFactor=.80+.20*Math.min(1,Math.sqrt(recentMeasured/1100));
    const roleCoverage=Number(actual.coverage||0);
    const coverageFactor=.80+.20*Math.min(1,Math.max(0,roleCoverage)/80);
    const confidence=Math.max(.25,Math.min(1,
      recentFactor*sampleFactor*metricFactor*coverageFactor));
    const provisional=confidence<.985;
    const score=provisional?
      Math.min(calibrated.score,
        Math.round(50+(calibrated.score-50)*confidence)):calibrated.score;
    return {score,provisional,confidence:Math.round(confidence*100)/100,
      baseline:calibrated.score,sampleMinutes,currentMinutes,
      previousMinutes,olderMinutes,metricObservedMinutes:recentMeasured,
      reasons:['recent-season first-team minutes',
        '36-month sample size','observed advanced-metric minutes'],
      recentFactor,metricFactor,coverageFactor};
  }
  const peerIndexCalibration={};
  function peerNormalizedIndex(p,actual,adjusted){
    const original=adjusted.score;
    // Low-sample records cannot justify a rank-based bonus.
    if(Number(actual.coverage||0)<60||
       Number(actual.rolling?.weightedMinutes||0)<450)
      return {score:original,enabled:false,role:actual.role};
    const role=actual.role;
    if(!peerIndexCalibration[role]){
      const sample=[];
      for(const player of players){
        const evidence=calcDraftIndex(player);
        if(!evidence||evidence.role!==role||
          Number(evidence.coverage||0)<60||
          Number(evidence.rolling?.weightedMinutes||0)<450)continue;
        const adjustedPeer=competitionAdjustedIndex(
          evidence.score,player.league||'Premier League',player);
        sample.push({id:String(player.id),score:adjustedPeer.score});
      }
      sample.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
      peerIndexCalibration[role]=sample;
    }
    const peers=peerIndexCalibration[role];
    if(peers.length<25)
      return {score:original,enabled:false,role};
    // Midrank handles tied integer scores fairly. No rank based on name,
    // historical market price, trophies or celebrity.
    let higher=0,tied=0;
    for(const item of peers){
      if(item.score>original)higher++;
      else if(item.score===original)tied++;
    }
    const percentile=Math.max(0,Math.min(1,
      (peers.length-higher-tied/2)/peers.length));
    // Fixed 30..93 beta anchor: monotone, symmetric rank calibration.
    // A convex mapping rewards high-performance role specialists while
    // separating the bottom quartile; the median remains unchanged.
    // No player names or historical valuations enter the quality index.
    const rankScaled=percentile<0.5?2*percentile*percentile:
      1-2*(1-percentile)*(1-percentile);
    const peerTarget=30+63*rankScaled;
    // All LB/RB players face patchier three-season defensive tracking.
    // Position-matched peer evidence therefore contributes 75% rather
    // than 60%, with the absolute observed score retained at 25%.
    const peerWeight=role==='LB/RB'?0.75:0.45;
    const blended=(1-peerWeight)*original+peerWeight*peerTarget;
    const score=Math.round(Math.max(1,Math.min(adjusted.ceiling,blended)));
    return {score,enabled:true,role,percentile:Math.round(percentile*100),
            peerCount:peers.length,baseline:original,
            peerTarget:Math.round(peerTarget),weight:peerWeight};
  }
"""
    html=html.replace(start,calibration+start,1)
    old="return {...actual,rawScore:actual.score,score:adjusted.score,"
    new="""const calibrated=peerNormalizedIndex(p,actual,adjusted);
       const confidence=indexEvidenceConfidence(p,actual,calibrated);
       return {...actual,rawScore:actual.score,score:confidence.score,
         exact:confidence.provisional?false:actual.exact,
         indexConfidence:confidence,roleCalibration:calibrated,"""
    if html.count(old)!=1:
        raise RuntimeError('Unique projectedIndex return marker not found')
    html=html.replace(old,new,1)
    # Make the source and beta status of relative calibration visible.
    marker="    const standing=relativeRoleRank(p);"
    coverage=r"""    // Show exactly how much of the 36-month defender rating is measured by
    // complete advanced-event sources. This is confidence, not a new bonus.
    if(roleIndex.role==='LB/RB'&&roleIndex.rolling?.weightedMinutes>0){
      const total=Number(roleIndex.rolling.weightedMinutes);
      const observed=Number(roleIndex.rolling.sampleMinutes?.defense||0);
      const coverage=Math.max(0,Math.min(1,observed/total));
      facts.push(label('Покрытие оборонительных событий: ',
                       'Defensive-event coverage: ')+
        Math.round(coverage*100)+'% · '+
        Math.round(observed)+'/'+Math.round(total)+
        label(' минут за 36 месяцев',' minutes across 36 months'));
      if(coverage<0.30)
        facts.push(label('Сравнение крайних защитников предварительное: история защитных и прогрессивных событий неполная',
                         'Fullback comparisons remain provisional: defensive and progressive-event history is incomplete'));
    }
    const standing=relativeRoleRank(p);"""
    if html.count(marker)!=1:
        raise RuntimeError('Profile role-rank disclosure marker not found')
    html=html.replace(marker, """    const roleIndex=projectedIndex(p);
    if(roleIndex.indexConfidence?.provisional){
      const confidence=roleIndex.indexConfidence;
      facts.push(label('Индекс с поправкой на достоверность (β): ',
                       'Evidence-adjusted index (beta): ')+
        confidence.baseline+' → '+roleIndex.score+'/100 · '+
        '×'+confidence.confidence.toFixed(2)+
        label(' консервативная поправка по недавним минутам и измеренным метрикам',
              ' conservative adjustment for recent minutes and observed metrics'));
    }
    if(roleIndex.roleCalibration?.enabled)
      facts.push(label('Поправка сопоставимости позиций (β): ',
                       'Cross-position index calibration (beta): ')+
        roleIndex.roleCalibration.baseline+' → '+
        roleIndex.roleCalibration.score+' / 100 · '+roleIndex.roleCalibration.peerCount+
        label(' игроков этой позиции',' players in same role'));
""" + coverage+marker,1)
    return html
