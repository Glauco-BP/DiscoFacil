import sys
from comum import *
preparar()
if not tem_faixas_reais():
    # as faixas reais (com direitos autorais) não vão pro GitHub: sem elas, este teste não roda
    print('PULADO: faltam as faixas reais em testes/dados (não são distribuídas)')
    fim()
    sys.exit(0)
import numpy as np, main, subprocess
pos=174.216; total=174.216+239.736
c=main.SmartCutter.__new__(main.SmartCutter); c.audio_file=tmp('junto.wav'); c._rms_audio_cache=None; c._env_cache=None
logs=[]; c._log=logs.append; c.metadata={'tracks':[{'duration':177},{'duration':244}]}
c._get_total_audio_duration=lambda: total
cuts=[{'start':0,'end':pos},{'start':pos,'end':None}]
c.ajustar_ao_inicio_da_proxima(cuts); novo=cuts[0]['end']
print('\n'.join(logs))
env,dt=c._envelope_db(); i=lambda x:int(x/dt); piso=float(env.min())+1.0   # silêncio digital
t(f'Gloria 7->8 real: corte recua ({pos:.2f} -> {novo:.2f})', novo < pos-0.5)
t(f'novo corte cai no silêncio digital (nível {env[i(novo)]:.0f} dB)', env[i(novo)] <= piso)
t(f"fim da faixa 7 sem som da 8 (máx no último 1,5s: {env[i(novo-1.5):i(novo)+1].max():.0f})", env[i(novo-1.5):i(novo)+1].max() <= piso)
t(f'começo da 8 inteiro (primeiro som em {novo:.2f}+{(np.argmax(env[i(novo):]>30))*dt:.2f}s)', (np.argmax(env[i(novo):]>30))*dt >= 0.3)
# e o final real da 7 continua inteiro (a música termina ~5s antes do fim do arquivo original)
t('final da música da 7 preservado', novo > pos-3.3)
fim()
