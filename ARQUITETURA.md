# DiscoFácil — mapa do código

Para quem vai mexer no programa. O histórico de cada decisão está em `MUDANCAS.md`;
os testes, em `testes/LEIA.md`.

## O caminho de um álbum

```
Enfileirar (janela_principal / fila_trabalho)
  └─ FilaUnica (fila_unica.py, gravada em disco)
       └─ trabalhador único (fila_trabalho._trabalhador_da_fila)
            ├─ disco único / canal → processo_album.process_single_video
            ├─ playlist            → processo_playlist.process_playlist
            └─ pendência           → _process_pending_video_item / _process_pending_playlist_item

process_single_video
  1. yt-dlp: título, descrição, capítulos, duração          (downloader.py)
  2. artista/álbum/ano do título (descrição, Groq se faltar) (identificacao_titulo.py, nomes.py, groq_ajuda.py)
  3. Discogs: busca, pontua as edições, nota de identificação (catalogo.py, pontuacao.py)
       nota baixa / não achou / limite de pedidos → "Precisam de você" (pending_queue.py)
       já no acervo → pula                                   (acervo_index.py)
  4. baixa o áudio (ou usa o antecipado)                     (saida.py, pre_download.py)
  5. afina durações pelo MusicBrainz                          (processo_album._refine_durations_with_musicbrainz)
     disco sem NENHUMA duração: pega as do Deezer ou do iTunes (nomes ficam os do
     Discogs; todos os títulos casados - edição com bônus serve -, soma batendo com o áudio)
                                                              (processo_album._duracoes_de_fora, catalogo.deezer/itunes)
  6. corta, nesta ordem:
       capítulos + nomes do Discogs
       → a edição que ENCAIXA nos silêncios                   (escolha_edicao.py, encaixe.py)
       → capítulos sozinhos
       → só silêncios, nomes casados pela duração
       → outra edição da busca com o título exato do vídeo, reconhecida pelo
         áudio (cada pedaço casado pela duração; `_reidentificar_pelo_audio`)
     sem durações em lugar nenhum, ou o corte falhou → os tempos de um comentário do
       vídeo, se for a lista DESTE disco (processo_album._tempos_dos_comentarios,
       corte nas posições: corte_estrategias.cut_at_positions)
     falhou → "Precisam de você" com o motivo e as edições candidatas
       (o áudio fica em .audios_pasta_pendencia; "✂ Editar" abre a tela "Conferir cortes" e
       o que você salvar volta como tempos #exato: cut_at_positions(exato=True), sem ajuste;
       sem Discogs confirmado, o item vai com 'editor_sem_discogs' e o artista/álbum da tela;
       se os cortes do editor não servem, nenhum outro corte é tentado)
     "processar mesmo assim": até metade das fronteiras sem silêncio (no máximo 2
     seguidas, músicas emendadas) vão pela duração, marcadas "conferir"
     (corte_estrategias._estimar_fronteiras); só depois o consenso, e "Track N"
     só para disco SEM durações (nenhum pedaço < 60s com o nº de músicas conhecido)
  7. MP3 por faixa, tags, IDs do Discogs, capa              (corte_album.py, saida.py, metadata_manager.py)
```

Pendência com **⏱ Informar tempos** (lista colada pelo usuário, `tempos_usuario`): o
corte é feito nesses tempos antes de tudo (`processo_album._faixas_dos_tempos`).

Toda troca de edição depois da escolha (reavaliação pós-corte, encaixe, MusicBrainz,
edição pelo áudio) passa pela regra única `pontuacao.mesmo_disco`: outro disco nunca entra.

Pendência "não encontrado" que o usuário manda baixar (`_resolver_sem_discogs`):
Discogs de novo (qualquer nota) → capítulos → tracklist com tempos na descrição →
MusicBrainz → só silêncios ("Track N"). O mesmo caminho vale quando o usuário usa
**Corrigir busca** (artista/álbum digitados; item marcado `busca_corrigida`).

