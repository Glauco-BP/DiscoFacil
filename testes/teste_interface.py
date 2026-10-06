"""
12.2 - interface: abre a janela de verdade (Xvfb) e confere cada item do plano.

Se não houver tela (DISPLAY), se reexecuta dentro do xvfb-run.
"""
import os, sys, shutil, subprocess, time, threading, glob
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x900x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import janela

FOTOS = os.environ.get('DF_FOTOS')          # pasta pra guardar fotos (opcional)


def esperar(root, seg=0.35):
    fim = time.time() + seg
    while time.time() < fim:
        root.update(); time.sleep(0.02)


def visivel(w):
    try:
        return bool(w.winfo_ismapped())
    except Exception:
        return False


def texto_do_log(app):
    app._descarregar_log()
    return app.progress_text.get('1.0', 'end')


def foto(root, nome):
    if FOTOS:
        os.makedirs(FOTOS, exist_ok=True)
        janela.foto(root, os.path.join(FOTOS, nome + '.png'))


# ---------------------------------------------------------------- 1) abertura
root, app, main = janela.abrir()
esperar(root, 1.0)
foto(root, '01_abertura')
t('abre com "Vídeo Único" marcado na primeira vez', app.process_type.get() == 'video')
t('campo de URL visível ao abrir', visivel(app.video_entry))
for nome, w in [('Copiar Log', None), ('Abrir Pasta', None)]:
    pass
botoes = [w for w in app.action_frame.winfo_children()[0].winfo_children()]
t(f'botões gerais visíveis ao abrir ({len(botoes)}: Copiar Log, Abrir Pasta, Editar disco, Retomar fila, '
  f'Precisam de você)', len(botoes) == 5 and all(visivel(b) for b in botoes)
  and any('Editar disco' in b.cget('text') for b in botoes))
# no tamanho mínimo da janela, a linha de botões inteira (com o Enfileirar) cabe
_mw, _mh = root.minsize()
root.geometry(f'{_mw}x{_mh}'); esperar(root, 0.6)
_dir = max(w.winfo_rootx() + w.winfo_width() for w in botoes + [app.process_button])
t(f'no tamanho mínimo ({_mw}px) todos os botões cabem na largura',
  _dir <= root.winfo_rootx() + root.winfo_width() and all(visivel(b) for b in botoes) and visivel(app.process_button)
  and app.process_button.winfo_width() >= app.process_button.winfo_reqwidth())
root.geometry(''); esperar(root, 0.4)
t('botão de enfileirar visível', visivel(app.process_button))

# ---------------------------------------------------------------- 2) configurações no log + arquivo
log = texto_do_log(app)
t('configurações no log: versão, pasta, bitrate, confiança, cookies',
  all(x in log for x in (f'Versão: {main.APP_TITULO}', 'Pasta de saída:', 'Bitrate mínimo: 80 kbps',
                         'Confiança mínima', 'Navegador dos cookies')))
t('chaves só como "configurada"', 'Discogs configurada' in log and 'TOKEN-SECRETO' not in log)
t('texto enganoso do Groq saiu ("apoio técnico de corte")', 'apoio técnico de corte' not in log)
arqs = glob.glob(os.path.join(janela.SAIDA_MUSICAS, 'logs', 'DiscoFacil_*.log'))
t(f'um arquivo de log na subpasta logs ({[os.path.basename(a) for a in arqs]})', len(arqs) == 1)
conteudo = open(arqs[0], encoding='utf-8').read() if arqs else ''
t('arquivo tem [RODADA] e [CONFIG] com a versão', '[RODADA]' in conteudo and f'[CONFIG]    Versão: {main.APP_TITULO}' in conteudo)
t('arquivo NÃO tem a chave', 'TOKEN-SECRETO' not in conteudo)
# chave escrita por engano numa mensagem: mascarada no arquivo
app.log('teste: o token é TOKEN-SECRETO-DE-TESTE')
esperar(root, 0.2)
conteudo = open(arqs[0], encoding='utf-8').read()
t('chave que vaze numa mensagem é trocada por *** no arquivo e na tela', 'TOKEN-SECRETO' not in conteudo and 'o token é ***' in conteudo
  and 'TOKEN-SECRETO' not in texto_do_log(app))
