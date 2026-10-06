# DiscoFácil — plano combinado (01/10/2026)

Anotado a partir da conversa com o usuário. Andamento:

- **12.2 (feito):** itens 6, 7 e 10.1/10.4 - interface, log na tela e arquivo de log por rodada; testes dentro do projeto.
- **12.3 (feito):** item 4 - nova janela "Precisam de você".
- **12.4 (feito):** itens 5 (nomes de faixa de playlist, álbum da descrição) e 9 (número do artista).
- **12.5 (feito):** itens 1, 2 e 3 - identificação × encaixe, outras edições, MusicBrainz, sem a passada repetida.
- **12.6 (feito):** item 5 - baixar o próximo durante o corte.
- **12.7 (feito):** item 8 - Groq como sugestão.
- **12.8 (feito):** organizar o código (item 5, último tópico) - main.py dividido em módulos, código morto e multi-fonte antigo (Selenium) fora, documentação (ARQUITETURA.md).
- **12.9 (feito):** melhorias pequenas pedidas depois da 12.8 (ver MUDANCAS.md) e o Groq com o modelo novo.
- **12.10 (feito):** disco sem durações em lugar nenhum - nomes pela ordem, juntando pausas curtas (palpite marcado "a conferir").
- **12.11 (feito):** Ray Charles "Forever": título comparado nos dois sentidos, ano de coletânea, pendência "talvez outro disco", queda de volume que não vira faixa curta.
- **12.12 (feito):** edição reconhecida pelo áudio quando a escolhida não encaixa (Ray Charles "Forever": a certa estava na busca).
- **12.13 (feito):** empate de durações casa na ordem do disco (o "Forever" tem duas faixas de 3:42).
- **12.14 (feito):** durações do Deezer pra disco sem nenhuma (Neco); "processar mesmo assim" estima até 2 fronteiras emendadas, marcadas "conferir" (Tocando Victor Assis Brasil); consenso sem pedaço < 60s; compacto × coletânea com o mesmo nome ("Can't Play A Playgirl").
- **12.15 (feito):** "processar mesmo assim" estima até metade das trocas emendadas (no máximo 2 seguidas) e não corta mais em "Track N" disco que tem durações (Ray Charles "Ingredients"); durações também do iTunes e de edição com faixas bônus (Os Cobras).
- **12.16 (feito):** regra única de "mesmo disco" em toda troca de edição (Vê, Os Cobras); tempos nos comentários do vídeo; botão "Informar tempos"; lojas mostram o título que não bateu; revisão independente dos pontos de troca e de nomes.
- **12.17 (feito):** tela "Conferir cortes" pra ouvir o disco e acertar os cortes: botão "✂ Editar" em "Precisam de você" (áudio guardado em `.audios_pasta_pendencia`, cortes exatos) e "✂ Editar disco" na tela principal (corrige disco já cortado, guarda os arquivos de antes).
- **12.18 (feito):** o editor tem a última palavra (os nomes acompanham os cortes); guias amarelas (Discogs) e roxas (o som muda); lista de nomes candidatos e "Colar nomes"; disco sem Discogs confirmado não usa o palpite (título do vídeo, capítulos); arquivo de correções do editor (`logs/correcoes_do_editor.txt`) pra ajustar os cortes automáticos; medidas guardadas.
- **Próximo:** analisar o arquivo de correções a cada ~2 semanas (lembrete marcado) e ajustar os cortes; quando estiver bom, desligar a gravação.

## 1. Duas notas em vez de uma "confiança"

- **Identificação** ("é este o álbum?"): título do álbum, títulos das faixas, nº de faixas
  e duração total.
  - Duração total conta como coincidente se estiver dentro de **±5%** da duração do áudio.
  - Se a fonte **não tem durações** (ex.: Os Boêmios), isso é "sem informação", não falha:
    a identificação fica pelos títulos.
  - Identificação baixa → "Precisam de você" (como hoje).
- **Encaixe** ("as durações deste cadastro servem pra cortar este áudio?"): medido
  **faixa a faixa** depois de detectar os silêncios — em quantas faixas a duração aponta
  pra um silêncio real a poucos segundos. Total que bate não basta (Nico Assumpção 1981:
  total a 1,4%, mas a ordem das faixas era outra).

## 2. Identificação alta + encaixe ruim — ordem de tentativas

1. **Outras edições do mesmo álbum no Discogs** — já ficam em memória da busca (até 20, com
   tracklist e durações); não custa consulta nova.
