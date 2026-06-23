import logging
L=logging.getLogger('risk._pip_helpers')
PS={'EURUSD':0.0001,'GBPUSD':0.0001,'AUDUSD':0.0001,'NZDUSD':0.0001,'USDCAD':0.0001,'USDCHF':0.0001,'EURGBP':0.0001,'EURAUD':0.0001,'EURCAD':0.0001,'EURCHF':0.0001,'EURNZD':0.0001,'GBPAUD':0.0001,'USDJPY':0.01,'EURJPY':0.01,'GBPJPY':0.01,'XAUUSD':0.01,'XAGUSD':0.001,'US30':1.0,'BTCUSD':1.0}
def _price_to_pips(s,d):
 sym=s.upper().strip();ps=PS.get(sym)
 if not ps:ps=0.0001
 return round(d/ps,6)