Disco SEM durações em lugar nenhum (nem Discogs, nem MusicBrainz, nem descrição):
corta pelos silêncios e, se sobrarem poucos pedaços curtos (pausas dentro da música),
junta-os pela fronteira mais fraca até dar o nº de músicas e nomeia pela ordem
(`encaixe.juntar_pedacos_curtos`, `escolha_edicao._nomes_por_ordem_sem_duracoes`).
É palpite: log, arquivo da rodada e tag `TXXX:DISCOFACIL_NOTA` dizem "conferir".

Pendência "Discogs não respondeu" (limite de pedidos) volta sozinha pra fila como
`nova_tentativa` depois de 10 min, até 3 vezes por abertura
(`fila_trabalho._tentar_de_novo_limite_discogs`).

Medidas do áudio que não dependem das faixas (decodificação, envelope, duração,
silêncios do disco) são feitas uma vez por arquivo e reaproveitadas por todas as
tentativas de corte do álbum (`corte_audio.medidas_do_arquivo`).

## Módulos

| Arquivo | O que faz |
|---|---|
| `main.py` | Ponto de entrada: prepara ffmpeg/yt-dlp e abre a janela. Reexporta nomes usados nos testes. |
| `versao.py` | Número da versão (um lugar só). |
| **Janela** | |
| `janela_principal.py` | Classe `FullTracksDownloaderGUI`: junta os mixins abaixo, cria as peças e desenha a janela. |
| `log_janela.py` | Log na tela (em lotes, seguro entre threads) e no arquivo da rodada. |
| `fila_trabalho.py` | Enfileirar, trabalhador único, pausa, painel da fila, linha de situação. |
| `janela_pendentes.py` | Janela "Precisam de você". |
| `janela_busca.py` | Janela "Buscar Playlists". |
| `janela_config.py` | Configurações. |
| `janela_editor.py` | Tela "Conferir cortes": desenho do disco, cursor, marcas, tabela das músicas, teclas. |
| `editor_acoes.py` | `EditorMixin`: abre a tela a partir de "Precisam de você" (✂ Editar; disco confirmado usa o Discogs, não confirmado usa o título e os capítulos/descrição/comentário do vídeo) ou de uma pasta já cortada (✂ Editar disco), faz o que o salvar pede e anota as correções. |
| `tocador.py` | Toca o disco a partir de um ponto (ffmpeg → `sounddevice`); sem a biblioteca, a tela funciona sem som. |
| `ui_util.py` | Paleta de cores (`Cores`), ícones, menu do botão direito, botão "?", tipo de link. |
| **Identificação** | |
| `identificacao_titulo.py` | Artista/álbum/ano do título (expressões regulares). |
| `nomes.py` | Limpeza e comparação de nomes (" (N)" do Discogs, sufixos de vídeo, álbum na descrição). |
| `catalogo.py` | Discogs, MusicBrainz, Deezer e iTunes (os dois só durações), com limites de pedidos, e as pistas do vídeo (`pistas_do_video`). |
| `pontuacao.py` | Pontuação das edições e nota de identificação (funções puras). |
| `groq_ajuda.py` | Groq: só sugestão, sempre confirmada por outra coisa. |
| **Processo** | |
| `processo_album.py` | Modo álbum (acima), pendências de vídeo e o caminho sem Discogs. |
| `processo_playlist.py` | Modo playlist: um vídeo por faixa, casando com a tracklist oficial. |
| `escolha_edicao.py` | Identificação × encaixe: qual edição serve pra cortar este áudio. |
| `encaixe.py` | Nota de encaixe faixa a faixa e casamento por duração (funções puras). |
| `pre_download.py` | Baixa o próximo álbum enquanto o atual é cortado. |
| **Corte** | |
| `corte_album.py` | `AlbumCutter`: detectar silêncios → decidir → cortar → tags. |
| `corte_estrategias.py` | `SmartCutter`: as 5 estratégias de corte, em ordem (ver o topo do arquivo). |
| `corte_audio.py` | Medições do áudio (silêncio, RMS, envelope, início de nota). |
| `ajustes.py` | `CutTuning`: todos os limiares do corte, cada um com o porquê. |
| `youtube_chapters_extractor.py` | Capítulos do vídeo como faixas. |
| **Disco e externos** | |
| `downloader.py` | yt-dlp: informações, listas, download com bitrate mínimo, cookies. |
| `dependencias.py` | yt-dlp atualizado e Deno instalados sozinhos. |
| `audio_util.py` | ffmpeg/ffprobe do programa, duração, bitrate, taxa do MP3. |
| `saida.py` | Nome da pasta, download com novas tentativas, capa (baixar e embutir). |
| `metadata_manager.py` | Todas as tags dos MP3 (mutagen, ID3 v2.3): `gravar_tags`, `embutir_capa`, IDs do Discogs. |
| `acervo_index.py` | Índice do que já está no disco (dedupe por master/release). |
| `fila_unica.py` | A fila de trabalho, persistente. |
| `pending_queue.py` | A lista "Precisam de você", persistente. |
| `edicao_cortes.py` | Áudio guardado das pendências (`.audios_pasta_pendencia`) e as medidas dele (`_medidas/<id>.npz`); a edição dos cortes (`Edicao`: marcas com as faixas que começam nelas, nomes que acompanham os cortes, guias do Discogs, mudanças no som, candidatos de nome, tempos `#exato`); ler/juntar/regravar a pasta de um disco já cortado; o arquivo de correções (`logs/correcoes_do_editor.txt`). |
| `registro.py` | Arquivo de log por rodada (chaves sempre mascaradas). |
| `config.py` | `config.json` (pasta de saída, chaves, ajustes); converte o formato antigo guardando `config.json.antigo`. |
| `util.py` | `sanitize`, `segundos_da_faixa`, `onde_quebrou`. |