2. **Edições do MusicBrainz** (mesmo nº de faixas, títulos parecidos).
3. Fica com a fonte de **melhor encaixe**. Se nenhuma passar:
4. **Corta pelos silêncios e usa o Discogs só pros nomes**, casando cada faixa pela duração
   (mesmo fora de ordem).
5. Se o corte pelos silêncios achar **nº de faixas diferente** do Discogs (sinal de duas
   músicas emendadas) → **"Precisam de você"**. Nada sai com nomes trocados nem duas
   músicas num arquivo.

- Guardar as edições candidatas junto com o item quando ele vai pra "Precisam de você",
  pra nova tentativa não precisar refazer a busca.

## 3. Correções já identificadas

- **Conta errada no corte pelos silêncios** (Nico Assumpção 1981): comparou 10 cortes com
  9 esperados ANTES de descartar um pedaço de 0,5s no fim — deu "Track 1, Track 2…" mesmo
  com 10 faixas = 10 do Discogs.
- MusicBrainz também como **desempate** na escolha de edição.
- **Segunda passada inútil**: quando o disco é rejeitado, "Usando detecção de silêncio com
  nomes do Discogs" refaz a mesma análise com a mesma entrada (mesmo áudio, mesmas faixas e
  durações, mesmas regras) — resultado sempre idêntico, e se acertasse gravaria artista/álbum
  como "Unknown". Sai; o lugar dela vira o passo "corta pelos silêncios e casa os nomes pela
  duração" (item 2.4). A tentativa pelos capítulos do YouTube, que vem antes, fica.

## 4. Janela "Precisam de você" (aceito pelo usuário)

Hoje cada clique (marcar, desmarcar, remover) apaga e redesenha a lista inteira e grava o
arquivo; remover pede confirmação um por um. Trocar por:

- **Lista em tabela**: colunas título, motivo, confiança, data.
- **Seleção normal**: clique, Ctrl+clique, Shift+clique, "Selecionar tudo",
  "Selecionar todos com este motivo".
- **Filtro por motivo + busca** no topo (cobre o agrupamento por motivo).
- **Botões que agem nos selecionados**: Enfileirar, Remover (uma confirmação só),
  Buscar outra versão.
- **"Abrir no YouTube" continua individual, como hoje**: uma coluna "▶ YouTube" em cada
  linha — clicar nela abre o vídeo daquela linha sem mexer na seleção (duplo clique na
  linha também abre).
- Resposta instantânea: só as linhas afetadas mudam; grava o arquivo uma vez por ação.
- "Remover" manda pra uma lista de **descartados** recuperável, em vez de apagar de vez.

## 5. Outras melhorias aceitas

- **Nomes das faixas de playlist**: o casamento de títulos não entende o nome do artista na
  frente ("SIMONE PARA LENNON & McCARTNEY"), títulos bilíngues com "=" ("Para Lennon Y
  McCartney = Para Lennon E McCartney") nem "&" no lugar de "E" — 7 das 10 faixas da Simone
  ficaram com o nome do vídeo. Também tirar sufixos como "(Audio)" do nome do arquivo
  ("Will You Still Love Me Tomorrow (Audio)").
- **Título sem nome de álbum** (ex.: "Wes Montgomery (Jazz)"): tirar o álbum da descrição
  do vídeo antes de buscar no Discogs.
- **Baixar só o próximo álbum** (na pasta .temp) enquanto corta o atual.
- **Organizar o main.py** (10+ mil linhas, estratégias antigas sobrepostas): feito na 12.8
  (ver ARQUITETURA.md). As 5 estratégias de corte ficaram, só organizadas e documentadas.

## 6. Interface — incômodos do usuário

- **Menu do botão direito em nenhum lugar**: o Tkinter não traz isso pronto. Criar o menu
  (Recortar, Copiar, Colar, Selecionar tudo) em todos os campos de texto: URL, lista de
  playlists, Configurações, busca; no log, Copiar e Selecionar tudo.
- **Botões escondidos ao iniciar**: hoje nenhum modo vem escolhido, e o campo de URL e a
  linha de botões abaixo dele só aparecem depois de clicar num modo. Abrir já com o último
  modo usado (ou "Vídeo Único" na primeira vez); botões gerais (Copiar Log, Abrir Pasta,
  Retomar fila, Precisam de você) sempre visíveis, independentes do modo.
- **Mesma caixa de texto pra Vídeo Único e Canal**: hoje é literalmente o mesmo campo, só
  muda o rótulo — trocar de modo leva junto o que estava escrito. Separar: cada modo com seu
  campo. E reconhecer o tipo do link colado (watch?v= / youtu.be = vídeo; /@nome ou /channel/
  = canal; list= = playlist) e avisar se não bater com o modo escolhido.
- **URL / lista de playlists não são apagadas depois de enfileirar**: limpar o campo assim
  que o item entra na fila (o link fica registrado no log). Na lista de playlists, tirar só
  as que entraram; as que deram erro ficam, com aviso.

## 7. Mais itens de interface (aceitos)

- **Pergunta ao abrir, se houver fila**: "Há N álbuns na fila. [Retomar agora] [Depois]".
  Se o Deno ainda estiver instalando, a fila espera sozinha (como já faz). O botão
  "Retomar fila" continua sempre visível.
- **Menu do botão direito sem "Recortar"**: Colar, Copiar, Selecionar tudo; nos campos de
  URL também "Limpar".
- **Rolagem do log**: hoje cada linha força o fim e redesenha a janela. Passa a: só acompanhar
  o fim se o usuário já estiver no fim; se ele rolar pra cima, fica parado e aparece
  "↓ N linhas novas" (clicar ou rolar até o fim volta a acompanhar); linhas entram em
  lotes (~10x por segundo) em vez de uma a uma.
- **Configurações no log**: no início e a cada vez que salvar — pasta de saída, bitrate
  mínimo, confiança mínima, navegador dos cookies, versão. Chaves (Discogs, Groq) NUNCA
  aparecem: só "configurado".

## 8. Groq (IA) — usar de verdade, sempre só como sugestão

Hoje só entra em dois casos raros (título ilegível = "Unknown"; descrição com tracklist que os
padrões não leem, e só quando o Discogs não achou o álbum). Duas funções que o usariam
(validar artista, comparar títulos entre fontes) nunca são chamadas. O log diz "Groq (apoio
técnico de corte)" — enganoso, ele não participa do corte.

