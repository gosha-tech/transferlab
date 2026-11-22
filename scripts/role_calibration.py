"""Fair cross-role index calibration using verified empirical peer distributions.

The model retains the full rolling 36-month tennis-style match score.
For all players with sufficient observed minutes and coverage, a cautious
45% cross-role percentile calibration (60% for fullbacks whose defensive event feeds remain less comprehensive) makes an excellent wing-back and
excellent winger comparable without a player-specific manual bonus.
"""
def inject_role_calibration(html):
    start="  function projectedIndex(p,_unused){"
    if html.count(start)!=1:
        raise RuntimeError('Unique projectedIndex not found')
    calibration=r"""  const peerIndexCalibration={};
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
    // Fixed beta anchor: 30..93 within the qualified peer distribution.
    // Blend rather than overwrite absolute 36-month performance.
    const peerTarget=30+63*percentile;
    // Fullback defensive event feeds are less comprehensive across
    // tournaments. Rely more on qualified peer-relative performance for
    // ALL LB/RB players, never on identity or headline reputation.
    const peerWeight=role==='LB/RB'?0.60:0.45;
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
       return {...actual,rawScore:actual.score,score:calibrated.score,
         roleCalibration:calibrated,"""
    if html.count(old)!=1:
        raise RuntimeError('Unique projectedIndex return marker not found')
    html=html.replace(old,new,1)
    # Make the source and beta status of relative calibration visible.
    marker="    const standing=relativeRoleRank(p);"
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
