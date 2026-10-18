# Instruções para o Claude (projeto DiscoFácil)

Este arquivo é lido automaticamente pelo Claude quando a conversa é ligada a este repositório. Ele leva o que foi combinado com o dono do projeto (Glauco) nas conversas anteriores.

## O projeto

- **DiscoFácil**: transforma vídeos de disco inteiro do YouTube em faixas MP3 com tags (nome, número, artista, álbum, ano, capa). Python 3.12 + Tkinter, **só Windows 64 bits** (o .exe é gerado pelo GitHub Actions).
- Repositório: **https://github.com/Glauco-BP/DiscoFacil** (o usuário antigo `glaucoaiexcorrea-glitch` foi trocado por `Glauco-BP` em 06/10/2026; os links antigos redirecionam). O link fica em `versao.py` (`APP_URL`), e o programa o manda pro Discogs e o MusicBrainz como identificação.
- Versão atual: ver `versao.py` (12.22 quando este arquivo foi atualizado). Por dentro: `ARQUITETURA.md`. Histórico: `MUDANCAS.md`. Planos: `PLANO.md`. Testes: `testes/LEIA.md`.

## Como o Glauco quer trabalhar

- **Responder em português, de forma concisa.**
- **Não mudar nada fora do que foi combinado sem perguntar antes.**
- "Apenas responda", "apenas relate", "apenas fale": só texto, **sem mexer em código**.
- **Regra de ouro do programa:** nunca gravar disco errado nem nome errado. Na dúvida, o disco vai pra "Precisam de você" ou sai com "Track N". O objetivo é ser o mais automático possível **na rodada automática**; o ✂ Editar é a última palavra do usuário.
- A cada versão:
  - número novo em `versao.py`;
  - seção nova no `MUDANCAS.md`;
  - tutorial refeito se a tela mudou (`python testes/gerar_tutorial.py`, que também atualiza as figuras do README em `docs/telas`);
  - um teste para cada correção;
  - **todos os testes** rodando antes de entregar;
  - abrir a janela para conferir a tela;
  - atualizar no `README.md` o link do tutorial (o nome do PDF tem a versão) e o `NOTAS_DA_VERSAO.md`.
- **Segurança:**
  - chaves (Discogs, Groq, YouTube) nunca aparecem em log, tela, arquivo ou mensagem; nem pedaços delas;
  - testes nunca usam a internet nem os dados do usuário;
  - `config.json` nunca entra no repositório nem em zip;
  - não publicar o e-mail do Glauco.
- **Commits:** autor `Glauco <Glauco-BP@users.noreply.github.com>`. Pode ter a linha `Co-Authored-By: Claude ...`, mas **sem** a linha `Claude-Session:` com o link da conversa (pedido do Glauco).
- **Música com direitos autorais nunca entra no repositório** (as duas faixas reais de `testes/dados` ficam só no computador de quem desenvolve; sem elas, `teste_gloria_real` é pulado).

## Testes

- `python testes/rodar_todos.py`: todos, cerca de 15 min. Rode em segundo plano (`nohup ... &`) e espere o fim, porque a saída só aparece no final. Precisa de `ffmpeg` e, no Linux, de `xvfb-run` para as telas.
- `python testes/conferir_cortes.py`: cerca de 1 min. Corta 10 discos de teste e compara cada corte, na posição exata, com `testes/referencia_cortes.json` (os cortes da 12.8, iguais até a 12.22). **Rode depois de qualquer ajuste nos cortes.** Se um disco mudou de propósito, grave a referência nova com `--gravar` e explique no `MUDANCAS.md`.

## Publicar uma versão

1. Commit e push em `main`.
2. O Claude **não consegue** criar Release nem tag a partir da conversa (o GitHub recusa).
3. O Glauco faz no site: **Releases → Draft a new release → tag `v12.19` (Create new tag) → título `DiscoFácil 12.19` → texto do `NOTAS_DA_VERSAO.md` → Publish**.
4. O GitHub Actions (`.github/workflows/release.yml`) gera `DiscoFacil_<versão>_Windows_64bits.zip` (o .exe com o FFmpeg, o tutorial, o README e as licenças) e anexa à versão em uns 5 min.