- Ler título + descrição pra achar o álbum quando o título não traz (Wes Montgomery; item 3).
- Reforço no casamento de nomes de faixa difíceis ("=", "&"/"E", artista na frente) quando a
  comparação normal falhar (Simone).
- Ler a descrição mesmo com Discogs achado: pode trazer a ordem das faixas daquele vídeo
  (ajuda no "encaixe").
- Regras: não ouve áudio (não corta); pode inventar → nunca decide sozinho, Discogs e
  durações confirmam; plano gratuito tem limite. Corrigir o texto do log.

## 9. Número depois do nome do artista ("Simone (3)", "Jay White (3)", "Marina Sena (2)")

É o desempate do Discogs pra artistas com o mesmo nome (existem várias "Simone"). Tirar o
" (N)" do fim do nome nas PASTAS e nas TAGS; manter o identificador completo só por dentro
(busca e master_id/release_id). Também tirar o "*" que o Discogs põe em variações de nome
("Marina*", "Paulo Braga*"). Pastas já criadas com o número: não mexer sem o usuário pedir.

## 10. Método de trabalho (combinado com o usuário)

1. **Primeiro, testes dentro do projeto** (pasta testes/): ajustar caminhos e deixar todos
   rodando. Cada mudança é conferida contra todos os casos já resolvidos (Gloria, Simone,
   Frank, Nico…). Cada correção nova ganha um teste novo.
2. **Etapas pequenas, uma versão por etapa:**
   - 12.2: interface (menu do mouse, botões visíveis, rolagem do log, configurações no log,
     pergunta ao abrir, campos separados, limpar URL após enfileirar);
   - 12.3: nova janela "Precisam de você";
   - 12.4: nomes de faixas de playlist, número do artista, álbum lido da descrição;
   - 12.5: identificação × encaixe, outras edições, MusicBrainz, retirada da passada repetida;
   - depois: baixar o próximo durante o corte; Groq.
3. **Claude testa cada versão antes de entregar** (testes automáticos + simulações + áudio
   real disponível + abrir a janela). Do ambiente de trabalho não dá pra baixar do YouTube:
   o teste com discos reais fica com o usuário, que manda o log se algo der errado.
4. **Log preparado pra análise do Claude**: além do log na tela, um arquivo de log por
   rodada (pasta de saída, subpasta de logs) com tudo que importa pra diagnóstico — versão,
   configurações (sem chaves), cada disco com fonte escolhida e notas (identificação/encaixe),
   motivo de cada rejeição e o erro com o local (arquivo:linha). Formato fácil de ler e de
   procurar, pra o usuário só anexar o arquivo.
5. Ao entregar cada versão: número da versão novo, MUDANCAS.md atualizado, tutorial só se a
   interface mudar.
