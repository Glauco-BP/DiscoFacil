# Testes do DiscoFácil

Rodar todos (de qualquer pasta):

    python testes/rodar_todos.py          # resumo no fim; mostra a saída só de quem falhar
    python testes/rodar_todos.py -v       # mostra tudo
    python testes/rodar_todos.py suite e2e   # só alguns

Precisa de ffmpeg/ffprobe no PATH e das bibliotecas do requirements.txt. Os testes de
janela precisam de tela; sem tela (servidor), se reexecutam sozinhos dentro do `xvfb-run`.
Arquivos de trabalho vão para `testes/.tmp` (pode apagar; são refeitos). Os testes rodam com a
pasta atual em `testes/.tmp/pasta_atual`, pra nenhum caminho relativo escapar.

Variáveis úteis:
- `DF_PROJ=<pasta>` roda os testes contra outra cópia do programa (ex.: a versão anterior).
- `DF_FOTOS=<pasta>` guarda fotos da janela tiradas pelos testes de interface.

| Arquivo | O que confere |
|---|---|
| comum.py | caminhos (pasta do programa, testes/.tmp), arquivos de apoio, `t()`/`fim()` |
| rodar_todos.py | roda todos, cada um num processo |
| janela.py | abre a janela de verdade com config temporária, sem rede, e tira fotos |
| sint.py / album_lp.py | geradores de áudio sintético |
| suite.py | 20 testes de corte (silêncio, Gloria, vinil, intro suave, acorde final, .webm…) |
| teste_falta.py | recuo do corte quando a faixa seguinte fica curta + silêncio longo (Gloria 7→8); silêncio digital com 1 amostra perdida (12.2) |
| teste_gloria_real.py | o mesmo, com o áudio REAL das faixas 7 e 8 (pasta dados/) |
| teste_semdiscogs.py | discos sem Discogs / LP com chiado / jazz com faixas longas |
| teste_gloria.py | ajuste de durações pelo MusicBrainz (formatos "M:SS") |
| e2e.py | ponta a ponta: discos limpo, vinil e tipo Gloria; compara com `referencia_e2e.json` (12.1) |
| teste_pc.py / teste_corrompido.py | playlist num computador sem ffmpeg instalado |
| teste_deno.py | instalação do Deno (certificado, sem internet, falhas passageiras) |
| teste_recarregar.py | contorno do "The page needs to be reloaded", trava de qualidade, idade, Frank |
| teste_interface.py | 12.2: janela principal (modo, campos, avisos, limpeza, menu do mouse, rolagem do log, pergunta da fila) |
| teste_registro.py | 12.2: arquivo de log por rodada (etiquetas, chaves mascaradas, erro com local) |
| teste_pendentes.py | 12.3: janela "Precisam de você" (tabela, seleção, filtro, busca, lote, Descartados, 3000 itens) |
| teste_nomes.py | 12.4: nomes de faixa de playlist (Simone, Aja), número do artista, álbum lido da descrição |
| teste_encaixe.py | 12.5: identificação × encaixe, outras edições, MusicBrainz, silêncios + nomes pela duração, Nico, candidatas; e os discos do e2e pelo caminho novo |
| teste_antecipado.py | 12.6: baixar o próximo álbum durante o corte (com o trabalhador da fila de verdade) |
| teste_groq.py | 12.7: Groq só como sugestão (álbum, nome de faixa, ordem da descrição), limite do plano gratuito |
| teste_editor.py | 12.17: tela "Conferir cortes" (com um tocador falso no lugar da placa de som) - marcas iniciais, botões e teclas, avisos, salvar em tempos exatos, corte exato no processamento, áudio guardado, regravar a pasta de um disco já cortado, tocador com um `sounddevice` falso, botões "✂ Editar" e "✂ Editar disco"; 12.18: o editor é a última palavra (menos faixas que o Discogs), nomes que acompanham os cortes, guias amarelas e roxas, mudanças no som sintéticas, lista de nomes e Colar nomes, disco sem Discogs confirmado (Ruth Brown/Zen Garden) até a pasta gravada, arquivo de correções, medidas guardadas e os achados da revisão |
| teste_casos_reais.py | 12.16: casos reais dos logs com os números de verdade - Vê e Os Cobras (nunca trocar por outro disco), regra de mesmo disco, lojas (título sem par), tempos de comentário, tempos informados, botão Informar tempos, achados da revisão independente |
| teste_emendas.py | 12.15: Ray Charles "Ingredients" (4 emendas estimadas; 3 seguidas = pendente, sem "Track N"), Os Cobras (edição com bônus no Deezer, iTunes); 12.14: Neco (durações do Deezer, cliente com respostas simuladas), Tocando Victor Assis Brasil (emenda estimada só em "processar mesmo assim", marcada "conferir"), consenso sem pedaço < 60s, compacto × coletânea ("Can't Play A Playgirl") |
| teste_melhorias.py | 12.12: edição reconhecida pelo áudio; 12.11: Ray Charles "Forever" (título nos dois sentidos, ano de coletânea, "talvez outro disco", pausa de 30s não vira faixa); 12.10: disco sem durações (Luiz Loy, 14 pedaços → 12 músicas); 12.9: Corrigir busca, limite do Discogs de volta à fila, hora na descrição, medidas uma vez por álbum, tags num lugar só, config antigo, bitrate, cabeçalho |
| teste_caminho_simples.py | 12.8: pendência "não encontrado" (Discogs → capítulos → descrição → MusicBrainz → silêncios), sem Selenium, pistas do vídeo, capa embutida, tags, pasta, playlist e fila |
| falso_discogs.py | Discogs falso no formato da API + config falsa que se comporta como a real (auxiliar) |
| gerar_tutorial.py | gera o tutorial em PDF com fotos da janela de verdade (não é teste) |

`referencia_e2e.json`: cortes do ponta a ponta gravados na 12.1. Se uma mudança no corte
for intencional, regrave com `python testes/e2e.py --gravar` e explique no MUDANCAS.md.
