"""Render verified transfer fees separately from current and genuinely historical model estimates."""
def inject_transfer_ui(html):
    anchor='<div class="verified-profile-meta" id="verifiedProfileMeta" aria-live="polite"></div>'
    if html.count(anchor)!=1:
        raise RuntimeError('Transfer UI profile metadata anchor missing')
    html=html.replace(anchor,anchor+
      '<section id="transferComparison" class="transfer-comparison" aria-live="polite" hidden></section>',1)
    marker="  function renderProfile(){"
    if html.count(marker)!=1:
        raise RuntimeError('Transfer UI render anchor missing')
    ui=r"""  function renderTransferComparison(p,model){
    const panel=$('transferComparison');
    if(!panel)return;
    const moves=ROOT.verifiedTransfersByPlayer?.[String(p.id)]||[];
    if(!moves.length){panel.hidden=true;panel.innerHTML='';return;}
    const move=moves[0];
    const ru=state.language==='ru';
    const tr=(r,e)=>ru?r:e;
    const price=value=>'€'+Number(value).toLocaleString(ru?'ru-RU':'en-GB',{
       maximumFractionDigits:1})+' '+tr('млн','m');
    const fmtDate=value=>String(value||'').slice(0,10);
    const historical=move.pre_transfer_prediction;
    // Historical predictions MUST be captured strictly before the reported
    // transfer date; current prices must NEVER be backdated.
    const validPrior=historical&&historical.as_of<move.date&&
      Number(historical.eur_m)>0;
    const current=!model.index?.proxy&&Number.isFinite(Number(model.estimate))?
      price(model.estimate):tr('нет надёжной оценки','not available');
    const fee='≈ '+price(move.reported_fee_eur_m);
    const actualText=tr('Сообщённая сумма трансфера','Reported transfer fee');
    const priorText=tr('Оценка TransferLab до сделки','Pre-transfer TransferLab valuation');
    const todayText=tr('Текущая оценка модели','Current model valuation');
    const prior=validPrior?price(historical.eur_m):
      tr('Нет сохранённого прогноза до этой сделки',
         'No forecast was archived before this deal');
    const gap=validPrior?(Number(move.reported_fee_eur_m)-Number(historical.eur_m)):null;
    const diff=gap==null?'':('<p class="transfer-gap">'+
      tr('Разница цены сделки и прежнего прогноза: ',
         'Deal price minus original forecast: ')+
      (gap>0?'+':'')+price(gap)+'</p>');
    const note=validPrior?
      (tr('Прогноз зафиксирован ','Forecast archived ')+fmtDate(historical.as_of)+
        ' · '+esc(historical.model_version||'')+
        tr(' · до перехода',' · before the transfer')):
      tr('Тогда модель не сохраняла датированные прогнозы. Сегодняшний расчёт нельзя выдавать за прогноз июля 2026 года.',
         'No dated forecast existed then. A present-day estimate is not a July 2026 prediction.');
    const details=move.guaranteed_gbp_m!=null?
      ('<p class="transfer-note">'+tr('По Sky Sports: £','Sky Sports: £')+
       Number(move.guaranteed_gbp_m).toLocaleString('en-GB')+
       tr(' млн гарантированно','m guaranteed')+
       (move.maximum_addons_gbp_m!=null?
        tr(', до £',', up to £')+Number(move.maximum_addons_gbp_m)+
           tr(' млн бонусами','m in add-ons'):'')+'.</p>'):'';
    const link=(url,label)=>/^https:\/\//.test(String(url||''))?
      '<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+
          esc(label)+'</a>':'';
    panel.hidden=false;
    panel.innerHTML='<h3>'+tr('Трансфер: цена сделки и прогноз','Transfer: deal fee vs model')+
      '</h3><p class="transfer-route">'+esc(move.from_club)+' → '+
      esc(move.to_club)+' · '+fmtDate(move.date)+'</p>'+
      '<div class="transfer-values">'+
        '<div><span>'+actualText+'</span><strong>'+fee+'</strong></div>'+
        '<div><span>'+priorText+'</span><strong>'+
          esc(prior)+'</strong></div>'+
        '<div><span>'+todayText+' · '+fmtDate(ROOT.siteBuiltAtUTC)+
          '</span><strong>'+current+'</strong></div></div>'+
      diff+'<p class="transfer-note">'+esc(note)+'</p>'+details+
      '<p class="transfer-note">'+
        tr('Сумма сообщена СМИ, не официально раскрытая точная цена. Сделка и рыночная стоимость — разные величины. ',
           'Fee reported by media, not officially disclosed exact consideration. Price and market valuation differ. ')+
        link(move.fee_source,tr('Источник суммы','Fee report'))+
        ' · '+link(move.fee_structure_source,'Sky Sports')+
        ' · '+link(move.official_source,tr('Подтверждение перехода','Confirmed transfer'))+
      '</p>';
  }
  // Dated model observations: used by scheduled GitHub Actions to record
  // genuine future pre-transfer forecasts. Fees are NEVER model inputs.
  window.transferLabForecastExport=function(){
    const forecasts={};let errors=0;
    for(const player of players){
      try{
        const model=pricedPlayer(player);
        if(!model||model.index?.proxy||!Number.isFinite(Number(model.estimate)))continue;
        forecasts[String(player.id)]={
          eur_m:Math.round(Number(model.estimate)*100)/100,
          index:model.index.score,club:player.team,
          coverage:Number(model.index.coverage||0)};
      }catch(err){errors++;}
    }
    return {as_of:String(ROOT.siteBuiltAtUTC||'').slice(0,10),
      model_version:String(MONETARY_MODEL.version||'beta'),
      forecasts,errors};
  };
"""
    html=html.replace(marker,ui+marker,1)
    existing="renderTournamentSelector(p);renderVerifiedProfileMeta(p);"
    if html.count(existing)!=1:
        raise RuntimeError('Transfer comparison render call marker missing')
    html=html.replace(existing,existing+"renderTransferComparison(p,pricedPlayer(p));",1)
    return html

def selftest():
    html='<div class="verified-profile-meta" id="verifiedProfileMeta" aria-live="polite"></div>\n'         '  function renderProfile(){\nrenderTournamentSelector(p);renderVerifiedProfileMeta(p);'
    page=inject_transfer_ui(html)
    for phrase in ('window.transferLabForecastExport=function()',
       'historical.as_of<move.date','No forecast was archived before this deal',
       'renderTransferComparison(p,pricedPlayer(p))', 'transferComparison'):
        assert phrase in page,phrase
    print('Transfer UI: strictly pre-deal price comparisons PASS')

if __name__=='__main__':selftest()