## Onde mexer

| Quero mudar… | Arquivo |
|---|---|
| quando um álbum baixa sozinho ou vai pra "Precisam de você" | Configurações (confiança mínima); `pontuacao.avaliar_identificacao` |
| o que conta como "o mesmo disco" | `pontuacao.mesmo_disco` |
| como as edições do Discogs são pontuadas | `pontuacao.score_discogs_candidate` (título nos dois sentidos: `palavras_a_mais`; duração muito longe do vídeo = outro disco) |
| máximo de faixas de um candidato (box set) | `catalogo.limite_de_faixas` |
| busca no Discogs / MusicBrainz / Deezer / iTunes | `catalogo.py` |
| onde o corte cai, limiares de silêncio | `ajustes.py` (números) e `corte_estrategias.py` (lógica) |
| qual edição é usada pra cortar | `escolha_edicao.py`, `encaixe.py` |
| nome da pasta, capa | `saida.py` |
| tags dos MP3 | `metadata_manager.gravar_tags` (usado pelos dois modos) |
| modelo do Groq | `groq_ajuda.MODELOS` (troca sozinho quando um sai do ar) |
| qualidade mínima do áudio | `downloader.py` e Configurações |
| textos e botões da janela | `janela_*.py`, `fila_trabalho.py` |
| o que vai pro arquivo de log | `registro.py` e as chamadas `self._reg(...)` |
| a tela "Conferir cortes" (botões, cores, teclas) | `janela_editor.py`; as regras das marcas em `edicao_cortes.Edicao` |
| a sugestão roxa (mudança no som) | `edicao_cortes.medir_audio` / `mudancas_no_som` (`SOM_*`) |
| o que vai pro arquivo de correções | `edicao_cortes.registro_de_correcoes` |

## Regras que valem em todo o código

- **Chaves de API nunca aparecem** no log, na tela ou no arquivo (só "configurada"/"não configurada").
- **A interface só é tocada pela thread do Tk** (`root.after`); o trabalhador roda em outra thread.
- **Nome errado é pior que genérico**: sem confirmação pelo áudio, a faixa fica "Track N".
- **Um erro numa etapa nova nunca derruba o álbum**: registra o local (`onde_quebrou`) e segue pelo caminho antigo.
- **Testes não usam a rede nem os dados do usuário** (`python testes/rodar_todos.py`).