## O trabalho em andamento: refinar o corte automático com as correções do editor

**Objetivo:** cortar mais certo sozinho, aprendendo com o que o Glauco corrige no ✂ Editar.

- **Como funciona.** Desde a 12.18, cada vez que o Glauco salva no ✂ Editar, o programa anota uma linha (JSON) em `<pasta dos discos>\logs\correcoes_do_editor.txt`:
  - o disco, a origem (pendência ou disco já cortado) e se o Discogs estava confirmado;
  - cada corte sugerido, com o que aconteceu com ele: `mantido` (até 0,5 s), `movido` (com `diferenca_s`), `apagado` ou `novo`, e o tipo (`silencio` / `estimado` / `usuario`);
  - o que havia perto de cada corte: `pausa_perto_s` e `pausa_dura_s`, `som_perto_s` (a guia roxa), `discogs_perto_s` (a guia amarela);
  - os nomes trocados (desde a 12.19, comparados com o que aparecia ao salvar), `fonte_dos_nomes` e `nomes_automaticos_mantidos`;
  - desde a 12.19, `medidas`: o arquivo em `logs\medidas_do_editor\` com o "desenho do volume" do disco (volume em dB a cada 0,05 s, silêncios, mudanças no som, cortes sugeridos e finais). É com ele que se testa um ajuste do corte sem os áudios (que são grandes demais pra mandar). Disco já cortado aberto no "✂ Editar disco" e salvo sem mudança também guarda as medidas (linha com `sem_mudanca`, fora do resumo).

  Ver `edicao_cortes.registro_de_correcoes` e `guardar_medidas_da_edicao`. O log de cada rodada mostra o resumo "📊 Editor: … X% dos cortes sugeridos ficaram onde estavam".
- **Ciclo** (a cada ~2 semanas, ou depois de ~30 a 50 edições):
  1. O Glauco manda o `correcoes_do_editor.txt` e a pasta `logs\medidas_do_editor` zipada (e, se quiser, o log da rodada).
  2. O Claude analisa **com números** (script, não estimativa):
     - % mantidos por tipo;
     - para que lado e quanto os `estimado` erram;
     - que pausas viram cortes apagados (respiração? aplauso?);
     - onde estavam os cortes novos (perto de roxo? de amarelo? de pausa curta?);
     - se a guia roxa acerta.
  3. Propõe ajustes (os limiares ficam em `ajustes.py`, a lógica em `corte_estrategias.py`/`corte_audio.py`). **Pergunta antes de mudar.**
  4. Valida: testes novos com os casos reais, `rodar_todos.py`, `conferir_cortes.py`.
  5. Entrega uma versão nova.
- **O programa NÃO aprende sozinho**, e isso foi decidido: os ajustes passam por análise, testes e versão.
- **Lembretes:**
  - Combinado com o Glauco: lembrar de pedir o arquivo a cada ~2 semanas, **nesta** conversa nova (agendar com `send_later`).
  - O lembrete antigo (`trig_01HzhsxHYvzuZBvQR2rBoC7B`, da conversa anterior) foi apagado em 12/10/2026. O atual é `trig_018dnWzGDmA4YJtJhBra37mM`, para 19/10/2026 às 19h (Brasília), nesta conversa. Cada lembrete é de uma vez só: quando chegar, pedir o arquivo e marcar o próximo para 14 dias depois, às 19h.
- **Fim do projeto de refinamento:** quando o resultado estiver bom, combinar com o Glauco, desligar a gravação (`settings.gravar_correcoes_editor` passa a vir desligado) e parar os lembretes.

## Pendências conhecidas (decididas ou de baixa prioridade)

- Disco sem durações em lugar nenhum, com o nº de pedaços batendo: sai com os nomes pela ordem, marcados "conferir". Decisão do Glauco (12.10).
- Baixa prioridade: o casamento aproximado de títulos no modo playlist e o casamento de títulos das lojas (Deezer/iTunes) um pouco frouxo.
- A tabela do Tk não deixa colorir uma coluna só (por isso a guia amarela fica no desenho).
