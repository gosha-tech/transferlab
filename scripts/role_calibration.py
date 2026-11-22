"""Fair cross-role index calibration using verified empirical peer distributions.

The model retains the full rolling 36-month tennis-style match score.
For all players with sufficient observed minutes and coverage, a cautious
45% cross-role percentile calibration (75% for fullbacks whose defensive event feeds remain less comprehensive) makes an excellent wing-back and
excellent winger comparable without a player-specific manual bonus.
"""
def inject_role_calibration(html):
    start="  function projectedIndex(p,_unused){"
    if html.count(start)!=1:
        raise RuntimeError('Unique projectedIndex not found')
    calibration=r"""  // Empirical shrinkage for archived-only, limited-metric 36-month profiles.
  // A small historic sample can have extreme goals/90 (particularly in cups)
  // without proving the same ability in a current full league campaign.
  // Never use market value or player identity to modify sporting ability.
  function indexEvidenceConfidence(p,actual,calibrated){
    const id=String(p.id),calendar=['MLS','Brasileirão'].includes(p.league);
    const seasons=calendar?['2024','2025','2026']:
      ['2023/24','2024/25','2025/26','2026/27'];
    const liveSeason=calendar?'2026':'2026/27';
    const records=seasons.map(season=>({
      season,stat:ROOT.liveIndexStats?.[season]?.[id]||null
    }));
    const trustedCurrent=records.some(({season,stat})=>season===liveSeason&&
      stat&&Number(stat.minutes)>=180&&
      !['transfermarkt_historical','historical_appearances'].includes(stat.source));
    const archiveRecords=records.filter(({stat})=>stat&&
      stat.source==='transfermarkt_historical'&&Number(stat.minutes)>0);
    const archivedOnly=!trustedCurrent&&archiveRecords.length>0&&
      records.filter(({stat})=>stat&&Number(stat.minutes)>0)
        .every(({stat})=>stat.source==='transfermarkt_historical');
    if(!archivedOnly)return {score:calibrated.score,
      provisional:false,confidence:1,sampleMinutes:Number(actual.rolling?.weightedMinutes||0)};
    const sampleMinutes=Number(actual.rolling?.weightedMinutes||0);
    const coverage=Math.max(0,Math.min(100,Number(actual.coverage||0)));
    // The neutral 50-point prior is a display-calibration prior, not
    // invented match statistics. This is deliberately conservative.
    const seasonCount=archiveRecords.filter(({stat})=>Number(stat.minutes)>=180).length;
    const minuteConfidence=Math.min(1,Math.sqrt(Math.max(0,sampleMinutes)/2600));
    const metricConfidence=Math.max(.35,Math.min(1,coverage/95));
    const historyConfidence=seasonCount<=1?.90:seasonCount===2?.97:1;
    const confidence=Math.max(.3,Math.min(1,
      minuteConfidence*metricConfidence*historyConfidence));
    const neutral=50;
    return {score:Math.round(neutral+(calibrated.score-neutral)*confidence),
      provisional:true,confidence:Math.round(confidence*100)/100,
      baseline:calibrated.score,sampleMinutes,
      reasons:['archived only','partial metric coverage','sample uncertainty'],
      seasonCount,coverage};
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
    marker="    if(roleIndex.indexConfidence?.provisional){
      const confidence=roleIndex.indexConfidence;
      facts.push(label('Архивный индекс (предварительно): ',
                       'Provisional archived index: ')+
        confidence.baseline+' → '+roleIndex.score+'/100 · '+
        Math.round(confidence.confidence*100)+'%'+
        label(' уверенности модели; без текущих подтверждённых матчей',
              ' model confidence; no verified current-season matches'));
    }
    const standing=relativeRoleRank(p);"
    if html.count(marker)!=1:
        raise RuntimeError('Profile role-rank disclosure marker not found')
    html=html.replace(marker, """    const roleIndex=projectedIndex(p);
    if(roleIndex.roleCalibration?.enabled)
      facts.push(label('Поправка сопоставимости позиций (β): ',
                       'Cross-position index calibration (beta): ')+
        roleIndex.roleCalibration.baseline+' → '+
        roleIndex.score+' / 100 · '+roleIndex.roleCalibration.peerCount+
        label(' игроков этой позиции',' players in same role'));
""" + marker,1)
    return html