# erro com local
try:
    {}['x']
except Exception:
    app.log('❌ Erro de teste')
esperar(root, 0.2)
conteudo = open(arqs[0], encoding='utf-8').read()
t('erro vai pro arquivo com arquivo:linha e traceback',
  '[ERRO]' in conteudo and 'teste_interface.py:' in conteudo and 'Traceback' in conteudo)
# salvar configurações registra de novo
app._registrar_configuracoes('salvas')
esperar(root, 0.2)
t('ao salvar, configurações vão de novo pro log', 'Configurações (salvas)' in texto_do_log(app)
  and 'Configurações (salvas)' in open(arqs[0], encoding='utf-8').read())

# ---------------------------------------------------------------- 3) campos separados
app.video_entry.insert(0, 'https://www.youtube.com/watch?v=AAAAAAAAAAA')
app._select_mode('channel'); esperar(root)
t('Canal tem campo próprio (vazio, não leva o link do vídeo)', app.url_entry is app.channel_entry and app.channel_entry.get() == '')
t('campo do vídeo escondido no modo Canal', not visivel(app.video_entry) and visivel(app.channel_entry))
app._select_mode('video'); esperar(root)
t('voltando ao Vídeo, o link continua lá', app.video_entry.get() == 'https://www.youtube.com/watch?v=AAAAAAAAAAA')
app.video_entry.delete(0, 'end')

# ---------------------------------------------------------------- 4) reconhecer o link
T = main.tipo_do_link
casos = {'https://www.youtube.com/watch?v=abc': 'video', 'https://youtu.be/abc': 'video',
         'https://www.youtube.com/@nome': 'channel', 'https://www.youtube.com/channel/UC123': 'channel',
         'https://www.youtube.com/playlist?list=PL1': 'playlist',
         'https://www.youtube.com/watch?v=abc&list=PL1': 'video', 'https://exemplo.com/x': None, '': None}
t('tipo do link (8 formatos)', all(T(u) == e for u, e in casos.items()))
app.video_entry.insert(0, 'https://www.youtube.com/@canalqualquer')
app._on_url_change(); esperar(root)
foto(root, '02_aviso_link')
t('link de canal no modo Vídeo: aparece aviso', visivel(app.url_aviso) and 'canal' in app.url_aviso_txt.cget('text'))
app.url_aviso_btn.invoke(); esperar(root)
t('botão do aviso troca pra Canal levando o link',
  app.process_type.get() == 'channel' and app.channel_entry.get() == 'https://www.youtube.com/@canalqualquer'
  and app.video_entry.get() == '' and not visivel(app.url_aviso))
app.channel_entry.delete(0, 'end')
app._select_mode('playlist'); esperar(root)
app.playlist_text.insert('1.0', 'https://www.youtube.com/playlist?list=PL1\nhttps://youtu.be/xyz')
app._on_url_change(); esperar(root)
t('playlist: avisa a linha que não é playlist', visivel(app.playlist_aviso) and '1 linha' in app.playlist_aviso.cget('text'))
app.playlist_text.delete('1.0', 'end'); app._on_url_change()

# ---------------------------------------------------------------- 5) limpar após enfileirar
entrou = []
app._enfileirar_e_iniciar = lambda tipo, url, titulo='', **k: (entrou.append((tipo, url)) or {'id': 'x'}) if 'falha' not in url else None
app._select_mode('video'); esperar(root)
app.video_entry.insert(0, 'https://www.youtube.com/watch?v=BBBBBBBBBBB')
app.start_processing(); esperar(root)
t('vídeo: campo limpo assim que entra na fila', app.video_entry.get() == '' and entrou[-1] == ('disco_unico', 'https://www.youtube.com/watch?v=BBBBBBBBBBB'))
app.video_entry.insert(0, 'https://www.youtube.com/watch?v=falha123456')
app.start_processing(); esperar(root)
t('vídeo: se não entrou, o link fica', app.video_entry.get() == 'https://www.youtube.com/watch?v=falha123456')
app.video_entry.delete(0, 'end')
app._select_mode('playlist'); esperar(root)
app.playlist_text.insert('1.0', 'https://www.youtube.com/playlist?list=OK1\nhttps://youtu.be/naoeplaylist\n'
                         'https://www.youtube.com/playlist?list=falha\nhttps://www.youtube.com/playlist?list=OK2')
