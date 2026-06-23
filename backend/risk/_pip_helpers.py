import logging
L=logging.getLogger('risk._pip_helpers')
PS={'EURUSD':0.0001,'GBPUSD':0.0001}
def _price_to_pips(s,d):
 sym=s.upper().strip();ps=PS.get(sym)
 if not ps:ps=0.0001
 return round(d/ps,6)
