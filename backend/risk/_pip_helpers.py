import logging
L=logging.getLogger('risk._pip_helpers')
PS={'EURUSD':0.0001,'GBPUSD':0.0001,'AUDUSD':0.0001,'NZDUSD':0.0001,'USDCAD':0.0001,'USDCHF':0.0001,'EURGBP':0.0001,'EURAUD':0.0001,'EURCAD':0.0001,'EURCHF':0.0001,'EURNZD':0.0001,'GBPAUD':0.0001}
PS.update({'USDJPY':0.01,'EURJPY':0.01,'GBPJPY':0.01,'AUDJPY':0.01,'NZDJPY':0.01,'CADJPY':0.01,'CHFJPY':0.01})
PS.update({'XAUUSD':0.01,'XAGUSD':0.001,'USOIL':0.01,'US30':1.0,'US500':0.1,'BTCUSD':1.0,'ETHUSD':0.01})
PA={'GOLD':'XAUUSD','SILVER':'XAGUSD','BTC':'BTCUSD','ETH':'ETHUSD','WTI':'USOIL','DAX':'GER40','DOW':'US30'}
def _price_to_pips(s,d):
 sym=s.upper().strip()
 ps=PS.get(sym) or PS.get(PA.get(sym,''))
 if not ps:
  for t in range(1,5):
   c=sym[:-t]
   if c in PS:ps=PS[c];break
   if c in PA and PA[c] in PS:ps=PS[PA[c]];break
 if not ps:ps=0.0001
 return round(d/ps,6)