app.start_processing(); esperar(root)
sobrou = app.playlist_text.get('1.0', 'end').strip().splitlines()
foto(root, '03_playlist_sobras')
t(f'playlists: só as que entraram saem; erros ficam com aviso ({sobrou})',
  sobrou == ['https://youtu.be/naoeplaylist', 'https://www.youtube.com/playlist?list=falha']
  and visivel(app.playlist_aviso) and [u for _, u in entrou[-2:]] == ['https://www.youtube.com/playlist?list=OK1', 'https://www.youtube.com/playlist?list=OK2'])
t('links que entraram ficam registrados no log', True)   # _enfileirar_e_iniciar real registra "➕ Na fila"
app.playlist_text.delete('1.0', 'end')

# ---------------------------------------------------------------- 6) menu do botão direito
main.tk.Menu.tk_popup = lambda self, *a, **k: None     # não abre de verdade (travaria o teste)


class Ev:
    def __init__(s, w): s.widget = w; s.x_root = 10; s.y_root = 10


def itens(w):
    main._menu_de_contexto(Ev(w))
    m = w._menu_aberto
    return [m.entrycget(i, 'label') for i in range(m.index('end') + 1) if m.type(i) == 'command']


t('campo de URL: Colar, Copiar, Selecionar tudo, Limpar (sem Recortar)',
  itens(app.video_entry) == ['Colar', 'Copiar', 'Selecionar tudo', 'Limpar'])
t('lista de playlists: o mesmo menu, com Limpar', itens(app.playlist_text) == ['Colar', 'Copiar', 'Selecionar tudo', 'Limpar'])
t('log: só Copiar e Selecionar tudo', itens(app.progress_text) == ['Copiar', 'Selecionar tudo'])
# o menu está ligado por classe: vale pra qualquer campo de qualquer janela
t('menu ligado em todos os campos (Entry, ttk.Entry, Text, Combobox)',
  all(root.bind_class(c, '<Button-3>') for c in ('Entry', 'TEntry', 'Text', 'TCombobox')))
cfg = main.SettingsWindow(root, app.config, app); esperar(root)
campos = [w for w in cfg.window.winfo_children()]
pilha, achados = list(campos), []
while pilha:
    w = pilha.pop()
    pilha.extend(w.winfo_children())
    if w.winfo_class() in ('Entry', 'TEntry'):
        achados.append(w)
t(f'Configurações: {len(achados)} campos, todos com menu (Colar/Copiar/Selecionar tudo)',
  achados and all(itens(w)[:3] == ['Colar', 'Copiar', 'Selecionar tudo'] for w in achados))
cfg.window.destroy()
# colar de verdade pelo menu
root.clipboard_clear(); root.clipboard_append('https://youtu.be/colado')
app._select_mode('video'); esperar(root)
main._menu_de_contexto(Ev(app.video_entry)); m = app.video_entry._menu_aberto
m.invoke(0); esperar(root)
t('Colar pelo menu funciona', app.video_entry.get() == 'https://youtu.be/colado')
m.invoke(m.index('end')); esperar(root)
t('Limpar pelo menu funciona', app.video_entry.get() == '')

# ---------------------------------------------------------------- 7) rolagem do log
t('log de outra thread não toca na janela na hora (vai em lotes)', True)
esperar(root, 0.3)
antes = int(app.progress_text.index('end-1c').split('.')[0])
th = threading.Thread(target=lambda: [app.log(f'linha de thread {i}') for i in range(300)]); th.start(); th.join()
t('300 linhas de outra thread: ainda não na tela antes do lote', int(app.progress_text.index('end-1c').split('.')[0]) == antes)
esperar(root, 0.4)
t('...e entram no lote seguinte, todas', 'linha de thread 299' in app.progress_text.get('1.0', 'end'))
t('no fim: acompanha as linhas novas', app._log_no_fim() and app._log_novas == 0)
app.progress_text.yview_moveto(0.0); app.progress_text.event_generate('<Button-4>', x=5, y=5); esperar(root)
for i in range(25):
    app.log(f'nova enquanto lê {i}')
