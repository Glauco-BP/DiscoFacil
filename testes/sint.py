import numpy as np, wave, os
from comum import TMP
SR = 22050
rng = np.random.default_rng(7)
def musica(seg, amp=0.3):
    n=int(seg*SR); x=rng.standard_normal(n)
    x=np.convolve(x,np.ones(8)/8,'same')             # mais "grave"
    mod=0.7+0.3*np.sin(np.linspace(0,seg*1.3,n))      # dinâmica lenta, sem buracos
    return amp*x/np.std(x)*mod                          # ~ -12 dBFS, como música gravada
def silencio(seg): return np.zeros(int(seg*SR))
def ruido(seg, amp=0.003): return amp*rng.standard_normal(int(seg*SR))
def fade(x, entra=False):
    r=np.linspace(0,1,len(x)); return x*(r if entra else r[::-1])
def salvar(x, nome):
    x=np.clip(x,-1,1); d=(x*32767).astype(np.int16)
    p=os.path.join(TMP, nome)
    with wave.open(p,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(d.tobytes())
    return p
