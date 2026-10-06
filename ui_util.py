"""
Peças de interface reaproveitadas: ícones, menu de contexto (copiar/colar)
em todo campo, botão de ajuda "?", e o tipo de um link do YouTube (vídeo,
canal, playlist) pra avisar quando não combina com o modo.
"""
import sys
import webbrowser
import tkinter as tk
from pathlib import Path
from typing import Optional


class Cores:
    """Paleta única: janela principal, fila, "Precisam de você", busca e Configurações."""
    COLOR_ACCENT = "#4F46E5"
    COLOR_ACCENT_DARK = "#3730A3"
    COLOR_ACCENT_LIGHT = "#EEF2FF"
    COLOR_BG = "#F1F5F9"
    COLOR_CARD = "#FFFFFF"
    COLOR_BORDER = "#E2E8F0"
    COLOR_TEXT = "#1E293B"
    COLOR_TEXT_MUTED = "#64748B"
    COLOR_SUCCESS = "#16A34A"
    COLOR_ERROR = "#DC2626"
    COLOR_WARNING = "#D97706"


def _resolve_icon_path(filename: str) -> Optional[str]:
    """
    Caminho de um ícone, rodando como .py (ao lado do módulo) ou empacotado
    pelo PyInstaller (sys._MEIPASS; ver main.spec). None se não achar - o
    chamador apenas pula o ícone.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        candidates.append(base_dir / filename)
        candidates.append(Path(sys.executable).parent / filename)
    candidates.append(Path(__file__).parent / filename)
    for c in candidates:
        if c.exists():
            return str(c)
    return None


ICON_PATH = _resolve_icon_path('icone.ico')
ICON_PNG_PATH = _resolve_icon_path('icone_vinil.png')


# ============================================================================
# TIPO DO LINK COLADO
# ============================================================================
def tipo_do_link(url: str) -> Optional[str]:
    """
    'video', 'channel', 'playlist' ou None (não parece link do YouTube).

    watch?v= / youtu.be / shorts  -> vídeo
    /@nome, /channel/, /c/, /user/ -> canal
    list= (sem watch?v=)           -> playlist
    watch?v=...&list=...           -> vídeo (o vídeo aberto dentro de uma playlist;
                                      no modo Playlist conta como playlist)
    """
    u = (url or '').strip().lower()
    if not u:
        return None
    if not any(d in u for d in ('youtube.com', 'youtu.be', 'youtube-nocookie.com')):
        return None
    if 'youtu.be/' in u or 'watch?v=' in u or '/shorts/' in u or '/live/' in u:
        return 'video'
    if 'list=' in u:
        return 'playlist'
    if any(m in u for m in ('/@', '/channel/', '/c/', '/user/')):
        return 'channel'
    return None


def link_serve_para_o_modo(url: str, modo: str) -> bool:
    """O link colado combina com o modo escolhido? (link desconhecido: deixa passar)"""
    tipo = tipo_do_link(url)
    if tipo is None:
        return True
    if modo == 'playlist':
        return 'list=' in (url or '').lower()
    return tipo == modo


# ============================================================================
# MENU DO BOTÃO DIREITO EM TODOS OS CAMPOS DE TEXTO
# ============================================================================
def _menu_de_contexto(evento):
    """
    Menu de contexto do campo clicado (o Tkinter não traz um pronto).
    Editável: Colar, Copiar, Selecionar tudo; com _menu_limpar=True também
    Limpar; só leitura (o log): Copiar, Selecionar tudo. Colar/Limpar geram
    <<Colado>>.
    """
    w = evento.widget
    try:
        w.focus_set()
    except Exception:
        pass
    eh_texto = isinstance(w, tk.Text)
    try:
        estado = str(w.cget('state'))
    except Exception:
        estado = 'normal'
    so_leitura = estado in ('disabled', 'readonly')

    def tem_selecao():
        try:
            if eh_texto:
                return bool(w.tag_ranges('sel'))
            return bool(w.selection_present())
        except Exception:
            return False

    def copiar():
        try:
            if eh_texto:
                txt = w.get('sel.first', 'sel.last') if w.tag_ranges('sel') else ''
            else:
                txt = w.selection_get() if w.selection_present() else ''
            if txt:
                w.clipboard_clear()
                w.clipboard_append(txt)
        except Exception:
            pass

    def colar():
        try:
            txt = w.clipboard_get()
        except Exception:
            return
        try:
            if eh_texto:
                if w.tag_ranges('sel'):
                    w.delete('sel.first', 'sel.last')
                w.insert('insert', txt)
            else:
                if w.selection_present():
                    w.delete('sel.first', 'sel.last')
                w.insert('insert', txt)
            w.event_generate('<<Colado>>')
        except Exception:
            pass

    def selecionar_tudo():
        try:
            if eh_texto:
                w.tag_add('sel', '1.0', 'end-1c')
            else:
                w.selection_range(0, 'end')
                w.icursor('end')
        except Exception:
            pass

    def limpar():
        try:
            if eh_texto:
                w.delete('1.0', 'end')
            else:
                w.delete(0, 'end')
            w.event_generate('<<Colado>>')
        except Exception:
            pass

    menu = tk.Menu(w, tearoff=0)
    if not so_leitura:
        menu.add_command(label="Colar", command=colar)
    menu.add_command(label="Copiar", command=copiar,
                     state='normal' if tem_selecao() else 'disabled')
    menu.add_command(label="Selecionar tudo", command=selecionar_tudo)
    if not so_leitura and getattr(w, '_menu_limpar', False):
        menu.add_separator()
        menu.add_command(label="Limpar", command=limpar)
    w._menu_aberto = menu            # usado pelos testes
    try:
        menu.tk_popup(evento.x_root, evento.y_root)
    finally:
        try:
            menu.grab_release()
        except Exception:
            pass
    return 'break'


def instalar_menu_contexto(root):
    """Liga o menu do botão direito (via bind_class) em todos os campos de texto, uma vez só."""
    botoes = ['<Button-3>']
    if sys.platform == 'darwin':
        botoes += ['<Button-2>', '<Control-Button-1>']
    for classe in ('Entry', 'TEntry', 'Text', 'TCombobox', 'Spinbox', 'TSpinbox'):
        for b in botoes:
            root.bind_class(classe, b, _menu_de_contexto, add='+')


# ============================================================================
# BOTÃO DE AJUDA (?) REUTILIZÁVEL
# ============================================================================
def make_help_button(parent, title, text, link_url=None, link_label=None,
                      button_bg='#E2E8F0', footer_note=None):
    """
    Botão "?" que abre, junto dele, um popup com `title` e `text` (aceita
    \\n). Opcionais: link_url/link_label (link que abre no navegador) e
    footer_note (linha em itálico no fim). Devolve o botão, pra posicionar
    com .pack()/.grid().
    """
    btn = tk.Button(parent, text="?", font=('Segoe UI', 8, 'bold'),
                     bg=button_bg, fg=Cores.COLOR_ACCENT, bd=0, width=2,
                     cursor='hand2', relief='flat',
                     activebackground='#C7D2FE', activeforeground='#3730A3')

    def show_popup():
        popup = tk.Toplevel(btn)
        popup.title(title)
        popup.configure(bg='#FFFFFF')
        popup.resizable(False, False)
        try:
            popup.transient(btn.winfo_toplevel())
        except Exception:
            pass

        # Posiciona o popup pertinho de onde o usuário clicou
        x = btn.winfo_rootx() + 10
        y = btn.winfo_rooty() + btn.winfo_height() + 6
        popup.geometry(f"+{x}+{y}")

        container = tk.Frame(popup, bg='#FFFFFF', padx=18, pady=16,
                              highlightthickness=1, highlightbackground='#E2E8F0')
        container.pack()

        tk.Label(container, text=title, font=('Segoe UI', 11, 'bold'),
                 bg='#FFFFFF', fg='#1E293B', justify='left',
                 wraplength=320).pack(anchor='w', pady=(0, 8))
        tk.Label(container, text=text, font=('Segoe UI', 9),
                 bg='#FFFFFF', fg='#334155', justify='left',
                 wraplength=320).pack(anchor='w')

        if link_url:
            def open_link():
                webbrowser.open(link_url)
            link_btn = tk.Button(container, text=(link_label or link_url),
                                  font=('Segoe UI', 9, 'underline'),
                                  bg=Cores.COLOR_CARD, fg=Cores.COLOR_ACCENT, bd=0, cursor='hand2',
                                  activeforeground='#3730A3', command=open_link)
            link_btn.pack(anchor='w', pady=(10, 0))

        if footer_note:
            tk.Label(container, text=footer_note, font=('Segoe UI', 8, 'italic'),
                     bg='#FFFFFF', fg='#94A3B8', justify='left',
                     wraplength=320).pack(anchor='w', pady=(12, 0))

        close_btn = tk.Button(container, text="Fechar", command=popup.destroy,
                               bg='#F1F5F9', fg='#1E293B', bd=0, font=('Segoe UI', 9),
                               cursor='hand2', padx=12, pady=4, relief='flat')
        close_btn.pack(anchor='e', pady=(14, 0))

        popup.focus_set()
        popup.bind('<Escape>', lambda e: popup.destroy())

    btn.config(command=show_popup)
    return btn