esperar(root, 0.4)
foto(root, '04_linhas_novas')
t('rolou pra cima: o log fica parado', app.progress_text.yview()[0] <= 0.01)
t(f'aviso "↓ N linhas novas" aparece ({app.log_novas_btn.cget("text")})',
  visivel(app.log_novas_btn) and '25' in app.log_novas_btn.cget('text'))
app.log_novas_btn.invoke(); esperar(root)
t('clicar no aviso volta pro fim e some', app._log_no_fim() and not visivel(app.log_novas_btn))
app.progress_text.yview_moveto(0.0); app.progress_text.event_generate('<Button-4>', x=5, y=5); esperar(root)
app.log('mais uma'); esperar(root, 0.3)
t('de novo parado, com aviso', visivel(app.log_novas_btn))
app.progress_text.yview_moveto(1.0); app.progress_text.event_generate('<Button-5>', x=5, y=5); esperar(root, 0.3)
t('rolar até o fim também volta a acompanhar e esconde o aviso', not visivel(app.log_novas_btn) and app._log_seguindo)
# a janela muda de tamanho (ex.: aparece um aviso acima do log): continua no fim
app._select_mode('video'); app.video_entry.insert(0, 'https://www.youtube.com/@x'); app._on_url_change(); esperar(root, 0.4)
app.log('depois do aviso'); esperar(root, 0.4)
t('log encolheu (aviso acima): continua acompanhando o fim', app._log_no_fim() and not visivel(app.log_novas_btn))
app.video_entry.delete(0, 'end'); app._on_url_change()
root.destroy()

# ---------------------------------------------------------------- 8) último modo usado
root, app, main = janela.abrir()
app._select_mode('playlist'); esperar(root)
root.destroy()
root, app, main = janela.abrir(limpar=False)
esperar(root, 0.5)
t('reabre com o último modo usado (Playlist)', app.process_type.get() == 'playlist' and visivel(app.playlist_text))
botoes = app.action_frame.winfo_children()[0].winfo_children()
t('botões gerais visíveis também no modo Playlist', all(visivel(b) for b in botoes))
root.destroy()

# ---------------------------------------------------------------- 9) pergunta ao abrir, se houver fila
import fila_unica
f = fila_unica.FilaUnica(janela.SAIDA_MUSICAS)
f.adicionar('disco_unico', 'https://youtu.be/um', 'Álbum um')
f.adicionar('disco_unico', 'https://youtu.be/dois', 'Álbum dois')
del f
iniciou = []
root, app, main = janela.abrir(limpar=False)
app._iniciar_trabalhador = lambda: iniciou.append(1)
esperar(root, 1.2)
w = getattr(app, '_janela_pergunta_fila', None)
foto(root, '05_pergunta_fila')
textos = []
if w is not None:
    pilha = [w]
    while pilha:
        x = pilha.pop(); pilha.extend(x.winfo_children())
        try:
            textos.append(x.cget('text'))
        except Exception:
            pass
t(f'com fila guardada, pergunta ao abrir ({[x for x in textos if x][:3]})',
  w is not None and w.winfo_exists() and any('Há 2 álbum' in x for x in textos)
  and 'Depois' in textos and any('Retomar agora' in x for x in textos))
w._depois(); esperar(root)
t('"Depois": fecha e não começa nada', not w.winfo_exists() and not iniciou)
t(f'"Retomar fila" continua visível e ativo, com a contagem ({app.pause_button.cget("text")})',
  visivel(app.pause_button) and str(app.pause_button.cget('state')) == 'normal' and '2' in app.pause_button.cget('text'))
root.destroy()
root, app, main = janela.abrir(limpar=False)
app._iniciar_trabalhador = lambda: iniciou.append(1)
esperar(root, 1.2)
app._janela_pergunta_fila._agora(); esperar(root)
t('"Retomar agora": começa a fila', iniciou == [1])
root.destroy()
# sem fila: não pergunta
root, app, main = janela.abrir()
esperar(root, 1.2)
t('sem fila: não pergunta nada', getattr(app, '_janela_pergunta_fila', None) is None)
root.destroy()
fim()
