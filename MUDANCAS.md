# FullTracksDownloader v11.0 — Changelog desta revisão

Resumo do que mudou em relação ao YouTube Album Ripper v10.9 original, organizado pelos itens discutidos.

## 1. master_id/release_id do Discogs (dedupe do acervo)

- **`metadata_manager.py`**: novas tags ID3 `TXXX:DISCOGS_MASTER_ID` e `TXXX:DISCOGS_RELEASE_ID`, gravadas em cada faixa. Novos métodos `add_discogs_ids()` (grava só esses dois campos) e `read_discogs_ids()` (lê de volta).
- **`acervo_index.py`** (novo arquivo): mantém `acervo_index.json` na raiz da pasta de saída (`master_id → pasta`). Se o arquivo estiver ausente, é reconstruído automaticamente varrendo os MP3s já baixados (lendo a tag acima). Sem sufixo no nome da pasta.
- Antes de baixar qualquer álbum, o programa consulta esse índice; se o `master_id` (ou `release_id`, quando o release não tem master vinculado no Discogs) já estiver lá, o álbum é pulado.

## 2. Discogs como única fonte de metadados

- `metadata_hunter_voting.py`: `discogs()` agora também retorna `master_id`, `release_id` e `confidence_pct` (0-100).
- `main.py`: o pipeline automático (`process_single_video`, e por extensão `process_channel`, que só chama esse) agora usa **só** o Discogs. Se encontrar com confiança boa, baixa e corta normalmente. Se não encontrar ou a confiança for baixa, o álbum vai para a fila de pendentes (ver item 3) e **não é baixado**.
- O mesmo vale para `process_playlists` (modo "playlist inteira = 1 álbum").
- O pipeline antigo multi-fonte (Last.fm, Apple Music, Painel "Música" do YouTube, YouTube Chapters/descrição, silêncio puro) **continua existindo**, mas só é acionado manualmente, quando você clica "Baixar" num item "não encontrado" na fila de pendentes (`_resolve_via_all_sources` / `_resolve_playlist_via_all_sources`).
- YouTube continua sendo usado como apoio técnico: pista de busca pro Discogs (título/tracklist dos chapters) e guia de corte.
- Removida a instanciação do `SearchManager`/`AIAnalyzer` (eram código morto — nunca chamados em lugar nenhum, confirmado antes de remover).
- Removidos os campos de API do Last.fm e "Search Engine ID" das Configurações (não são mais usados). O campo antes chamado "Google Custom Search API Key" foi renomeado para "YouTube Data API Key" — é usado só pra listar vídeos de canal, nunca teve relação com metadados (o nome antigo era enganoso).
- O Chrome headless (Selenium) usado pelo Painel Música do YouTube agora só é iniciado sob demanda (primeira vez que o fallback manual precisar dele), não mais toda vez que o programa abre.
- **Bug corrigido de bônus**: `SettingsWindow.save_settings()` chamava uma classe `DiscogsAPI` que não existe em lugar nenhum do projeto — isso quebraria com `NameError` toda vez que alguém clicasse "Salvar" nas Configurações. Removido; a chave do Discogs agora atualiza o identificador em tempo real sem precisar reiniciar o programa.

## 3. Álbuns não catalogados no Discogs (fila de pendentes)

- **`pending_queue.py`** (novo arquivo): fila persistida em `fila_pendentes.json`, unificando os dois casos ("não encontrado" e "baixa confiança"), cada item com `confidence_pct` (0% para não encontrado).
- Nova tela `_show_pending_queue()` (substitui a antiga "revisar álbuns"): lista os pendentes com % de confiança colorido, botão "☐/☑ Baixar" por item (marca, não baixa na hora), "🗑 Remover" (com confirmação, apaga de vez), "▶ Abrir no YouTube". Rodapé com "▶ Processar selecionados (N)" e "Ocultar".
- "Processar selecionados" baixa de fato os marcados: usa os dados do Discogs já encontrados (caso de baixa confiança) ou cai no pipeline antigo multi-fonte (caso "não encontrado"), exatamente como combinado.
- Botão "⏳ Pendentes" no rodapé principal abre essa tela a qualquer momento (mesmo fora do fim de um lote).

## 4. Bitrate mínimo configurável

- Novo campo "Bitrate mínimo aceito (kbps)" nas Configurações, pré-preenchido com **128** por padrão.
- `downloader.py`: depois de baixar, confere o bitrate reportado pelo yt-dlp (ou mede via `ffprobe` se não vier informado) contra o mínimo configurado; descarta o arquivo e retorna falha se ficar abaixo.

## 5. Botões do rodapé

- "Limpar Log" → **"Copiar Log"** (copia o conteúdo pra área de transferência).
- "Abrir Pasta" → sem mudanças.
- "Resetar Progresso" → **"Pausar"/"Continuar"** (toggle): pausa entre um álbum e outro (nunca no meio de um download/corte já em andamento). A função antiga de "resetar progresso salvo de canal/playlist" foi movida para dentro de Configurações (aba "Pasta de Saída"), já que virou um utilitário secundário.
- Novo botão "⏳ Pendentes" (abre a fila do item 3).
- Todos os botões utilitários (Copiar Log, Abrir Pasta, Pausar/Continuar, Pendentes) agora ficam **à esquerda do botão "Processar"**, na mesma linha — não mais soltos embaixo do log.

## 6. Ícone

- `icone.ico` (novo arquivo, gerado): disco de vinil preto com sulcos e rótulo na cor de destaque do app (#4F46E5), em 7 resoluções (16 a 256px).
- Usado como ícone do executável (`main.spec`) e da janela/taskbar em tempo de execução (`root.iconbitmap()` em `main.py`, com fallback silencioso em sistemas onde `.ico` não é suportado).
- Emoji do cabeçalho trocado de 🎵 para 💿.

## 7. Renomeação

- "YouTube Album Ripper" → **"FullTracksDownloader"** no título da janela, cabeçalho, diálogo de ajuda, nome do executável gerado (`build_exe.bat`, `main.spec`) e comentários/docstrings principais.
- Nomes de arquivo/módulo (`main.py`, `downloader.py` etc.) e nomes de classes internas **não** foram alterados, exceto `YouTubeAlbumRipperGUI` → `FullTracksDownloaderGUI` (era necessário para consistência com o novo nome, baixo risco por ser só uma renomeação mecânica de classe).

## 8. Corte no meio exato do silêncio

Corrigidos três pontos que cortavam no **início** do silêncio em vez do **meio** (causa raiz do "vaza um pouquinho da faixa anterior"):
- `SmartCutter._detect_all_silences_full_disk()` — usado por `cut_with_durations()`, o caminho mais comum quando o Discogs fornece durações.
- `SmartCutter._ffmpeg_silence()` — usado pela cascata de fallback `cut_directly_on_gaps()`.
- `SmartCutter._find_nearest_silence()` — hoje código morto (não chamado por ninguém), corrigido por consistência mesmo assim.
- `hybrid_silence_detector.py` (`HybridSilenceDetector.detect_without_durations()`) — também usava o fim do silêncio como corte; corrigido para o meio, junto com o comentário que dizia o contrário.

Um caminho (`SmartCutter.detect_gaps()`, usado por `cut_by_cross_validation`/`cut_with_consensus`/`cut_with_durations`) já cortava corretamente no meio — não precisou de mudança.

---

## Correções pós-entrega (a partir de um teste real em lote)

### A. Fluxo de confiança 80-100% não estava processando direto

**Bug real encontrado no primeiro teste em lote grande.** O sintoma no log: álbuns apareciam como `confiança: 100%` mas mesmo assim iam para a fila de pendentes com o motivo "confiança baixa". Causa: a decisão de "baixar direto" ou "enfileirar" usava o rótulo categórico `confidence` (`'low'/'medium'/'high'`) vindo de `score_discogs_candidate()`, que marca como `'low'` qualquer empate entre o 1º e o 2º colocado (margem < 20 pontos) — **mesmo quando os dois candidatos têm score alto** (ex: duas edições praticamente idênticas do mesmo álbum, ou entradas duplicadas no Discogs). O `confidence_pct` (percentual mostrado na tela) já vinha calculado corretamente a partir do score, mas não era isso que decidia o roteamento.

Corrigido: a decisão agora usa só o `confidence_pct` contra um limite (`FullTracksDownloaderGUI.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 80`, no topo da classe em `main.py`) — **80% a 100% processa direto, abaixo disso vai para a fila**. Aplicado nos dois pontos de roteamento (`process_single_video` e `process_playlists`). A cor do badge de confiança na tela de pendentes também foi realinhada para esse mesmo limite. Testado reproduzindo os valores exatos do log real (score=163/confidence='low'/pct=100 → agora processa direto; score=-27/pct=0 → continua enfileirando corretamente).

### B. Ícone da barra de tarefas/janela ainda aparecia como o padrão (a "pena")

O `root.iconbitmap(ICON_PATH)` sozinho não estava bastando em algumas combinações de Windows/Tk. Agora o programa aplica o ícone por **dois mecanismos independentes**, cada um com seu próprio tratamento de erro:
- `iconbitmap(default=ICON_PATH)` — mecanismo nativo do Windows via `.ico`, agora com `default=` para valer também em todas as janelas secundárias (Configurações, Álbuns pendentes etc.), não só na janela principal.
- `iconphoto(True, PhotoImage(...))` — mecanismo nativo do Tk via imagem (`icone_vinil.png`), mais consistente entre versões.

`icone_vinil.png` também foi adicionado aos dados embutidos no `main.spec`, junto com `icone.ico`.

### C. Downloads começaram a falhar 100% das vezes depois do filtro de bitrate mínimo

**Bug real, quebrava todo download.** Causas combinadas:

1. **Margem de tolerância ausente**: o bitrate medido (via `ffprobe`) de um áudio nominalmente "128kbps" quase nunca bate exatamente 128000 - fica um pouco acima ou abaixo por causa de VBR e overhead de container. Sem tolerância nenhuma, isso podia rejeitar áudio perfeitamente bom só por ficar 1-2kbps abaixo do limite. Adicionada margem de 8kbps (`TOLERANCE_KBPS` em `downloader.py`).
2. **Falha silenciosa**: o motivo real da rejeição (bitrate baixo, ou qualquer outro erro) só era passado pro `progress_callback` da chamada de download, e essa chamada usava um callback "mudo" (`lambda msg: None`) especificamente pra não poluir o log com progresso de download - só que isso também apagava a ÚNICA pista de por que o download tinha falhado. Toda falha aparecia genericamente como "Falha na tentativa N" e, no final, "Motivo comum: Vídeo privado, removido ou bloqueado" - mesmo quando o motivo real era outro completamente diferente.
3. **Retentativas inúteis**: quando o motivo da falha é determinístico (o bitrate da fonte não vai mudar entre uma tentativa e outra), o programa mesmo assim tentava 3 vezes com 2s de espera entre elas - desperdiçando tempo sem chance de dar certo.

Corrigido:
- `YouTubeDownloader` agora guarda `self.last_error` (motivo legível) e `self.last_error_retryable` (se vale a pena tentar de novo) depois de cada tentativa de download.
- `_download_and_process()` agora usa um filtro no callback que deixa passar pro log só o que importa (sucesso, erro, motivo de rejeição de bitrate) e esconde só o spam de progresso (%, velocidade).
- Quando `last_error_retryable` é `False` (ex: bitrate abaixo do mínimo), para na primeira tentativa em vez de insistir mais duas vezes à toa.
- A mensagem final de falha agora mostra o motivo real e específico, não mais um texto genérico fixo.

### D. Falha no download agora vai para a fila de pendentes

Reproduzindo a pergunta: sim - qualquer álbum que o Discogs identificou corretamente mas cujo **download** falhou (bitrate insuficiente, vídeo indisponível, erro de rede após 3 tentativas) agora entra na fila de "Álbuns pendentes" com o tipo `falha_download`, em vez de simplesmente ser descartado e esquecido. Na tela da fila, esses itens aparecem com um selo "❌ Falha no download" (em vez do percentual de confiança, que não é o problema nesse caso) e o motivo específico da falha. Clicar em "Baixar" tenta de novo usando os dados do Discogs já identificados (não precisa buscar tudo de novo) - útil por exemplo depois de baixar o mínimo de bitrate nas Configurações.

**Fora do escopo desta correção**: falhas de download no modo "Playlist Completa" (quando cada vídeo é uma faixa individual, não um álbum inteiro) continuam apenas logadas e puladas, sem entrar na fila - a granularidade por-música não se encaixa bem no conceito de "álbum pendente" da fila. Se isso também for necessário, é um ajuste à parte.

### E. Erro `'>' not supported between instances of 'str' and 'int'` ao reprocessar pendente

Bug real na correção do item D (falha no download → fila de pendentes). Quando um download falhava, eu guardava na fila o `discogs_data` já **formatado** para exibição (duração tipo `"3:22"`, texto), mas o código que reprocessa itens da fila espera o formato **bruto** vindo direto do Discogs (duração em segundos, número) — o mesmo formato usado pelos itens de "baixa confiança". Ao tentar reprocessar, `duração > 0` comparava uma string com um número e quebrava.

Corrigido: a conversão para o formato certo (string "M:SS" → segundos) agora acontece no momento de enfileirar. Também adicionei uma defesa na leitura, para não quebrar em itens que **já ficaram salvos em disco com o formato antigo** antes desta correção (ex: o item do Robert Knight que já estava na sua fila) — esses são detectados e convertidos automaticamente na hora de reprocessar, sem precisar removê-los manualmente.

### F. Log embaralhado / processamento concorrente

O botão "Processar selecionados" da fila de pendentes não tinha nenhuma trava contra rodar **ao mesmo tempo** que o lote principal (canal/playlist) já em andamento — foi isso que causou o log com seções intercaladas/duplicadas that você viu (duas threads escrevendo no mesmo log ao mesmo tempo) e piora o risco de as duas mexerem nos mesmos arquivos temporários. Agora usa a mesma trava (`self.processing`) do botão "Processar" principal: só um processamento por vez, de qualquer tipo. O botão da fila mostra "⏳ Processamento em andamento..." e fica desabilitado quando já há algo rodando, e mesmo num clique que escape dessa checagem visual (condição de corrida), a lógica interna recusa e avisa antes de iniciar qualquer coisa.

### G. Ajuste no corte do silêncio (estava cortando depois da faixa seguinte já ter começado)

Depois da correção anterior (cortar no meio do silêncio, não no início), o resultado prático passou a cortar **tarde demais** em alguns álbuns - depois da faixa seguinte já ter começado. Causa provável: o "silêncio" medido por threshold de dB não é o mesmo que o silêncio real percebido - em vinis com ruído de superfície, ou quando a próxima faixa tem uma entrada suave/gradual, o fim do silêncio "detectado" pode já estar dentro do áudio audível da próxima faixa. Usar o meio exato de um silêncio superestimado corta tarde demais.

Ajustado: em vez do meio exato, esses pontos de detecção inicial do silêncio (usados como estimativa aproximada antes do refinamento fino) agora avançam **no máximo 0,4 segundos** a partir do início do silêncio detectado (constante `SILENCE_CUT_MAX_OFFSET_SEC` no topo do `main.py`, mesma ideia replicada em `hybrid_silence_detector.py`). Isso mantém a melhoria sobre cortar exatamente no início sem arriscar avançar demais em silêncios longos ou mal-medidos. Essa parte continua em vigor mesmo depois do item I abaixo, porque afeta uma etapa diferente (a estimativa inicial, não o refinamento fino).

### H. Álbum não deve terminar com nomes genéricos (Track 1, Track 2...) sem avisar

Caso real: "Doris Day - What Every Girl Should Know" foi identificado no Discogs com 100% de confiança, mas o corte automático não conseguiu confirmar 3 das 12 faixas batendo com as durações informadas. Em vez de parar aí, o programa (comportamento que já existia antes desta conversa) caía num último recurso que ignora completamente o Discogs e corta só pela análise de silêncio - e como esse método achou uma contagem de faixas diferente (16, não 12), não tinha como saber os nomes reais, então usou "Track 1, Track 2...". Isso aconteceu de forma silenciosa, sem chance de revisão.

Corrigido: esse último recurso (`cut_by_cross_validation`, nomes genéricos) **não roda mais automaticamente**. Quando as etapas que respeitam as faixas/durações do Discogs falham, o álbum vai para a fila de "Álbuns pendentes" com o tipo `falha_corte` (selo "✂️ Corte não confirmado"), explicando que o corte não bateu e que processar mesmo assim resultará em nomes genéricos. Só quando você clica "Baixar" nesse item da fila é que o último recurso é liberado - exatamente como pedido ("se o usuário quiser, vai ter").

### I. Corte não bate no momento certo quando há fade in/fade out

Implementado (só o ajuste pedido, sem os outros dois que propus): o ponto de **menor energia (RMS)** dentro da janela de busca virou o **primeiro método tentado** no refinamento fino do corte, em vez de ser um último recurso quase nunca alcançado. Motivo: a detecção por limiar de decibéis quase sempre "acha algo" já na primeira tentativa (mesmo numa transição gradual/fade), então na prática o RMS nunca era usado - e é justamente ele que lida melhor com fades, porque acha o ponto de silêncio mais profundo de verdade, em vez de um ponto arbitrário onde o volume cruzou um limiar durante a rampa do fade.

**Bug real encontrado durante o teste** (antes de eu confirmar que a mudança funcionava): o cálculo de energia (RMS) tinha um erro de estouro de número - os dados de áudio são inteiros pequenos, e elevá-los ao quadrado sem antes converter para ponto flutuante estourava o limite do tipo e virava um número negativo sem sentido, fazendo o "ponto de menor energia" sempre apontar pro início da janela de busca, errado. Esse bug já existia no código antes desta conversa, só nunca tinha sido notado porque esse método quase nunca rodava. Corrigido (conversão para ponto flutuante antes da conta) e testado com áudio sintético (uma transição com fade real e um corte seco de controle) antes de promover o método - a versão com o bug teria piorado a precisão do corte, não melhorado.

Também adicionei um cache do áudio decodificado por álbum, já que o RMS agora roda uma vez por faixa (antes rodava raramente) - sem isso, cada faixa recarregaria e decodificaria o álbum inteiro do zero.

**Sobre calibrar ainda mais**: não tenho como ouvir o resultado real aqui, então não posso garantir que isso resolve 100% dos casos de fade. Se ainda cortar no lugar errado depois dessa mudança, me diga o que você ouviu (cedo ou tarde demais, quantos segundos aproximadamente) para eu ajustar com base em dado real, em vez de continuar chutando.

### J. Erro 429 (limite de requisições do Discogs) sendo tratado como "não encontrado"

Causa raiz: para cada álbum, o programa buscava até 40 candidatos e fazia uma requisição de detalhe **separada** para cada um, só para pontuá-los - até ~42 requisições por álbum. O Discogs limita a 60 requisições/minuto por token, então um único álbum ambíguo (muitos homônimos) já podia esgotar o limite sozinho, fazendo **todos os álbuns seguintes** no mesmo minuto voltarem 429 - e o programa tratava isso exatamente igual a "esse álbum não existe no Discogs", jogando tudo na fila com 0% de confiança sem qualquer chance real de ter sido respondido.

Corrigido:
- Reduzido o teto de candidatos testados de 40 para 20 (a busca estruturada já prioriza os mais prováveis primeiro).
- Novo método `_discogs_get()` em `metadata_hunter_voting.py`: quando a resposta é 429, espera (respeitando o cabeçalho `Retry-After` do Discogs, ou um recuo progressivo) e tenta de novo automaticamente, em vez de desistir na hora. Também aplica um intervalo mínimo entre requisições pra reduzir a chance de bater no limite.
- `MetadataHunter.last_error` agora distingue "genuinamente não encontrado" (0 resultados de verdade) de `'rate_limited'` (nunca chegou a ter uma resposta real).
- Na fila de pendentes, esses casos agora entram como um tipo novo, `erro_discogs` (selo "⏳ Erro de conexão"), separado de "não encontrado". Ao clicar "Baixar" nesse item, o programa **tenta o Discogs de novo primeiro** - só cai no fallback multi-fonte antigo se isso também não resolver.

### K. Pausar o lote principal e processar a fila de pendentes ao mesmo tempo

Antes, a trava de concorrência (item F) bloqueava a fila de pendentes sempre que `self.processing` estivesse ligado - mesmo só PAUSADO, quando na real nada está acontecendo (a thread principal só está dormindo entre álbuns). Agora a trava distingue: pausado libera processar a fila normalmente; rodando de verdade (ou a própria fila já processando algo) continua bloqueado - dos dois lados (o botão "Processar" principal também recusa iniciar se a fila estiver ocupada). Testados os quatro cenários (rodando bloqueia, pausado libera, nada rodando libera, fila ocupada bloqueia o botão principal).

**Isso evoluiu para o item M abaixo** depois que percebemos, num teste real, que a versão inicial (deixar pausado e esperar pelo mesmo botão) causava uma corrida de dois processamentos ao mesmo tempo quando o usuário clicava "Continuar" enquanto a fila ainda rodava.

### L. Bar-Kays - Gotta Groove cortado errado (álbum quase sem silêncio real entre faixas)

Causa raiz: quando a busca por silêncio ao redor da posição esperada (calculada pela duração de cada faixa) não achava nada suficientemente perto, ela ia alargando a janela de busca progressivamente (até ±150s) e **aceitava o que encontrasse dentro dessa janela, não importa a distância** do esperado - inclusive uma pausa qualquer dentro de outra faixa, não uma fronteira real entre faixas. Em álbuns com pouco ou nenhum silêncio real de verdade (como esse, ao que tudo indica uma gravação sem pausas perceptíveis entre faixas), isso resultava em cortes até 70+ segundos errados, mesmo "confirmados" como se fossem silêncio real.

Corrigido (nessa primeira versão): só aceita esse silêncio "reencontrado" se ele ficar a no máximo 25 segundos da posição que a duração da faixa (Discogs) prevê, no mecanismo de reataque local. Essa parte permanece válida - **veja o item O abaixo** para o refinamento aplicado também na primeira tentativa de corte, que não usava esse limite ainda.

### M. Pausar/Continuar contextual (lote principal vs. fila de pendentes)

Implementado do jeito certo depois de duas tentativas (a primeira, com "pausa e espera pelo mesmo botão", ficava travada esperando um "continuar" que não fazia sentido nesse fluxo). O comportamento final:

- Lote rodando (fila parada): botão controla a pausa do **lote**, como sempre.
- Lote pausado, fila processando: botão vira "⏸ Pausar (fila)" - clicar **para a fila** (não pausa-e-espera): termina o item atual (nunca interrompe um download/corte em andamento) e não começa o próximo. O que sobrar continua **marcado** na fila, pronto para rodar de novo quando o usuário clicar "Processar selecionados" outra vez.
- Assim que a fila para (ou termina sozinha), o botão volta a controlar o lote principal - nunca libera o lote só porque a fila parou de processar, resolvendo em definitivo a corrida de dois processamentos ao mesmo tempo (o mesmo bug que causou o erro `[WinError 32]` de arquivo em uso por dois processos).

Testada a sequência completa (lote → pausa → fila assume o botão → para a fila → botão volta pro lote → retoma o lote) e a integração real com a fila (processa o item em andamento, remove ele da fila, mantém os restantes marcados).

### N. Silêncio inicial do disco contado na timeline esperada

Álbuns com alguns segundos de silêncio antes da faixa 1 realmente começar (comum em rip de vídeo do YouTube) faziam a timeline esperada (soma das durações do Discogs a partir do segundo 0) ficar sistematicamente adiantada - e esse erro se repetia (às vezes crescia) em todas as faixas seguintes, como visto no álbum do Robert Knight. Agora o programa mede esse silêncio inicial (rápido, só os primeiros 30s do arquivo) e usa isso como ponto de partida da timeline, nos dois métodos de corte que fazem essa soma. Testado com áudio sintético com 3s de silêncio real no início (detectou 3,00s) e confirmado que álbuns sem silêncio inicial continuam com offset 0 (sem regressão).

### O. Corte que discorda da API, mas com evidência forte de áudio, não deve ser descartado

Reconsideração importante do item L (Bar-Kays): ao investigar o álbum "Doris Day - What Every Girl Should Know", percebemos que um corte considerado "suspeito" (23,9s longe do esperado) tinha **5 votos** - o máximo de confiança que o sistema consegue dar, várias detecções concordando. Isso é forte indício de que o corte estava certo e a **duração informada pelo Discogs para aquela faixa específica** é que estava errada (comum em transcrições manuais de tempos de faixa no Discogs). Aplicar cegamente "prefira sempre a matemática quando a distância for grande" teria piorado esse caso.

Corrigido de forma mais criteriosa: o limite de distância aceitável agora depende de quantos métodos concordam (votos) com o silêncio encontrado, na primeira tentativa de corte (a mesma ideia do item L, agora estendida pra esse outro ponto do código). Silêncio com 4+ votos (evidência forte) continua sendo aceito até 30s de distância do esperado - é o que preserva o corte correto do Doris Day. Silêncio com menos votos (evidência fraca) agora precisa estar a até 15s do esperado, senão é descartado e cai para a estimativa por duração (ancorada nos vizinhos) - é o que teria evitado o problema original do Bar-Kays. Testados os dois casos reais isoladamente, com resultado oposto correto em cada um.

### P. Créditos e log do master_id

- Adicionada uma assinatura em itálico ao final do popup de ajuda principal ("Como funciona o FullTracksDownloader"): *Elaborado por Glauco - Barra do Piraí - RJ*. Só nesse popup, não nos outros.
- O log agora mostra o valor real do `master_id`/`release_id` do Discogs gravado em cada álbum (antes só confirmava "gravado em N faixas", sem mostrar qual o número) - tanto no modo álbum quanto no modo playlist.

### Q. Item da fila reprocessado por bitrate saía com nomes genéricos (Track 1, Track 2...)

Bug real: `allow_cross_validation` (a permissão pro último recurso de nomes genéricos - ver item H) usava a mesma variável que só indicava "isso veio da fila de pendentes" (`from_pending`), sem checar POR QUE o item estava lá. Um álbum que caiu na fila só por bitrate baixo (`falha_download`) nunca teve o corte testado - identificação e faixas reais já estavam corretas desde a primeira tentativa. Mesmo assim, ao clicar "Baixar" nesse item, o programa liberava nomes genéricos à toa, porque tratava "veio da fila" como sinônimo de "o corte já falhou e foi aprovado manualmente".

Corrigido: `allow_cross_validation` agora é decidido pelo TIPO do item (`item['kind'] == 'falha_corte'`), não mais só por vir da fila. Só itens que já tiveram o corte tentado e rejeitado (`falha_corte`) liberam o último recurso; itens de bitrate, erro de conexão ou baixa confiança continuam com o corte automático normal (que, se falhar de verdade, aí sim vai pra fila como `falha_corte`, e só então libera). Testados os dois casos isoladamente com o cenário real relatado.

### R. Índice do acervo (acervo_index.json) ficava vazio mesmo com álbuns corretamente tagueados

Bug real na reconstrução do índice (quando o arquivo é apagado ou está ausente): o código só considerava um álbum "encontrado" se ele tivesse `master_id` gravado, ignorando por completo qualquer álbum tagueado só com `release_id` - que é exatamente o que acontece quando o Discogs não vincula aquele lançamento específico a nenhum "master" (comum em edições avulsas). O resto do programa (a escrita da tag, a checagem de duplicata) sempre aceitou `release_id` como alternativa ao `master_id` - só a reconstrução do índice esquecia essa regra, fazendo o índice voltar vazio (ou incompleto) mesmo com MP3s corretamente tagueados no disco.

Corrigido: a reconstrução agora usa `master_id` OU `release_id`, a mesma regra usada em todo o resto do programa. Testado com um álbum tagueado só com `release_id` (o caso que estava sendo perdido) e confirmado que o caso normal (com `master_id`) e o caso de álbuns realmente sem tag nenhuma (de antes dessa funcionalidade existir) continuam se comportando como antes.

## Novidade: tela de busca de playlists (botão 🔍 no cabeçalho)

Nova tela, aberta pelo botão "🔍 Buscar Playlists" no cabeçalho, com dois campos: **Artista** (obrigatório) e **Álbum** (opcional). Não baixa nada sozinha - o resultado alimenta o modo "Playlist Completa" já existente, então quase não mexe no resto do programa.

- **Só artista**: busca várias playlists do YouTube (prováveis álbuns diferentes do artista) - seleção **múltipla** (☐/☑), marca quantas quiser.
- **Artista + álbum**: busca candidatas a serem *aquele* álbum específico - seleção **única** (○/◉, estilo rádio - marcar uma desmarca a anterior automaticamente), porque a pergunta aqui é "qual dessas é a certa", não "quais eu quero".
- A busca sempre inclui o termo de viés **"full album"** (ex: `"Doris Day full album"` ou `"Doris Day What Every Girl Should Know full album"`), pra priorizar playlists de álbum de verdade em vez de mixes/coletâneas de fã - é só uma pista de relevância pro YouTube, não um filtro exato (playlists sem essas palavras no título ainda podem aparecer).
- Cada resultado mostra o número de vídeos da playlist (dá uma pista rápida: 8-15 provavelmente é um álbum; 100+ provavelmente não é) e um botão pra abrir no YouTube antes de decidir.
- O botão final ("Usar selecionada(s) na Playlist Completa") pega os links marcados, preenche o campo de playlists do modo "Playlist Completa" e já troca pra esse modo, pronto pra clicar "Processar".

**Requisito**: usa a mesma "YouTube Data API Key" já configurada em Configurações (a mesma usada pra listar vídeos de canal) - sem ela, essa busca especificamente não funciona (o resto do programa continua normal). Novo método `search_playlists()` em `downloader.py`.

Testados os dois modos de seleção (múltipla e única/rádio) de ponta a ponta, incluindo o preenchimento do campo e a troca de modo, e os casos de erro (sem artista digitado, sem chave de API configurada, busca sem resultados) - nenhum deles trava a tela.

### S. Modo "Playlist Completa" mostrava sempre o mesmo motivo genérico de falha, escondendo o motivo real

Bug real, achado ao investigar um relato de "a busca não baixa" - na real não tinha nada a ver com a busca (que só preenche o campo de playlist e troca de modo, sem tocar no download). O problema já existia antes, só nunca tinha aparecido num log analisado até agora: o download por música do modo playlist (`process_playlist_song`) tem seu próprio bloco de tentativas, separado do usado no modo álbum/canal - e esse bloco **descartava a mensagem de erro de verdade** do yt-dlp (`progress_callback=lambda msg: None`), sempre mostrando a mesma frase genérica "Vídeo privado, removido ou bloqueado" não importa qual fosse o motivo real (ex: limite de requisições do YouTube, erro de rede, etc.) - o dado certo já existia internamente (`self.downloader.last_error`), só não era usado aqui.

Corrigido: esse bloco agora usa o mesmo filtro de mensagens e a mesma lógica do modo álbum - mostra o motivo real quando disponível (só cai no genérico como último recurso, se realmente não houver nada mais específico) e para de tentar de novo à toa quando o motivo é determinístico (e.g. bitrate abaixo do mínimo), em vez de gastar as 3 tentativas e ~4s de espera sempre. Testados os três casos: motivo real disponível (aparece no log), sem motivo específico (cai no genérico, sem quebrar) e motivo determinístico (para na primeira tentativa).

### T. Corte cedo demais - refinamento rejeitava um resultado melhor por causa de um limite mais apertado que o do candidato original

Bug real, achado reconstruindo com números exatos o log de um álbum com corte adiantado (faixa 1 do Terumasa Hino Quintet - Into The Heaven): o candidato original foi aceito 18,6s longe do esperado (dentro do limite de até 30s liberado pra achados com boa votação - ver item O). O refinamento fino então achou uma posição REALMENTE melhor, só 12,4s longe do esperado - mas foi **rejeitada**, porque o refinamento só aceitava resultados dentro de ±10s do esperado, um limite mais apertado que o usado pra aceitar o próprio candidato original. Resultado: ficava com o pior dos dois quando o melhor estava disponível, cortando mais cedo do que precisava.

Corrigido: o refinamento agora compara a distância do resultado refinado contra a distância do candidato original - aceita sempre que for uma melhora real (mais perto do esperado), em vez de um teto fixo isolado que podia ser mais rígido que o critério já usado pra aceitar o ponto de partida. Testado reproduzindo os números exatos do log (refinamento melhor é aceito) e o caso de regressão (refinamento pior continua sendo rejeitado, mantém o original).

### U. Prefere o ano mais antigo entre candidatos empatados no Discogs

Quando o mesmo álbum tem várias reedições/pressagens cadastradas no Discogs com a duração e faixas idênticas (caso comum - o Terumasa Hino Quintet tinha a mesma gravação listada em 2024, 1997, 1970 e 1980), o desempate ficava por conta da ordem em que a API do Discogs devolveu os resultados - que não é significativa nem determinística.

Ajustado (revisado depois do feedback): a **escolha do candidato** (faixas, duração, master_id/release_id, capa) continua exatamente como antes, só por pontuação - não muda mais qual "release" é usado. O que muda é só o **ano exibido**: calculado à parte como o menor ano entre todos os candidatos que compartilham o mesmo `master_id` do vencedor (outras edições catalogadas da mesma obra, segundo o próprio Discogs) - representa "quando a obra passou a existir" em vez do ano da pressagem específica escolhida pela pontuação. Testado com o cenário do Terumasa Hino (mantém o release vencedor, ajusta só o ano pro mais antigo) e os casos de borda (candidato único, sem master_id) - não muda nada nesses casos.

### V. RMS mínimo cortava no início do silêncio, não no meio (erro pequeno, mas sistemático)

Depois do item T (refinamento), o erro caiu para menos de 1 segundo - uma melhora grande, mas ainda restava um viés sistemático: `_find_rms_minimum` usava `argmin`, que devolve a PRIMEIRA janela que bate no valor mínimo de energia - e um silêncio de verdade não é um ponto único, é um trecho inteiro de várias janelas seguidas com energia igual ou quase igual (o "chão de ruído" da gravação). Pegar só a primeira dessas janelas equivale a cortar bem no INÍCIO do trecho silencioso, não no meio - o mesmo problema original desta conversa (antes de trocar pro RMS), só que bem mais discreto agora.

Corrigido em duas partes: (1) em vez de pegar só a primeira janela no mínimo, agora expande para os dois lados a partir do mínimo global enquanto os vizinhos continuarem dentro de uma margem pequena (mesmo chão de ruído), e usa o meio desse trecho contíguo; (2) a posição de cada janela agora é medida pelo seu CENTRO, não pelo início dela (evita um viés adicional, já que uma janela que começa a "vazar" pro áudio alto seguinte tem RMS mais alto, encolhendo o platô medido só do lado direito). Testado com o mesmo áudio sintético de silêncio real usado antes nesta conversa (2s de silêncio) - o resultado saiu a menos de 0,15s do meio exato, contra ~1s de erro antes dessa correção. Testado também que o caso de fade (sem platô plano) continua funcionando normalmente.

### W. Refinamento não tinha alcance suficiente pra chegar na posição esperada, mesmo quando ela era melhor

Analisando os números exatos de um corte com ~23s de erro (Love More Train ficou maior do que devia), achei que eram na real DOIS erros pequenos, em direções opostas, nas duas fronteiras da faixa: uma ficou 13s cedo demais, a outra 8s tarde demais - e os dois se somaram na faixa do meio. Em ambos os casos, o candidato inicial já estava razoavelmente longe do esperado (19s e depois 8s), e o refinamento fino - que só busca num raio fixo de ±10s ao redor do candidato - simplesmente não tinha alcance matemático pra sequer chegar na posição esperada, mesmo que houvesse um silêncio real bem ali.

Ajustado: o raio de busca do refinamento agora cobre pelo menos a distância até a posição esperada (+ uma margem de 10s), até um teto de 30s - em vez de um raio fixo de 10s. Como o refinamento já só aceita um resultado quando ele é uma melhora real (item T), alargar o raio de busca é seguro: só pode achar algo melhor, nunca pior.

### X. Achado com 1 voto (evidência quase nenhuma) sendo aceito só por estar "mais perto disponível"

Testando de novo o mesmo álbum depois do item W, o resultado não mudou - e o motivo era outro: o corte problemático (faixa 2/3) tinha só **1 voto** entre ~13 métodos de detecção, mas foi aceito porque outro método diferente, tentado ANTES do que já tinha ganhado atenção especial nesta conversa (`cut_directly_on_gaps` - a estratégia "PROXIMIDADE PROGRESSIVA"), escolhe sempre o candidato mais próximo dentro da janela sem nunca olhar quantos métodos concordam com ele. Ouvindo o áudio, a fronteira real ficava 35 segundos depois de onde o Discogs previa - ou seja, não era imprecisão de detecção, era a duração de referência da própria faixa que parece estar errada pra esse vídeo específico, e o achado de 1 voto só coincidiu de estar "próximo o bastante" dessa referência errada pra ser aceito com confiança demais.

Corrigido em dois lugares: (1) `cut_directly_on_gaps` agora exige pelo menos 2 votos pra considerar um candidato válido dentro da janela - um achado isolado (1 só detector) não vira mais "sucesso" só por não ter nada melhor por perto, e o método falha nesse caso, abrindo caminho pro próximo método (com durações), que tem mais camadas de segurança; (2) o mesmo piso mínimo de 2 votos foi aplicado à primeira tentativa de `cut_with_durations` (que já tinha um limite de distância dependente de votos - item O - mas não tinha um piso absoluto, então um achado de 1 voto perto o bastante ainda passava). Testados os dois pontos isoladamente com os números exatos do caso real, e confirmado que casos com votação normal (3+) continuam funcionando sem nenhuma mudança.

**Importante**: essa correção resolve o "aceitar demais" - evita que um achado fraco seja usado com confiança de sobra. Não resolvo (e não tenho como resolver só no algoritmo de corte) o problema de fundo, que parece ser a duração de referência do Discogs estar errada por ~35s pra essa faixa específica desse vídeo - isso é um problema do dado de referência, não da busca por silêncio em si.

### Y. Fade out: o murmúrio final ficava grudado no começo da faixa seguinte (versão final: detecção por assimetria, não porcentagem fixa)

Relatado em dois álbuns diferentes (Thunderclap Newman e Helen Humes): quando uma faixa termina com fade out, o corte acontecia um pouco cedo demais, deixando os últimos resquícios/murmúrio da faixa anterior grudados no começo da faixa seguinte. Ajustei em várias rodadas usando uma porcentagem fixa dentro do trecho de silêncio (65%, depois 85%, depois 95%) - mas isso criou um problema novo: faixas **sem** fade out passaram a cortar tarde demais, porque uma porcentagem alta o bastante pra "salvar" o murmúrio de um fade sempre corta cedo demais num corte seco comum, que não tem esse murmúrio pra salvar.

Resolvido de vez, medindo a assimetria de verdade em vez de chutar um número fixo: o programa mede quanto tempo cada LADO do silêncio detectado demora pra voltar ao volume normal (a "inclinação" real da transição, não uma suposição). Um fade out tem um lado que demora muito mais que o outro (a faixa que está sumindo aos poucos); um corte seco tem os dois lados voltando rápido, de forma parecida. O corte é deslocado pra mais perto do lado que volta RÁPIDO (a fronteira real) - proporcionalmente à diferença medida.

Calibrado com dois ajustes finos depois de testar os quatro cenários: a base (quando os dois lados voltam ao normal de forma parecida, sem fade detectável) subiu de 50% pra **85%** - mesmo um corte seco soa melhor com um pouco menos de silêncio de sobra antes da próxima faixa; e o teto (quando a assimetria aponta claramente um fade out) subiu de 90% pra **98%** - deixando o mínimo de murmúrio possível grudado na faixa seguinte. Testados os quatro cenários sintéticos de novo depois do ajuste: corte seco simétrico (agora mais perto do fim do silêncio, ainda dentro dele), fade out com murmúrio (erro caiu pra ~0,25s), fade-in isolado e fade simétrico dos dois lados - todos deslocando na direção certa.

### AB. Desempate fino por faixa entre candidatos empatados do Discogs

O álbum "What Every Girl Should Know" (Doris Day) tinha vários candidatos do Discogs empatados na mesma pontuação (163.0 pts, todos de 1960) - provavelmente entradas de catálogo duplicadas pra praticamente a mesma gravação. A reavaliação que já existe (comparando a duração TOTAL medida contra cada candidato, item da rodada anterior) não distingue entre eles nesse caso, porque o total pode bater igual mesmo que as faixas individuais sejam ligeiramente diferentes entre candidatos - e o desempate acabava caindo na ordem arbitrária da busca.

Adicionado um desempate mais fino: quando vários candidatos ficam empatados (ou quase, dentro de 1 ponto) na pontuação agregada, compara a duração REAL medida de CADA faixa contra o que cada candidato empatado informa pra aquela posição específica (não só o total) - e escolhe quem bater mais de perto nessa comparação faixa a faixa. Não tem custo de API nova: os dados de cada candidato já estavam todos em memória desde a busca inicial, é só uma comparação a mais sobre o que já tinha sido buscado. Implementado de forma geral (não só pra esse álbum específico), já que não muda nada nos casos que já funcionavam bem - só entra em ação quando realmente há empate.

Testados os três cenários: candidatos empatados com dados por faixa genuinamente diferentes (escolhe o que bate melhor, com log mostrando os dois erros médios comparados); candidatos empatados com dados IDÊNTICOS por faixa - o cenário mais provável quando são duplicatas reais de catálogo (reconhece que não há como distinguir e não inventa uma escolha, só registra isso no log); e um vencedor claro sem empate (não interfere em nada).

### Z. Corrida de dois álbuns processando ao mesmo tempo, mesmo com o lote pausado

Bug real e sério, visto direto no log: o usuário pausou o lote principal enquanto um álbum ainda estava sendo processado (Nina Simone) - e a fila de pendentes começou a processar outro álbum (Doris Day) **ao mesmo tempo**, ainda com o primeiro em andamento (os logs saíram completamente intercalados, e apareceu de novo o erro de arquivo em uso por dois processos ao mesmo tempo, `[WinError 32]`).

Causa raiz: a trava que libera a fila de pendentes (item K/M) usava `self.paused` como sinal de "seguro processar agora" - mas `self.paused` só significa "assim que o álbum atual terminar, vai pausar" - ele vira `True` IMEDIATAMENTE quando o usuário clica, mesmo que o álbum anterior ainda vá levar minutos pra terminar (a pausa só é checada no início de cada álbum, não no meio de um já em andamento). A fila via `self.paused=True` e liberava o botão na hora, sem saber que o lote ainda estava ativo de verdade.

Corrigido: nova flag `self.between_albums_idle`, ligada pelo próprio loop de processamento exatamente no ponto onde ele está genuinamente parado entre um álbum e outro (não só "vai parar") - e é essa flag, não mais `self.paused`, que decide se o botão "Processar selecionados" da fila fica liberado. Testada a condição isolada reproduzindo os números exatos do log (pausado + álbum ainda ativo = bloqueado; pausado + genuinamente ocioso = liberado) e a interface (o botão mostra "Processamento em andamento..." desabilitado até o lote realmente parar, não só quando pausado).

### AA. Índice do acervo ficava vazio mesmo em álbuns processados com sucesso pelo modo automático

Achado direto no acervo_index.json real enviado pelo usuário: só tinha o álbum reprocessado pela fila de pendentes (Doris Day); os outros três álbuns do mesmo lote (Terumasa Hino, Freddie North, Nina Simone), processados com sucesso pelo modo automático normal, estavam faltando - mesmo com os MP3s corretamente identificados e tagueados.

Causa raiz: depois que o corte termina, o programa reavalia a escolha do Discogs usando a duração/contagem de faixas REAIS medidas no áudio (etapa "🔁 Reavaliando escolha do Discogs..." do log, roda quase sempre - qualquer álbum com mais de 1 candidato do Discogs passa por ela). Essa reavaliação troca `discogs_data` pelo candidato re-pontuado - mas esse candidato vem no formato BRUTO da busca do Discogs, que usa as chaves `master_id`/`release_id` (sem prefixo), enquanto o resto do código (a gravação das tags TXXX e do índice do acervo) lê `discogs_master_id`/`discogs_release_id` (COM prefixo). Sem mapear isso, o master_id se perdia silenciosamente bem nessa troca - mesmo quando a escolha era "confirmada" (não trocava de álbum, só re-verificava), o dado se perdia do mesmo jeito.

Corrigido: mapeia explicitamente as chaves sem prefixo pras chaves com prefixo logo depois da reavaliação. Testado reproduzindo exatamente esse cenário (candidato bruto reatribuído a `discogs_data`) e confirmado que o master_id/release_id agora sobrevive até a gravação das tags/índice.


Testado nesta revisão: sintaxe de todos os arquivos (`py_compile`), importação real do `main.py`, a lógica de corte no meio do silêncio (dados sintéticos), gravação/leitura de tags TXXX em MP3 real (ffmpeg), reconstrução do índice do acervo a partir de MP3s reais, a fila de pendentes (add/marcar/remover/persistência), `discogs()` com respostas simuladas da API (captura correta de master_id/release_id, escolhe o release certo e não um bootleg), a checagem de bitrate mínimo (valor reportado e medido via ffprobe), e a interface gráfica completa rodando de verdade sob Xvfb (criação da janela, os 3 modos, Configurações, Pausar/Continuar, Copiar Log, abrir a fila de pendentes vazia e com itens, marcar/remover itens).

**Não foi possível testar** (o ambiente de execução não tem acesso à internet real para discogs.com/YouTube, nem um Windows de verdade para o .exe): uma busca real na API do Discogs, um download real do YouTube, e a geração do executável final via `build_exe.bat`/PyInstaller. Recomendo testar esses três pontos assim que possível no seu ambiente normal antes de usar em lote grande.

### AC. Playlist rejeitada inteira se qualquer faixa falhar no download

Visto no log real: a playlist "Beck - Midnite Vultures" teve 11 de 13 faixas falhando por bitrate baixo na fonte, mas o programa mesmo assim declarou "✓ Playlist concluída!" com só 1 faixa de verdade baixada - um álbum claramente incompleto sendo apresentado como pronto.

Corrigido: `process_playlist_song` agora retorna se deu certo ou não (antes não retornava nada, o chamador não tinha como saber). O loop de playlists para assim que UMA faixa falha - comportamento pedido explicitamente (não é "se a maioria falhar", é qualquer falha rejeita a playlist inteira) - apaga a pasta parcial (as faixas que já tinham baixado com sucesso antes da falha) e coloca a playlist inteira na fila de pendentes (`falha_download`), igual ao modo álbum quando o download falha. Testados os dois cenários: uma falha no meio (para na hora, não processa as faixas seguintes, pasta removida, item na fila) e sucesso total (nada muda).

### AD. Botão "Processar" travado mesmo com o lote pausado e genuinamente ocioso

Reportado pelo usuário: pausar o lote principal (canal/playlist em andamento) e tentar processar um vídeo avulso ou uma playlist encontrada pela busca (🔍 Buscar Playlists) nesse meio tempo não funcionava - o botão "Processar" ficava travado o tempo todo, mesmo com o lote genuinamente parado entre álbuns (mesma flag `self.between_albums_idle` do item Z desta revisão anterior).

Corrigido reaproveitando o mesmo mecanismo já usado pela fila de pendentes: `process_url()` e `process_playlists()` ganharam um parâmetro `guest_mode` - quando rodam como um trabalho avulso durante uma pausa, gerenciam `self.pending_processing` (que já bloqueia retomar o lote principal e mostra o botão certo) em vez de `self.processing`/`process_button`, que pertencem ao lote principal. Um novo método `_refresh_main_buttons_state()` reabilita visualmente o botão "Processar" no momento exato em que o lote fica genuinamente ocioso (chamado de dentro da thread de fundo via `root.after`, pros dois modos - canal e playlist).

Achado durante a implementação: um trabalho avulso que ele mesmo processa vários itens (ex: um canal, ou várias playlists) usa esse MESMO `self.between_albums_idle` no seu próprio loop interno - o que podia deixar a flag em `False` ao terminar, mesmo com o lote principal (pausado) continuando genuinamente ocioso. Corrigido restaurando a flag corretamente ao final do trabalho avulso, se o lote principal ainda está rodando e pausado. Testados os cinco estados do botão isoladamente (nada rodando, lote ativo, lote pausado+ocioso, trabalho avulso rodando, trabalho avulso terminando) e a decisão de `start_processing` em cada cenário (inicia em modo convidado quando deveria, recusa quando já tem algo rodando).

### AE. Busca de playlists agora filtra por bitrate mínimo configurado

Pedido do usuário: a tela de busca de playlists (🔍 Buscar Playlists) só deveria trazer playlists cuja fonte tem qualidade de áudio acima do mínimo configurado nas Configurações - evita descobrir que a fonte é ruim só depois de já ter tentado baixar o álbum inteiro (o cenário do item AC acima).

Implementado sondando a PRIMEIRA faixa de cada playlist candidata (sem baixar nada, só consultando os formatos disponíveis via yt-dlp) como amostra representativa - checar todas as faixas de todas as playlists custaria caro demais pra uma busca interativa (a busca já usa até 15 playlists candidatas; checar cada faixa de cada uma seria dezenas de sondagens extras). Playlists do mesmo canal/uploader costumam manter a mesma qualidade de codificação em todas as faixas, então a primeira já é um bom indício. Quando não consegue sondar (erro de rede, vídeo indisponível), deixa a playlist passar em vez de descartar à toa. Testados os cenários: playlist de baixa qualidade filtrada corretamente (reproduzindo o caso real de 66kbps visto no log), filtro desligado (`min_bitrate_kbps=0`) não sonda nada, e sondagem que falha não descarta a playlist.

### AF. Bitrate: confiava no valor reportado pelo yt-dlp em vez de medir o arquivo real

Reportado pelo usuário com um caso concreto: o álbum "Honi Gordon Sings" foi descartado por bitrate (89kbps reportado, abaixo do mínimo de 100kbps configurado na época) - mas ao baixar de novo depois com o mínimo mais baixo, todas as 9 faixas do arquivo final mediam entre 167-186kbps, bem acima do que tinha sido reportado (quase o dobro).

Causa: `_meets_min_bitrate()` confiava no valor que o yt-dlp reporta ANTES de baixar (`reported_abr`), e só media o arquivo baixado de verdade via ffprobe quando esse valor vinha ausente - nunca quando vinha presente, mesmo que errado. Corrigido invertendo a prioridade: mede o arquivo REAL baixado via ffprobe primeiro sempre que possível (é a fonte de verdade, o arquivo já está ali) - o valor reportado pelo yt-dlp só é usado como último recurso, se a medição real falhar por algum motivo (ffprobe indisponível, etc.). Testados os cenários: valor reportado errado com arquivo real bom (agora aceita, reproduzindo o caso do Honi Gordon), arquivo genuinamente ruim (continua rejeitando), ffprobe indisponível (usa o valor reportado como último recurso), e nenhuma informação disponível (não descarta à toa).

### AG. Reataque local não deve mais estimar por duração sem nenhum silêncio real confirmado

Achado investigando o mesmo álbum "Honi Gordon Sings": mesmo depois do bitrate corrigido, uma das 9 faixas ("Walkin' Out The Door") foi cortada usando só a duração informada pelo Discogs, sem NENHUM silêncio real confirmando esse corte específico - o silêncio mais próximo encontrado ficava 139s longe do esperado, longe demais pra confiar, e o programa caía de volta pra uma estimativa puramente matemática. O próprio log já sinalizava isso ("corte ESTIMADO... vale conferir manualmente", "7/8 gaps por silêncio real"), mas o álbum era entregue como sucesso normal mesmo assim, sem parar pra revisão - o mesmo risco de "estimativa sem confirmação apresentada com a cara de um corte confiável" discutido antes nesta conversa pros outros dois casos (nomes genéricos e corte cross-validation), só que num mecanismo diferente e mais antigo (o reataque local com âncoras dos dois lados, existente desde bem no início do projeto).

Removida a estimativa por duração do reataque local por completo: quando nenhuma faixa do buraco tem silêncio real confirmado (mesmo isolada, mesmo com âncora confiável dos dois lados), o corte fica sem solução - o que já faz o álbum inteiro cair pra "DISCO REJEITADO" e ir pra fila de pendentes, em vez de ser entregue com uma faixa estimada sem aviso. Testado que: (1) o cenário exato do Honi Gordon (silêncio real longe demais do esperado) agora deixa a faixa sem corte, sem mais gerar `math_fallback_anchored`; (2) quando HÁ silêncio real confiável, o reataque continua resolvendo normalmente, sem regressão; (3) buracos maiores (várias faixas seguidas) continuam se comportando como antes (já não estimavam).

### AH. `cut_directly_on_gaps` ignorava a duração do silêncio, só olhava proximidade

Reportado pelo usuário com um caso concreto: no álbum "Julie Wilson - My Old Flame", a fronteira entre as faixas 4 e 5 foi cortada numa pausa de ~2,3s dentro da própria faixa 4 (uma pausa curta, não a fronteira real) - o usuário confirmou por audição que existe um silêncio de verdade mais longo logo depois, e que essa pausa curta é nitidamente mais curta que a fronteira real.

Causa: o método que decidiu esse corte (`cut_directly_on_gaps`, a estratégia "PROXIMIDADE PROGRESSIVA") tem um critério deliberado, marcado no próprio código como "V10: Ordena por PROXIMIDADE (não score!)" - ele escolhe sempre o candidato mais PRÓXIMO da posição que o Discogs prevê, nunca considerando a duração do silêncio em si. Uma pausa curta dentro de uma faixa (respiro, pausa instrumental) que calhe de estar mais perto da previsão do Discogs vence um silêncio de verdade mais longo que esteja um pouco mais distante.

Corrigido: quando existir, dentro de uma tolerância extra de distância (até 15s além do candidato mais próximo), um silêncio nitidamente mais longo (pelo menos 1,5s a mais de duração), o programa agora prefere esse mais longo - mesmo não sendo o mais próximo. "Proximidade" continua sendo a regra geral (não foi abandonada, só ganhou essa exceção limitada). Testado com o cenário exato relatado (pausa de 2,3s perto vs. silêncio de 4,5s um pouco mais distante - agora escolhe o mais longo) e os dois casos de segurança: diferença de duração pequena não troca nada, e um silêncio bem mais longo mas MUITO distante (fora da tolerância) também não troca.

**Limite conhecido**: essa correção só ajuda se o silêncio real já estiver entre os candidatos que o programa detectou (algum dos ~13 métodos precisa ter encontrado ele). Se a fronteira real não tiver sido detectada por nenhum método, não há candidato pra preferir.

### AI. Segunda opinião de duração quando o reataque local falha numa faixa isolada

Investigando junto com o usuário o caso da faixa 6 do Honi Gordon ("Walkin' Out The Door", item AG desta revisão), veio a pergunta: quando a duração do Discogs parece estar errada pra uma faixa específica (o reataque local não acha silêncio real perto o bastante), existe outra fonte pra conferir? A resposta foi sim - o programa já tem acesso a Last.fm, Apple Music e MusicBrainz (usados hoje só como fallback quando o Discogs falha por completo na identificação), e esses mesmos dados já trazem duração por faixa.

Implementado como uma "segunda opinião" pontual, sem enfraquecer a exigência de confirmação por áudio real: quando o reataque local falha numa faixa **isolada** (buraco de 1 faixa só, ancorada por faixas confirmadas dos dois lados) porque nenhum silêncio real foi achado perto da duração do Discogs, busca a duração dessa MESMA faixa (por título, com correspondência aproximada) em Last.fm/Apple Music/MusicBrainz, calcula uma posição alternativa, e tenta a busca de silêncio de novo ali - mas continua exigindo confirmação de áudio real perto dessa nova posição; se a fonte alternativa também não achar nada de verdade, o álbum continua indo pra revisão manual como antes (não é um novo tipo de estimativa cega, é só mudar onde procurar).

Restrito a buracos de 1 faixa isolada, por segurança - não estende esse "achismo" pra buracos maiores, onde o risco de errar em cascata seria maior. Testados: o cenário reconstruído do Honi Gordon (Discogs não acha nada, Apple Music aponta uma duração ~2min maior, e o silêncio real está exatamente lá - confirmado); sem acesso às APIs (comportamento antigo, sem tentar nada a mais); fonte alternativa existe mas também não confirma nada real (continua sem corte); e buraco com mais de 1 faixa (não tenta a segunda opinião, mesmo com a API disponível).

### AJ. Centralização dos limiares/constantes de ajuste

Depois de muitas rodadas ajustando valores numéricos (limiares de voto, distâncias de confiança, margens, janelas de busca) em cima de casos reais, eles estavam espalhados por 3 arquivos e mais de 10 escopos locais diferentes - com pelo menos duas duplicatas de verdade (o mesmo valor definido em dois lugares, onde mudar um sem mudar o outro passaria despercebido).

Reunidos em três classes de configuração, uma por domínio, cada valor mantendo a mesma explicação que tinha no lugar original:
- `CutTuning` (main.py): tudo de corte de faixa - offset de corte no silêncio, filtros básicos, votos mínimos e distâncias de confiança, janelas adaptativas, pontuação combinada (silêncio/energia/proximidade/votos), refinamento fino, reataque local, preferência por silêncio mais longo, parâmetros do RMS mínimo (janela, platô, assimetria/fade), clusterização, limiares do FFmpeg (os 3 paralelos e o de disco inteiro), e a heurística de "faixa suspeitosamente longa".
- `DownloadTuning` (downloader.py): bitrate mínimo padrão e margem de tolerância.
- `IdentificationTuning` (metadata_hunter_voting.py): timeout/retentativas/throttle/backoff das chamadas ao Discogs, máximo de candidatos testados por álbum, limite de chamadas de IA na comparação de faixas.

Nenhuma lógica foi alterada - só o endereço dos valores. Confirmado com a bateria de regressão completa (mesmos resultados numéricos exatos de antes) e com uma verificação específica reproduzindo números reais de log já vistos nesta conversa.

**Nota de processo**: uma substituição em lote gerou uma constante que referenciava a si mesma, o que quebraria o programa na abertura - e o `py_compile` NÃO detectou, porque só confere sintaxe. Só apareceu ao importar o módulo de verdade. A partir daí, toda verificação passou a incluir import real, não só compilação.

### AK. Índice do acervo agora é reconstruído a cada abertura do app

Antes, o `acervo_index.json` era tratado como fonte de verdade: se existisse, era lido como estava, e só era reconstruído quando o arquivo estava ausente ou corrompido. O problema: o disco pode mudar sem o programa saber - pastas apagadas à mão (inclusive de propósito, pra baixar de novo), álbuns movidos, ou copiados de outro computador. O índice virava um retrato antigo, e um álbum apagado continuava sendo pulado como "já está no acervo".

Agora o índice é reconstruído direto das tags ID3 dos MP3s presentes na pasta, a cada abertura do app (e de novo se a pasta de saída mudar nas Configurações). O JSON passa a ser só um cache da sessão.

Detalhe importante de implementação: o método que carrega o índice é chamado várias vezes por sessão (a cada processamento, ao abrir a fila de pendentes), então reconstruir em toda chamada faria varredura repetida à toa. A reconstrução acontece uma vez por sessão - confirmado por um teste que conta as varreduras de disco (exatamente 1, mesmo com 3 chamadas). Álbuns baixados durante a sessão continuam entrando no índice normalmente.

Testados quatro cenários: reconstrução na primeira abertura, arquivo desatualizado corretamente descartado, contagem batendo com a reconstrução original, e o modo antigo (sem forçar) preservado.

**Ressalva conhecida**: em acervos muito grandes, a varredura lê uma tag de MP3 por pasta na abertura - com milhares de álbuns isso pode somar alguns segundos no início. Não otimizei antes de saber se incomoda na prática.

### AL. Modo playlist agora usa os títulos oficiais do Discogs e confere as durações

Numa revisão do app inteiro, achei uma inconsistência real entre os modos: o modo álbum tem toda uma cascata de conferências (e rejeita o disco inteiro se uma faixa ficar sem confirmação de silêncio real), enquanto o modo playlist **buscava** a tracklist do Discogs e depois a descartava - o nome de cada faixa vinha do título do vídeo do YouTube (sujeito ao que o uploader escreveu: "04. Beck - Sexx Laws (Official Audio) HD"), o número da faixa vinha da posição na playlist, e a duração nunca era conferida contra nada.

Implementado `_match_playlist_track()`, que casa cada vídeo com a faixa correspondente da tracklist oficial:
- **Título**: comparação aproximada (a mesma `titles_similar` já usada no resto do programa), depois de limpar ruído comum de título de vídeo. Casou → usa o título oficial do Discogs.
- **Numeração**: passa a vir da posição no Discogs, não da posição na playlist - corrige playlists fora de ordem ou com um vídeo a mais/a menos.
- **Duração**: depois do download, mede a duração real via ffprobe e compara com a informada. Divergência acima da tolerância (10% da faixa, piso de 15s) gera aviso apontando as causas prováveis (vídeo com intro, versão estendida, faixa diferente). Só avisa, não rejeita - mesmo critério de "avisar em vez de descartar" já usado na heurística de faixa suspeitosamente longa.

**Segurança preservada**: vídeo que não casa com nenhuma faixa (bônus, intro, entrevista) ou playlist sem tracklist caem no comportamento antigo (título do vídeo + posição), sempre avisando no log - nunca inventa um nome.

Testados seis cenários com dados reais do Beck - Odelay: título sujo casando com o oficial, numeração corrigida pelo Discogs, duração divergente avisando, duração correta confirmando, vídeo sem correspondência, e playlist sem tracklist.

### AM. Tags de catalogação: ano, artista do álbum e gênero

Faltavam tags padrão que melhoram bastante a organização da biblioteca, mesmo com os dados já em mãos:
- **TDRC (ano)**: o modo álbum já gravava; o modo playlist não.
- **TPE2 (artista do álbum)**: não era gravado em modo nenhum. É o que a maioria dos players usa pra agrupar faixas sob um álbum só - sem ele, um disco com participação ("Fulano feat. Beltrano" numa faixa) se espalha em vários álbuns na biblioteca, mesmo com o TALB igual.
- **TCON (gênero)**: não era nem capturado do Discogs. Agora puxa `styles` (subgêneros, ex: Bop, Post Bop) e `genres` (categorias amplas, ex: Jazz) e junta numa string separada por ';', que é a convenção que a maioria dos players entende como múltiplos gêneros.

**Detalhe que quase passou despercebido**: o modo álbum grava tags via ffmpeg (`-metadata`), NÃO pelo `metadata_manager` - então alterar só o módulo não teria efeito nenhum no caminho principal. Foi preciso adicionar nos dois caminhos, e cada um foi validado separadamente escrevendo num MP3 real e lendo as tags de volta.

### AN. Validação por INTERVALO (em vez de posição) antes de gravar os arquivos

Investigando com o usuário o álbum "Julie Wilson - My Old Flame", que o app entregou como sucesso ("11/11 gaps por silêncio real (100%)") mas tinha três cortes errados de 12 a 26 segundos, a causa raiz apareceu: a validação comparava cada corte com a POSIÇÃO esperada, que é a soma das durações anteriores. Essa soma DERIVA - ela não conta os 2 a 5 segundos de silêncio entre cada par de faixas, que se acumulam ao longo do disco. Num álbum de 12 faixas a previsão chega ao fim uns 30 segundos adiantada.

Adicionada uma segunda validação, por intervalo: entre dois cortes cabe a faixa INTEIRA mais o silêncio, logo o intervalo tem que ser >= duração da faixa, sempre. Intervalo menor é fisicamente impossível - faltou áudio, e ele foi parar no arquivo seguinte. Comparar intervalos não sofre deriva, porque cada faixa é conferida contra a anterior, não contra a soma de todas.

Falta acima de 10s rejeita o disco; entre 4 e 10s avisa e segue (pode ser arredondamento do catálogo). Testado com os dados reais: aponta as faixas 8 e 11 do Julie Wilson e rejeitaria o disco, sem nenhum falso positivo no Nina Simone (que está correto). **Limite conhecido**: quando dois cortes vizinhos estão deslocados na mesma direção, o erro se cancela no intervalo entre eles - foi o caso da faixa 9, que escapa. Dois de três já basta pro disco não passar batido.

### AO. Alinhamento global por intervalos (nova etapa 3.5 da cascata)

O diagnóstico rodado pelo usuário no acervo real mediu os silêncios DENTRO de cada arquivo e provou o ponto decisivo: no Julie Wilson as fronteiras corretas existiam como silêncios de 3,8 a 4,6 segundos, bem claros - o app tinha esses candidatos e escolheu outros, porque os certos estavam longe da previsão (por causa da deriva) e uma pausa dentro da própria música estava mais perto. Ou seja: problema de ESCOLHA, não de detecção.

Implementado `cut_by_interval_alignment()`: em vez de decidir faixa por faixa comparando posições e nunca rever, escolhe o CONJUNTO de cortes que melhor encaixa a sequência inteira de durações, comparando intervalos (programação dinâmica). Duas coisas fazem o trabalho: a restrição física (intervalo >= duração, então candidato cedo demais nem entra em solução nenhuma) e a consistência (o silêncio entre faixas é parecido dentro do mesmo upload, e o valor típico é estimado do próprio disco em vez de fixado).

Entra como etapa 3.5, depois do método com durações e antes de desistir - assim os discos que já saem certos pelos métodos anteriores não passam por ele. Testado: **11/11 cortes corretos no Julie Wilson** (o app original acertava 8/11 nos mesmos candidatos, e estimou sozinho silêncio típico de ~3,0s, batendo com os 2,3-4,0s medidos no disco real); e **recusa o Honi Gordon**, onde o diagnóstico confirmou que a fronteira da faixa 6 não existe como silêncio - não inventa corte quando não há o que achar.

### AP. Chapters do YouTube viram a fonte das POSIÇÕES

Os chapters já eram extraídos, mas só entravam como fallback quando o Discogs falhava por completo - a informação melhor ficava ignorada justamente quando o Discogs funcionava. Eles descrevem ESTE arquivo de áudio (posições reais medidas no próprio upload), então toda a deriva perseguida acima simplesmente não existe ali: não há soma de durações pra acumular erro.

Agora, quando há chapters, as POSIÇÕES vêm deles e os NOMES do Discogs (o uploader escreve "04. Fulano - Musica (HD)"; o Discogs tem o título oficial). Três travas pra não colar nome errado em áudio errado: número de faixas discordando, mais de um quarto das durações divergindo muito, ou ausência de chapters - em qualquer desses casos não mistura e cai no fluxo de sempre. Testados o caso bom e os três de recusa.

### AQ. MusicBrainz: durações em milissegundos apertam as do Discogs

O Discogs guarda duração como "MM:SS", digitada à mão a partir da capa do disco - cada faixa carrega até meio segundo de arredondamento, e num álbum de 12 faixas isso soma vários segundos de incerteza, na mesma ordem de grandeza dos erros de corte. O MusicBrainz guarda em milissegundos, vindo do índice físico do CD. A implementação do MusicBrainz já existia mas truncava os milissegundos pra segundos inteiros, jogando fora exatamente a vantagem que ela tinha.

Corrigido, e adicionado `_refine_durations_with_musicbrainz()`, que substitui as durações do Discogs pelas exatas quando as duas fontes concordam (mesmo número de faixas, títulos parecidos, diferença menor que 2s - acima disso não é arredondamento, são gravações diferentes, e aí o Discogs manda por ter sido quem identificou o álbum). Isso não corrige erro grande de corte, mas aperta a margem e torna o alinhamento mais decisivo em empates. Testados o caso bom e os quatro de recusa, incluindo falha de rede.

**Nota**: entregue junto um programa separado, `diagnostico_cortes.py`, que mede o acervo já cortado (duração real vs oficial, silêncio nas pontas e no meio de cada arquivo) sem alterar nada. Foi ele que produziu os dados que guiaram os itens AN a AQ.

### AR. Corte agora cai no FIM do silêncio, não no começo (silêncios enormes no início das faixas)

Reportado pelo usuário depois de ouvir o acervo: "muitas faixas têm silêncios enormes no começo" e várias "começam atrasadas". Listou faixas de Nina Simone, Julie Wilson, Thunderclap Newman, Helen Humes e Boogaloo Joe Jones.

Isso era um problema DIFERENTE (e mais abrangente) do atropelo que vínhamos atacando. Causa: o corte era posicionado em `início_do_silêncio + 0,4s`. Como o silêncio entre duas faixas tem que ir pra algum lado, ele ia inteiro pro começo da faixa SEGUINTE. Num silêncio de 5s isso deixa 4,6s de nada antes da música entrar; no Boogaloo Joe Jones, cujos silêncios medem de 5 a 12 segundos (cross-validation registrou 12,16s), até 11,8 segundos. Afetava praticamente toda faixa de todo álbum - por isso incomodava mais que o atropelo, que atinge poucas faixas.

O raciocínio original (registrado no código) era evitar cortar tarde demais e comer o início da faixa seguinte, já que o fim do silêncio detectado por limiar de dB pode cair dentro de uma entrada suave. A trava foi mantida, mas virou uma margem pequena em vez de jogar o silêncio todo pra frente: o corte agora cai em `fim_do_silêncio - 0,5s`, com piso de `início + 0,2s` pra silêncios curtíssimos. Toda faixa passa a começar com meio segundo de respirada, e o silêncio sobra pro fim da faixa anterior, que é onde soa natural.

Centralizado num helper único (`posicao_de_corte_no_silencio`) usado pelos quatro pontos que posicionavam corte - antes cada um repetia a mesma conta. Conferido com as durações reais de silêncio dos logs (0,5s / 2s / 5s / 7,6s / 12,2s): em todos, sobra 0,5s antes da música, contra 0,2s a 11,8s antes. Regressão completa passou, incluindo o alinhamento global (11/11 no Julie Wilson) e o offset de silêncio inicial, que não mudou.

### AS. Divergência de duração volta a ser aviso, não rejeição

Pedido do usuário depois de ver três discos de um lote irem pra revisão manual: "quero voltar a ter discos que a duração não bate com Discogs processados automaticamente, sem ir para rejeitados".

Isso inverte uma decisão anterior desta conversa (rigor máximo: sem confirmação, o disco não sai). O raciocínio mudou porque a coleção é dele: um disco entregue com um corte torto é mais útil que disco nenhum, e agora existe o `diagnostico_cortes.py` pra achar os tortos depois, por medição, sem precisar ouvir tudo.

Criada a chave `CutTuning.REJEITAR_QUANDO_DURACAO_DIVERGE` (padrão False). Com ela desligada, as DUAS checagens que comparam com a duração informada viram aviso em vez de rejeição:
- delta grande entre o corte e a posição esperada (dois pontos no código);
- intervalo curto demais entre cortes vizinhos (a validação do item AN).

**O que continua rejeitando**: falta de corte. Quando o programa não acha posição nenhuma pra uma faixa (caso Honi Gordon faixa 6, cuja fronteira não existe como silêncio no áudio), não é questão de rigor - não há o que entregar. Esse caminho ficou intacto, e o teste confirma.

Testado com os números reais do John Hammond (faltas de 6,6s, 16,5s e 14,4s), que era rejeitado e agora é entregue com aviso; que pôr True volta a rejeitar; e que o Honi Gordon continua indo pra revisão. Regressão completa passou.

### AT. Cabeçalhos de seção do Discogs eram contados como faixas

O álbum "Boogaloo Joe Jones ... / My Fire" era rejeitado sempre, com "❌ Faixa 1: sem duração!". A causa não era corte: é uma coletânea de DOIS LPs, e o Discogs põe na tracklist duas linhas que são TÍTULO DE SEÇÃO (o nome de cada LP), não faixas - vêm com `type_='heading'` e duração vazia. O programa as contava como faixas, então "16 faixas" quando o disco real tem 14, e travava na primeira entrada por não ter duração.

A extração agora pula entradas cujo `type_` não é 'track'. Testado com a estrutura real da tracklist desse álbum: 16 entradas viram 14 faixas, todas com duração, primeira faixa = 'The Mindbender'. O disco passa a ser cortado com os nomes de verdade, em vez de rejeitado ou entregue com "Track 1, Track 2...".

Vale registrar que a solução veio dos dados, não de heurística: o usuário sugeriu cortar com nomes parciais ou adivinhar o número de faixas, mas o número certo estava no catálogo o tempo todo - só estava sendo lido errado.

### AU. Validação por intervalo passa a valer no caminho da PROXIMIDADE (onde faltava)

Os mesmos três cortes errados do "Julie Wilson - My Old Flame" sobreviveram a três rodadas de correção. O motivo: a validação por intervalo do item AN existia SÓ dentro de `cut_with_durations`, e esse álbum (como a maioria dos que dão "sucesso") sai por `cut_directly_on_gaps` - a estratégia da PROXIMIDADE, que devolvia os cortes sem conferência nenhuma. O disco nunca chegava na validação.

A conferência virou um método próprio (`_validar_intervalos`) e agora roda também nesse caminho. E não só avisa: quando um corte não comporta a faixa, o alinhamento global é chamado pra tentar um conjunto melhor ANTES de aceitar, e só substitui se de fato reduzir a pior falta.

Testado com os cortes reais do último lote: a validação aponta 26,7s faltando na faixa 8 e 18,2s na faixa 11 - batendo com os 28s e 19s que o usuário mediu de ouvido -, e o alinhamento corrige os três cortes (11/11 corretos, nenhuma falta restante). Sem falso positivo no Nina Simone, que está correto.

### AV. Conserto por alinhamento em TODOS os métodos que usam durações (não só num)

O usuário perguntou se a validação estava em todos os métodos. Não estava, e o log dele provou: no "John Hammond" a validação apontou as faixas 8, 10 e 12 e o disco foi entregue torto do mesmo jeito, porque `cut_with_durations` CONFERIA mas não chamava o conserto - só o caminho da PROXIMIDADE chamava. Inconsistência da implementação anterior (item AU).

Agora os três caminhos que têm durações do Discogs conferem E tentam consertar: PROXIMIDADE, COM DURAÇÕES e MODO HÍBRIDO. O CROSS-VALIDATION continua sem conferência, mas por impossibilidade, não por esquecimento: ele opera com nomes genéricos justamente porque não confia nas durações, então não há com o que comparar o intervalo.

### AW. Gatilho do conserto baixado de 10s para 4s

O "Thunderclap Newman" tinha faltas de 4,7s e 6,0s - abaixo do limite de 10s que disparava o alinhamento, então o conserto nunca era tentado, e o usuário ouvia as faixas 2 e 3 entrando atrasadas. O gatilho passou pro nível da tolerância (`INTERVAL_ALIGNMENT_TRY_SEC = 4.0`): qualquer falta que a validação considere real já vale uma tentativa.

Baixar o gatilho não tem risco de piorar nada, porque o alinhamento só substitui os cortes quando MEDE uma falta menor que a atual; se não melhorar, os originais ficam. O custo é uma passada extra de programação dinâmica em discos com falta pequena.

Confirmado com os números reais do Thunderclap: pior falta 6,0s, que antes não disparava (>= 10s: não) e agora dispara (>= 4s: sim). Regressão completa passou, incluindo os oito casos de referência.

### AX. MusicBrainz: quem decide agora é o áudio medido, não o Discogs

Investigando por que o "Thunderclap Newman" continuava com a faixa 2 entrando atrasada, o diagnóstico mostrou: o arquivo da faixa 2 tem 9,6s a mais que o catálogo, com ZERO silêncio nas duas pontas. Logo, esses 9,6s são áudio - o fim da faixa 1. Mas a faixa 1 "cabia" nos 195s informados. Conclusão: a duração do Discogs para a faixa 1 está curta; a gravação real tem ~204s. Não era erro de escolha de silêncio, era a régua torta.

Isso deveria ser exatamente o caso do refinamento por MusicBrainz (item AQ) - só que ele tinha uma trava que eu mesmo escrevi: só aceitava a duração nova se diferisse MENOS de 2s da do Discogs. Ou seja, eu estava usando o Discogs como juiz para avaliar o Discogs, e limitando a correção a arredondamento. A correção certa (9,6s) seria descartada.

Reescrito: as somas das duas fontes são comparadas contra a DURAÇÃO MEDIDA do arquivo de áudio (ffprobe). Quem chega mais perto do real é a régua melhor, e vale inteira, sem trava por faixa. Isso é medição, não preferência por catálogo. Só troca com vantagem clara (pelo menos 5s melhor E 30% menos erro), e só quando o álbum casa como um todo - mesmo número de faixas e títulos parecidos.

O log também deixou de falhar em silêncio: antes, quando o MusicBrainz não casava, nada aparecia e não havia como saber se ele tinha sido consultado. Agora cada caminho registra o motivo.

Testado com os números reais do Thunderclap (áudio 2878s, Discogs soma 2861s, MusicBrainz 2882s): adota o MusicBrainz e corrige a faixa 1 de 195s para 204,6s. E os quatro casos em que NÃO deve trocar: Discogs já bom, títulos divergentes, áudio não mensurável, MusicBrainz fora do ar.

### AY. Botão "Buscar outra versão" na fila de pendentes

Pedido do usuário, e o log dele justifica: o "Phyllis Diller" foi processado TRÊS vezes seguidas pela fila, falhando de forma idêntica nas três ("DISCO SEM DURAÇÕES - o Discogs não informou durações pra este álbum"). Insistir no mesmo vídeo não leva a lugar nenhum quando a causa está no áudio ou no catálogo; o que resolve é achar outro upload do mesmo disco.

Cada item da fila ganhou um botão que abre a busca de playlists já com **artista e álbum preenchidos**. Os dados saem do Discogs quando houver (que é o dado limpo); sem Discogs, saem do título do vídeo, cortando no primeiro separador e removendo ano e gênero do fim - porque o título cru vem como "Fulano – Disco -1962 (Bop)" e isso estraga a busca.

`_show_playlist_search` passou a aceitar `artista_inicial` e `album_inicial`, ambos opcionais: a lupa do cabeçalho continua abrindo a tela vazia como antes.

Testada a extração com os títulos reais dos logs (Honi Gordon com Discogs, Julie Wilson com artista em dict, Thunderclap com travessão, Freddie North com hífen, Ella Johnson com parênteses sem ano, item vazio) e o fluxo de tela de ponta a ponta: o botão aparece na fila, o clique abre a busca preenchida, e a lupa continua abrindo vazia.

**Limite conhecido**: título sem separador nenhum ("Phyllis Diller   Born To Sing  1968 (...)") cai inteiro no campo artista. Preferi isso a adivinhar onde termina o nome do artista - o usuário edita um campo preenchido, que ainda é melhor que digitar do zero.

**NÃO implementado**: a remoção automática do item após a segunda falha idêntica. Foi discutida junto, mas o usuário pediu só o botão.

### AZ. Item sai da fila depois de falhar duas vezes

Complemento do item AY, agora pedido pelo usuário. Até aqui, item que falhava ficava na fila para sempre: mandava processar, falhava, e podia ser mandado de novo indefinidamente. No log do usuário o "Phyllis Diller" rodou TRÊS vezes seguidas com a mesma mensagem.

Cada item passou a contar suas falhas (`registrar_falha` em pending_queue.py, campo `falhas` persistido em disco). Ao atingir `CutTuning.MAX_FALHAS_NA_FILA` (2), o item sai da fila com uma mensagem que explica o porquê e aponta o botão "Buscar outra versão".

Por que 2 e não 1: a primeira falha pode ser de rede ou de um erro passageiro, e aí a segunda tentativa resolve. A partir da segunda falha idêntica, a causa é o áudio ou o catálogo, e repetir o mesmo vídeo não muda nada.

Testado: o ciclo até a remoção (nunca chega numa terceira rodada); item que falha uma vez e depois dá certo não é punido; item salvo por versão antiga, sem o campo, conta a partir do zero sem quebrar; e a contagem sobrevive a fechar e reabrir o programa.

## REESTRUTURAÇÃO: FILA ÚNICA (em etapas)

### BA. Etapa 1 - o módulo `fila_unica.py` e a correção do número de tentativas

**Correção primeiro**: `MAX_FALHAS_NA_FILA` passou de 2 para 1. O usuário corrigiu meu raciocínio e estava certo - a falha que mandou o disco pra fila JÁ É a primeira tentativa, então processar pela fila é a segunda. Meu argumento de "deixar uma repetição por causa de rede" não se sustentava: rede já tem três tentativas próprias dentro do download.

**A fila**: criado `fila_unica.py`, fonte única da verdade sobre o que fazer e o que já aconteceu. Substitui três coisas que não conversavam entre si: a fila de pendentes, o `channel_progress.txt` e o `DISCOS_REJEITADOS.txt`.

O ganho principal não é organização, é eliminar uma classe de bug. Hoje existem DOIS donos possíveis do processamento (o lote principal e o botão da fila), e o código tem uma trava de concorrência com um comentário contando que os dois já rodaram juntos de verdade, brigando pelo mesmo arquivo. Com um trabalhador único consumindo a fila, deixa de haver dois donos - o bug não é remendado, deixa de ser possível.

Prioridades: disco_unico (0), playlist (1), pendencia (2), canal (3). Item novo não interrompe o álbum em andamento; só entra na frente na próxima volta, como o botão de pausar hoje.

Estados: pendente, processando, feito, rejeitado. Os dois últimos ficam no arquivo como HISTÓRICO - é o que substitui os dois TXT.

Cuidados que valem registro:
- **Gravação atômica** (temporário + `os.replace`): se a fila é a fonte única e é regravada a cada item, uma queda no meio da escrita levaria tudo.
- **Recuperação de queda**: item que ficou 'processando' volta a 'pendente' ao abrir - senão travaria pra sempre num estado que ninguém consome.
- **Arquivo corrompido** não derruba o programa: guarda cópia `.corrompido` e começa limpo.
- **JSON, não TXT**: a fila guarda o `discogs_data` inteiro (dicionário aninhado), que é o que evita reconsultar a API ao reprocessar. Em texto puro isso se perderia.

Testado: 8 casos de comportamento (prioridade, não-interrupção, queda, atomicidade, corrupção, substituição dos dois TXT, duplicata) e desempenho com o volume real do canal do usuário - 3022 itens enfileirados em 0,17s, 56ms por álbum em gravações, retomada instantânea ao reabrir.

**Ainda não ligado ao programa**: o módulo está pronto e testado, mas o laço principal, os botões e os três modos continuam como estavam. Isso é a etapa 2. Nada do comportamento atual foi alterado nesta entrega além do número de tentativas.

### BB. Etapa 2 - trabalhador único, botões que enfileiram, e os dois TXT aposentados

**Os botões PROCESSAR deixaram de iniciar processamento.** Agora ENFILEIRAM. Antes, cada modo abria sua própria thread e o botão da fila de pendentes abria outra: dois donos do mesmo trabalho. Existia uma trava de concorrência no código justamente porque os dois já rodaram juntos de verdade, brigando pelo mesmo arquivo. Com um trabalhador só consumindo a fila, essa situação deixou de ser possível - o bug não foi remendado, foi eliminado.

- Disco único e playlist entram como PRÓXIMOS (prioridade 0 e 1): assumem assim que o álbum em andamento terminar, igual à pausa. Não interrompem nada.
- Canal é listado UMA vez e vai inteiro pro FIM da fila. Antes essa lista vivia só na memória e se perdia ao fechar o programa, obrigando a revarrer o canal na API toda vez.
- Botão de pausa virou "⏸ Pausar fila" / "▶ Retomar fila".
- `DISCOS_REJEITADOS.txt` e `channel_progress.txt` aposentados: o estado 'rejeitado' e o estado 'feito' na própria fila fazem o mesmo papel, e por decisão do usuário nada foi importado dos arquivos antigos.

**Um erro encontrado no meio do caminho, que vale registrar**: o trabalhador morria silenciosamente na pausa. Minha primeira hipótese (o laço saindo pelo `break`) estava errada - instrumentei `proximo()` e ele nunca era chamado de novo. Só ao isolar a pausa num teste separado apareceu a causa real: `NameError: name 'time' is not defined`. O `main.py` nunca importou `time` no topo; as outras funções o importavam localmente, e o meu método não. Foi corrigido com o import no topo. Sem o teste que pausava ANTES de iniciar, isso teria passado.

Testado: prioridade (disco único assume na frente de 4 do canal), cinco cliques seguidos no botão não duplicam nem reprocessam nada, pausa entre álbuns guarda o resto e retoma sem perder nem repetir, falha vira rejeitado com uma tentativa só, e retomada após fechar o programa com item em andamento.

**Limite conhecido**: a lista do canal congela no momento da varredura. Vídeos novos publicados depois não entram sozinhos - falta uma ação de "atualizar canal" que revarra e acrescente só as URLs novas (a deduplicação por URL já cuida do resto). Não foi feito nesta etapa.

### BC. CORREÇÃO CRÍTICA - a etapa 2 rejeitava todos os álbuns sem tentar

O usuário rodou a etapa 2 e 25 álbuns seguidos falharam com `❌ Erro processando item da fila: 'title_artist'`. Nenhum foi processado. Erro meu, e grave.

**Causa**: roteei todos os itens da fila pra `_process_pending_video_item`. Aquela função processa um item que JÁ passou pela identificação - ela lê `item['title_artist']`, `item['title_album']` e `item['year']`, campos produzidos por `_extract_artist` lá dentro de `process_url`, DEPOIS de baixar as informações do vídeo. Um item vindo do canal só tem URL e título. Dava `KeyError` em todos.

Eu supus o formato do item em vez de ler quais chaves a função exigia. Os testes da etapa 2 não pegaram isso porque substituí `_process_pending_video_item` por uma função falsa - testei o trabalhador, não o encaixe dele com o pipeline real.

**Correção**: o despacho agora usa o pipeline COMPLETO - `process_url(url, guest_mode=True)` pra vídeo/canal/pendência e `process_playlists(url, guest_mode=True)` pra playlist. `guest_mode=True` faz essas funções mexerem em `self.pending_processing` em vez de `self.processing`/`process_button`, que pertencem ao trabalhador.

**Segundo erro, encontrado junto**: `process_url` não devolve valor (tem dezenas de `return` de saída antecipada), então o trabalhador leria `None` e marcaria como rejeitado TUDO, inclusive os que dessem certo. Resolvido com uma marca (`self._fila_item_ok`) posta no ponto de conclusão do álbum, que é o único lugar confiável.

Testado com um `process_url` simulado que conclui alguns e falha outros: os 4 itens foram tentados, 2 viraram 'feito' e 2 'rejeitado', os certos em cada grupo.

### BD. Painel da fila - o botão que não retomava nada

O usuário abriu o programa com ~3000 itens na fila e clicou em "Retomar fila". O log escreveu "Retomando processamento..." e NADA aconteceu. Dois problemas:

1. O trabalhador só nascia no clique de Processar. Com a fila salva em disco mas nenhum trabalhador vivo, o botão só alternava uma variável.
2. O log MENTIA. Escrever "retomando" sem retomar é pior que não dizer nada - o usuário fica esperando.

**Botão contextual, separado por estado** (o mesmo botão fazendo coisas diferentes no mesmo estado irrita):
- fila rodando → pausa/retoma na hora, como antes
- fila parada → abre o painel, e o rótulo vira "📋 Fila (N)" mostrando quantos aguardam

**Painel** com contagens primeiro (decidir apagar 3000 itens sem ver quantos são é decidir no escuro), ação principal destacada e separada das destrutivas, e as destrutivas em DUAS, porque são intenções diferentes:
- "Limpar histórico (N)" - tira feitos/rejeitados, mantém pendentes. É a de uso frequente.
- "Apagar a fila" - rara, em vermelho, com confirmação que diz o que vai acontecer, inclusive que o canal será revarrido do zero e que os áudios em disco NÃO são apagados.

Juntas numa só, a útil carregaria o risco da perigosa.

Também: aviso no log ao abrir o programa quando há fila guardada. Sem ele o usuário abre, vê tudo parado e não tem pista do trabalho esperando - foi exatamente o que aconteceu.

Testado: rótulo com a contagem, clique abrindo o painel (sem pausar nada), limpar histórico preservando os 2975 pendentes, apagar exigindo confirmação e respeitando a recusa, e o botão pausando direto quando a fila está rodando.

### BE. Três correções na fila + renomeação para DiscoFácil

**1. O laço antigo voltou a rodar junto com a fila (os dois donos de novo).** O log do usuário mostrou `Processando canal:` com formato `ÁLBUM 1/3027` acontecendo em paralelo com a fila. Causa: o trabalhador chamava `process_url`, e essa função decide o que fazer lendo o BOTÃO DE RÁDIO da tela (`self.process_type`). Com "Canal Inteiro" marcado, ela chamava `process_channel` pra CADA item da fila, e o laço antigo revarria o canal inteiro. Corrigido: o trabalhador vai direto pra `process_single_video`. O tipo do trabalho é do ITEM, não da tela.

**2. Listagem do canal disparava duas vezes.** Dois cliques em Processar abriam duas varreduras simultâneas (visível no log: a listagem e as mensagens duplicadas). Adicionada trava `_listando_canal`.

**3. Pausar agora abre o painel** - o usuário levantou que, com a fila rodando, o botão estava ocupado pausando e não havia como ver as contagens ou limpar o histórico. Agora a pausa é a porta de entrada do painel. O botão "Retomar" do painel distingue os dois casos: trabalhador vivo (só tira a pausa) e trabalhador morto (cria um novo), testados separadamente.

**Renomeação**: o programa passou a se chamar **DiscoFácil** - título da janela, cabeçalho e diálogo de ajuda. O nome da classe interna (`FullTracksDownloaderGUI`) e os nomes dos arquivos NÃO foram alterados, porque seria renomeação mecânica de risco sem ganho. No `build_exe.bat` e no `.spec` o executável virou `DiscoFacil` SEM acento, de propósito: arquivo `.bat` rodando no console do Windows costuma quebrar com caracteres fora do ASCII.

### BF. Botão PROCESSAR travado durante o trabalho + validação do tipo de URL

Pedido do usuário ("melhor desabilitar todos os botões PROCESSAR enquanto estiver trabalhando"), e o log dele mostrou por quê - com um problema pior escondido junto.

**O que o log revelou**: a trava contra clique duplo funcionou ("⏳ Já estou listando esse canal"), mas logo depois apareceu "➕ Na fila como próximo: .../@discosredondosfullalbum". A URL do CANAL entrou na fila como **disco único**, e o trabalhador tentou processar um canal inteiro como se fosse um álbum.

**Duas correções**:

1. **Botão desabilitado enquanto há trabalho** - listando canal, fila rodando, ou trabalho avulso. Vira "▶ Processando…". Continua liberado com a fila PAUSADA, que é justamente quando o usuário quer enfileirar algo novo pra assumir depois. Botão desabilitado é mais honesto que aceitar o clique e dar erro lá na frente.

2. **Validação do tipo de URL no modo Vídeo Único**: URL de canal (`/@`, `/channel/`, `/c/`, `/user/`) ou de playlist (`list=` sem `watch?v=`) é barrada com uma mensagem que diz qual modo usar. Barrar na entrada é melhor que descobrir depois, com o trabalhador já tentando baixar um canal como álbum.

Testado: as três formas de URL de canal e a de playlist barradas sem entrar na fila, URL de vídeo passando normal, e o botão travando/destravando nos cinco estados (parado, listando, fila rodando, fila pausada, terminou).

### BG. O bug do Rufus Thomas + o segundo dono que voltou

Dois defeitos encontrados no log real do usuário, ambos meus.

**1. Álbuns que davam CERTO eram registrados como rejeitados.** O "Rufus Thomas" saiu cortado, com as 10 faixas e as tags gravadas, e logo depois o log dizia "🚫 Não será repetido". Causa: `_download_and_process` tem DUAS saídas de sucesso e eu tinha posto a marca numa só. O álbum saiu pela outra.

Corrigido invertendo a lógica, o que resolve de raiz em vez de remendar: **sucesso é o padrão, a falha é que precisa se declarar**. Em vez de eu ter que achar toda saída boa (e errar), o programa declara a falha onde ela realmente acontece - ao mandar o álbum pra fila de pendências, que é a definição que o próprio app usa pra "não deu certo". Feito envolvendo `pending_queue.add` uma única vez, então qualquer caminho que mande um álbum pra pendências marca a falha - inclusive caminhos futuros, sem ninguém precisar lembrar.

**2. O segundo dono voltou pela tela de pendências.** O log mostrou "▶ Processando pendente: Art Farmer" rodando ao mesmo tempo que o trabalhador da fila. A tela de pendências abria sua própria thread - era a mesma classe de bug que a fila veio eliminar, entrando por uma porta que eu não fechei. (A trava com `showwarning` que existia ali era o remendo que existia justamente porque os dois donos existiam.)

Agora ela ENFILEIRA como tipo 'pendencia' (prioridade 2: depois de disco único e playlist, antes do canal) e quem processa é o trabalhador único. O item inteiro vai junto no campo `pendencia_item`, porque pendência já passou pela identificação e carrega campos (`title_artist`, `title_album`, `year`) que o processador exige - foi exatamente o que faltou na etapa 2 e causou o KeyError.

**Tela de pesquisa**: verificada, já estava correta. Ela só preenche o campo e troca de modo; quem processa é o botão, que enfileira.

Testado: álbum bem-sucedido virando 'feito' mesmo pela saída que não tinha marca; álbum que vai pra pendências virando 'rejeitado'; a tela de pendências enfileirando 3 itens sem abrir thread própria; o trabalhador processando pendências com o item completo (sem KeyError); a prioridade disco_unico → pendencia → canal; e a tela de pesquisa intacta.

### BH. Fila acessível, botão liberado, tela de enfileiramento - e a constante fantasma

**Bug independente, o mais grave da rodada**: `CutTuning.LOCAL_REATTACK_NO_ANCHOR_WINDOW_SEC` era USADA no código e nunca foi DEFINIDA. O "Wally Richardson" morreu com `type object 'CutTuning' has no attribute ...` e foi rejeitado sem que o erro tivesse qualquer relação com o áudio dele - qualquer álbum que chegasse no reataque local sem âncora seguinte caía igual. Definida como 150.0 (mesma janela do reataque com âncora dos dois lados; o achado ainda passa pelo filtro de distância máxima). Varri o arquivo atrás de outras constantes usadas sem definição: não há mais nenhuma.

**Erro meu da rodada anterior, corrigido**: eu havia travado o botão Processar durante todo o trabalho, seguindo ao pé da letra o pedido de "desabilitar enquanto estiver processando". Isso destruiu justamente o que a fila existe pra fazer - ENFILEIRAR enquanto algo roda -, e o usuário não conseguia mandar álbuns da pesquisa nem das pendências pra fila. Eu devia ter apontado a contradição em vez de obedecer literalmente. Agora o botão só trava durante a varredura do canal, que é o único clique que faz besteira de verdade.

**Fila com entrada própria no cabeçalho**, ao lado de "Buscar Playlists", funcionando a qualquer momento. Amarrar o painel ao botão de pausa foi erro meu: com a fila rodando, o botão estava ocupado pausando. O botão de pausa voltou a só pausar e retomar.

**A tela da fila virou tela de enfileiramento**: abre sozinha a cada vez que algo é enfileirado, pra o usuário VER o item entrando (antes o único retorno era uma linha no log, e parecia que nada acontecia). Lista os itens com marcação individual, "Marcar todos" e "Tirar da lista" - que juntos já cobrem o apagar tudo, então não há botão destrutivo separado. Sem confirmação pra enfileirar, porque a ação não é arriscada.

**"Limpar histórico" saiu.** O usuário disse que o nome não explicava nada e tinha razão.

**Detalhe de desempenho**: a lista mostra no máximo 60 itens, com o total no resumo. Com ~3000 na fila, criar um widget por item congelaria a janela.

### BI. A causa única por trás de três sintomas: item existente não era promovido

O usuário relatou três coisas: enfileirar parou de funcionar, ao retomar volta o canal em vez do que foi enfileirado, e a tela da fila para de mostrar os itens. O `fila.json` que ele mandou provou que era UMA causa só.

**A raiz**: em `FilaUnica.adicionar`, quando a URL já estava na fila, eu devolvia o item existente SEM MEXER EM NADA. Consequências medidas no arquivo real:

- O disco único que ele enfileirou 3 vezes estava lá como `tipo=canal, prioridade=3, ordem=3027`. A URL já existia na fila vinda do canal, então enfileirar não moveu nada - o item seguiu na posição 3027 entre 3000. O log escrevia "na fila como próximo" e **mentia**. Por isso ele clicou de novo, e de novo.
- As duas pendências ficaram com `prioridade=3` (a do canal, herdada) e **sem o campo `pendencia_item`** - o ramo de reabertura tinha um dict fixo que descartava os extras. Sem esse campo o trabalhador devolve falha imediata: o log mostra o cabeçalho "FILA [pendencia]" seguido direto de "Não será repetido", sem nenhuma tentativa.
- A tela "parar de mostrar itens" era a mesma coisa: ela lista os 60 primeiros pendentes por prioridade, e como nada era promovido, mostrava sempre os mesmos itens do canal.

O Ronnie Von funcionou porque aquela playlist era URL nova - único caso que não passou pelo ramo de reabertura.

**Correção**: o pedido novo manda. Tipo, prioridade e extras são atualizados, e o item vai pro fim da ordem do seu tipo - que é o que "como próximo" precisa significar pra ser verdade. Item fechado sem `reabrir_se_fechado` continua recusado.

**Tela de pendências não exige mais pausa**: a linha `if (self.processing ...) : process_btn.config(state='disabled')` era sobra da época em que essa tela processava por conta própria. Ela só ENFILEIRA agora, e enfileirar é sempre seguro. O botão virou "➕ Enfileirar selecionados".

Testado com o cenário exato do arquivo real: disco único enterrado na posição 2501 entre 3000 assume a frente; pendência reaberta volta com prioridade 2, falhas zeradas e o item completo; a ordem disco_unico → playlist → pendencia → canal se mantém; item já concluído não volta sozinho; e enfileirar duas vezes não duplica.

### BJ. Lista de pendências sincronizada + bitrate mínimo 80 kbps

**O que o usuário viu**: o "Yusef Lateef" foi cortado com sucesso (8 faixas, tags gravadas) e continuou na lista de pendências. O "James Brown" foi rejeitado de vez e também ficou lá. O `fila_pendentes.json` dele confirma os dois.

**Causa**: a remoção da lista de pendências só existia dentro do `_run()` da tela, que virou código morto quando ela passou a só enfileirar (item BG). O trabalhador nunca aprendeu a fazer isso.

**Correção**, com a distinção que importa:
- Álbum que **conclui** sai da lista, venha de onde vier - inclusive quando o canal processa com sucesso uma URL que estava pendente de uma falha antiga.
- Álbum que **veio das pendências e falhou de novo** sai também: já teve a segunda chance.
- Álbum do canal que **falhou agora** FICA. Ele acabou de ser adicionado à lista pelo próprio programa; removê-lo ali desfaria o que acabara de ser feito. Este é o caso perigoso e tem teste próprio.

**Bitrate mínimo: 128 → 80 kbps** (`config.py` e `DownloadTuning.DEFAULT_MIN_BITRATE_KBPS`). No log do usuário, três álbuns foram descartados por 82, 90 e 105 kbps - todos passam agora.

**Varredura por outros defeitos**: nenhuma constante usada sem definição nas três classes de ajuste; recuperação de queda funcionando; e removido o campo interno `_promovido`, que eu estava gravando no JSON sem necessidade (é informação do momento, não estado do item). O `_run()` da tela de pendências continua no arquivo como código morto - inofensivo, mas nunca mais chamado.

### BK. Revisão dos textos de ajuda - e os dois arquivos que ainda estavam sendo criados

Revisão pedida depois que um texto de ajuda apareceu desatualizado. Encontrei mais do que texto.

**O mais sério**: o `DISCOS_REJEITADOS.txt` continuava sendo ESCRITO em dois lugares e LIDO em um terceiro. Quando o usuário mandou aposentá-lo, eu troquei só as mensagens do log e deixei as escritas de pé - o arquivo seguia sendo criado na pasta dele. Removidas as duas escritas e a leitura (que pulava discos comparando o título contra linhas do arquivo; quem faz esse papel agora é a fila, comparando por URL, que é exato).

O `.channel_progress.txt` só é criado dentro de `process_channel`, que é chamado apenas por `process_url` - e `process_url` não tem mais nenhum chamador desde que o trabalhador passou a usar `process_single_video`. Ou seja, inalcançável: o arquivo nunca mais é criado. Deixei o código como está em vez de operar uma função grande e morta.

**Textos de ajuda atualizados**:
- "Como funciona": não mencionava a FILA, que hoje é o centro do programa. Acrescentado como seção própria (prioridades, e que fechar o programa não perde nada). A parte de pendentes falava em "decide se baixa ou descarta"; agora diz "Enfileirar selecionados - não precisa pausar nada".
- "Modos de processamento": dizia que o canal "processa automaticamente todos os vídeos". Agora explica que ele ENFILEIRA, que dá pra pausar e fechar, e como pegar vídeos novos depois.
- "URLs das playlists": dizia "processadas uma de cada vez, em sequência". Agora explica que entram na fila com prioridade, na frente do canal.
- "Bitrate mínimo": dizia "Padrão: 128 kbps" (corrigido para 80 na rodada anterior).

Verificados os 9 botões de ajuda (4 na tela principal, 5 nas Configurações): todos abrem sem erro.

### BL. Steely Dan, playlists acumuladas e revisão de interface

**O bug do Steely Dan** (confirmado pelo usuário: o arquivo estava na pasta temporária). Uma PLAYLIST que falha vai pra fila de pendências com `source_type: 'playlist'`, mas o trabalhador mandava TODA pendência pro `_process_pending_video_item`, ignorando esse campo. A playlist era tratada como vídeo único: baixava de verdade e o programa dizia "Arquivo baixado não encontrado no disco", porque procurava um arquivo único onde havia uma playlist. Três tentativas, três vezes o mesmo engano. Agora despacha por `source_type`.

**Pesquisa acumula playlists** (pedido do usuário). Antes, "Usar selecionadas" APAGAVA a caixa e FECHAVA a busca - procurar um segundo disco jogava fora o primeiro. Agora acrescenta, ignora repetidas, mostra o total e mantém a janela aberta pra continuar buscando. O botão virou "➕ Adicionar à lista", que descreve o que ele faz.

**Revisão de telas e botões** - quatro incoerências encontradas numa auditoria automática de todos os botões:

1. O botão de pausa NASCIA escrito "⏸ Pausar" com a fila vazia - mentindo sobre o estado. Agora nasce "▶ Retomar fila" desabilitado e vira "▶ Retomar (N)" quando há fila.
2. "Resetar progresso salvo", nas Configurações, mexia no `.channel_progress.txt` e `.playlist_progress.txt`, que não existem mais. Era um botão que não fazia nada. Removido; quem zera o andamento agora é a tela da Fila (Marcar todos + Tirar da lista).
3. Esc não fechava Configurações nem Buscar Playlists, só a Fila. Padronizado nas três.
4. O rótulo do botão da busca prometia "Usar na Playlist Completa" quando o comportamento agora é acumular.

### BM. Fluxo e usabilidade: o usuário não sabia em que pé estava

Revisão de usabilidade pedida pelo usuário. A falha maior não era visual: **não existia NENHUMA indicação de progresso**. Com ~2.800 álbuns na fila, cada um levando minutos, a única resposta pra "está funcionando? falta muito?" era ler o log rolando linha por linha.

**Linha de situação** acima do log, respondendo de relance as três perguntas que importam: o que está baixando AGORA, a posição no lote, e como está indo.
`▶ Baixando: Julie Wilson - My Old Flame · 3 de 2815 · 168 pronto(s) · 47 recusado(s) · 2600 na fila`
Muda para "⏸ Pausado", "Fila parada" ou "Nada na fila" conforme o estado.

**Rótulos que dizem o que o clique FAZ**:
- "Processar" (vago) virou "➕ Enfileirar álbum" / "➕ Enfileirar canal inteiro" / "➕ Enfileirar playlists", conforme o modo. Importa porque com canal o clique significa varrer milhares de vídeos.
- "Pendentes" virou "⏳ Precisam de você (N)", com a contagem. O nome antigo não dizia o papel da lista; agora a distinção fica clara: Fila = o que o programa faz sozinho; esta = o que depende de uma decisão sua.

**Um erro meu, pego pelo próprio teste**: a contagem mostrava "3 de 2" porque o álbum em processamento não entrava em nenhum dos totais. Corrigido incluindo o estado 'processando'.

**Nota sobre o teste**: a atualização usa `root.after`, que é a forma correta de tocar na interface a partir da thread do trabalhador. Meu primeiro teste dizia que não funcionava; investigando, o problema era o teste - sem `mainloop` rodando, o Tk recusa chamadas de outra thread. Escrevi um teste com `mainloop` de verdade, que reproduz a condição do programa rodando, e aí passou. Quase troquei código correto por causa de um teste inadequado.

### BN. Playlist pendente anunciava sucesso sem baixar nada

No log do usuário, as 7 faixas do "Steely Dan - Aja" falharam por bitrate (57 kbps contra os 80 configurados) e o programa respondeu **"🧹 Saiu da lista de pendências (concluído)"**, deixando a pasta vazia em disco.

**Causa**: `_process_pending_playlist_item` chamava `process_playlist_song` para cada faixa, **descartava o retorno** e devolvia `True` incondicionalmente. O caminho normal de playlist (`process_playlists`) já fazia isso certo - parava na primeira falha, apagava a pasta parcial e mandava pra pendências. Era esta cópia que estava incompleta.

Duas consequências, ambas ruins: o programa dizia ter feito o que não fez (e o item saía da lista de pendências por isso), e sujava o acervo com uma pasta vazia.

**Correção**: o laço agora confere cada faixa, para na primeira falha (não insiste nas restantes - se o álbum vai ficar incompleto, baixar o resto é desperdício), apaga a pasta parcial e devolve `False`. O item volta pro histórico como rejeitado, que é a verdade.

Testado com os três cenários: todas as faixas falhando (o caso real do usuário), uma falha no meio do álbum, e o caso bom - que mantém a pasta e os arquivos.

### BO. A causa real dos bitrates baixos: estávamos pedindo o áudio errado

O usuário insistiu que não havia nada de errado com a playlist do "Steely Dan - Aja". Ele tinha razão, e eu estava tratando o sintoma. Relendo o log com atenção, a pista estava espalhada por TODAS as rodadas anteriores: 57, 62, 82, 90, 105 kbps. O YouTube serve 128 kbps ou mais para música. Receber isso sistematicamente não é azar com uploads ruins - é o programa não pedindo o melhor áudio.

**Duas causas no seletor do yt-dlp**:

1. `bestaudio[ext=m4a]` vinha PRIMEIRO, com o comentário "m4a (mais rápido)". Isso descarta o opus antes de comparar, e o opus costuma ser o formato de maior bitrate do YouTube. Trocar qualidade de origem por velocidade de conversão é mau negócio num programa feito pra arquivar disco.

2. `player_client: ['android', 'web']` - o cliente android devolve um conjunto reduzido de formatos, às vezes só os ruins. O `Nonekbps` que aparecia no log era exatamente isso: o yt-dlp não recebia o bitrate para ordenar, e sem saber ordenar pegava qualquer um.

**Correção**: `'format': 'bestaudio/best'` sem preferir container, `format_sort: ['abr','asr','size']` ordenando explicitamente por bitrate, e `player_client: ['web','android']` com o web na frente, que devolve a lista completa. O log agora mostra `🎧 Áudio de origem: Xkbps` pra dar como conferir.

**Terceiro defeito, que o log denunciava**: "FALHA APÓS 3 TENTATIVAS" para um motivo que nunca mudaria. O downloader já marcava `last_error_retryable = False` para bitrate baixo (é característica da fonte), e o caminho de playlist ignorava essa marca - três downloads jogados fora por faixa. Agora para na primeira.

**Limite honesto**: não consigo alcançar o YouTube daqui, então verifiquei que o yt-dlp aceita as opções novas (sintaxe válida, versão 2026.08.19), mas NÃO pude confirmar que o bitrate sobe de verdade. Isso só o primeiro download real mostra - e a linha `🎧 Áudio de origem` existe pra isso.

### BP. A taxa do MP3 agora acompanha a fonte

O usuário notou que o bitrate que o programa reporta pra fonte não bate com o do arquivo salvo. Não era erro de medição - eram grandezas diferentes, e a regra de conversão estava errada nas DUAS direções.

**Medido aqui, com áudio de espectro rico** (a primeira tentativa usou onda senoidal, que comprime a quase nada e não revelava nada):

| fonte | regra antiga | efeito |
|-------|--------------|--------|
| 58k | 82k | inchava 1,4x - 40% mais disco sem ganhar nada |
| 129k | 83k | **perdia** qualidade |
| 201k | 90k | perdia muito |

A regra antiga escolhia entre três qualidades VBR fixas por faixa de bitrate, e o resultado não acompanhava a origem.

**Agora** `taxa_mp3_para()` escolhe a taxa de MP3 mais próxima da fonte: 57k→56k, 128k→128k, 200k→192k. Sem fonte conhecida, 192k. Verificado: os três casos acompanham (razão entre 0,85 e 1,15).

**Medição da fonte corrigida junto** (`medir_bitrate_fonte`): testei contra arquivos de bitrate conhecido e descobri que em m4a o contêiner acerta (erro de 1k), mas em **opus o contêiner reporta alto demais** - um opus de 128k é relatado como 145k - e o bitrate por stream nem existe. Como o programa passou a preferir opus (item BO), usar o contêiner faria o filtro de qualidade comparar maçã com laranja. Agora prefere o stream de áudio e, quando ele não existe, desconta a gordura medida.

**Ressalva honesta registrada no código**: MP3 é menos eficiente que AAC e opus, então um MP3 na mesma taxa da fonte soa um pouco pior que o original. Compensar exigiria encodar acima - exatamente o que o usuário não quer.

### BQ. O segundo caminho de download + diagnóstico de formatos + confiança configurável

**O bitrate continuava 57k depois da minha correção. Descobri por quê, e eram duas coisas:**

1. **`prefer_free_formats: False`** - essa opção manda o yt-dlp PREFERIR m4a em vez de opus, anulando a ordenação por bitrate que eu tinha acabado de instalar. Era por isso que o log seguia mostrando `mp4a.40.2` mesmo depois da mudança: a preferência por container vencia a qualidade.

2. **Existia um SEGUNDO caminho de download** (a tentativa alternativa) que ficou com o seletor antigo `bestaudio[ext=m4a]/...`. Eu tinha corrigido só o primeiro. Os dois agora usam `bestaudio/best` com `format_sort` por bitrate.

**Diagnóstico, porque já errei duas vezes às cegas**: quando um áudio é rejeitado por bitrate, o programa agora LISTA os formatos de áudio que o YouTube oferece pra aquele vídeo, do melhor pro pior. Isso encerra a dúvida na próxima execução: se a lista mostrar 128k e nós baixarmos 57k, o problema é a escolha; se o melhor da lista for 57k, o vídeo é ruim mesmo e nenhuma mudança no seletor resolve. Daqui não alcanço o YouTube, então essa é a forma honesta de decidir - com dado, não com palpite.

**Confiança mínima agora é configurável** (pedido do usuário). Estava fixa em 80% escondida no código; virou campo nas Configurações, com ajuda explicando o efeito. Com **0%** nada vai pra pendências por falta de confiança: o programa baixa sempre, com o melhor palpite do Discogs.

Detalhe de implementação que vale registro: 0 é um valor LEGÍTIMO aqui, então a validação testa a faixa (0 a 100) em vez de usar `if not valor` - que trataria 0 como "vazio" e silenciosamente voltaria pra 80.

### BR. O diagnóstico respondeu: era a restrição de player_client

O diagnóstico do item BQ fez o que foi feito pra fazer - encerrou a dúvida com dado em vez de palpite. No log do usuário:

```
🎧 Áudio de origem: 62kbps   →  recusado
📋 Áudios que o YouTube oferece pra este vídeo:
   • 138kbps  opus (webm, id 251)
   • 129kbps  mp4a.40.2 (m4a, id 140)
   • 53kbps   opus (webm, id 249)
   • 49kbps   mp4a.40.5 (m4a, id 139)
```

**O áudio bom existia** (138k e 129k) e nós baixamos 62k. E a comparação revelou a causa: o diagnóstico lista os formatos SEM forçar cliente nenhum e enxergou os quatro; o download forçava `player_client: ['web','android']` e recebia uma lista pobre - daí o "bitrate não informado" que aparecia junto.

Ou seja: minhas duas correções anteriores (format_sort, prefer_free_formats) estavam certas mas eram inúteis, porque a lista que chegava até elas já vinha capada. Removida a restrição de cliente; o yt-dlp escolhe sozinho, que é o que ele faz de melhor e o que se atualiza a cada versão conforme o YouTube muda.

**A mensagem que enganou o usuário**: a lista de pendências dizia "Faixa X falhou no download", e ele entendeu que a música não tinha sido encontrada - mas ela estava lá, e o que houve foi o filtro de bitrate recusando. Agora a mensagem traz o motivo real ("recusada: Bitrate 62kbps abaixo do mínimo..."). Mensagem que esconde a causa faz procurar o problema no lugar errado.

### BS. Os dois problemas eram opostos: formatos bons x acesso bloqueado

**Erro meu, direto**: remover o `player_client` fixo (item BR) resolveu o bitrate baixo e QUEBROU o download. O YouTube passou a responder `403 Forbidden` e "Sign in to confirm you're not a bot". O cliente android estava ali por um motivo que eu não conhecia quando o removi.

Os dois problemas são reais e puxam para lados contrários: sem forçar cliente, a lista de formatos é boa mas o acesso é barrado; com o android, o acesso passa mas a lista é pobre.

**A saída não é escolher um lado, é tentar na ordem certa.** Primeiro sem forçar cliente (formatos melhores); se o YouTube barrar - detectado por `_parece_bloqueio_do_youtube()`, que reconhece 403 e a checagem de robô - repete com o android. Melhor um álbum em 62kbps que nenhum álbum.

A alternância só dispara para bloqueio, não para erro do vídeo (privado, removido): nesses casos repetir com outro cliente não mudaria nada.

**O texto da tela de pendências estava errado.** Dizia que os itens vinham de "álbuns que o Discogs não encontrou ou encontrou com baixa confiança" - mas os dois do usuário estavam lá por falha de DOWNLOAD. A explicação mandava procurar o problema no lugar errado. Agora nomeia os três motivos reais (Discogs não achou, achou com pouca confiança, download falhou) e aponta pra linha vermelha de cada item, que traz a causa daquele. Também corrigido "clicar em Processar", que era o nome antigo do botão - hoje é "Enfileirar selecionados".

### BT. A segunda playlist e os cookies do navegador

**O que aconteceu com a segunda playlist**: defeito meu na correção anterior. A marca `_ja_tentou_android` era zerada só no `__init__`, então valia pro programa INTEIRO - depois que a primeira faixa usava o cliente alternativo, nenhuma outra podia usar. No log: a primeira playlist teve o "↻ repetindo com outro cliente" e baixou; a segunda levou três 403 seguidos sem nem tentar. Agora zera a cada download.

**Cookies do navegador** (pedido do usuário, que escolheu qualidade sobre quantidade). Resolve o problema na raiz: com a sessão do navegador, o YouTube não trata o programa como robô, não bloqueia, e aí não é preciso o cliente android - e sem ele a lista de formatos vem completa, com os 138kbps que o diagnóstico mostrou existir.

Virou um campo nas Configurações (lista com chrome, firefox, edge, brave, opera, vivaldi, chromium, ou "nenhum"). A ajuda explica o porquê e as ressalvas: o navegador precisa estar instalado e logado, e no Windows o Chrome criptografa os cookies (DPAPI) - se a leitura falhar, o programa avisa e segue sem eles em vez de travar. O código de queda suave pra esse caso já existia.

Testado: a marca zera antes de cada download; os cookies só entram nas opções quando um navegador é escolhido; o campo aparece e guarda a escolha.

**Não verificável daqui**: se os cookies realmente liberam os 138kbps. Daqui não alcanço o YouTube nem tenho navegador logado. A linha `🎧 Áudio de origem` no log dá a resposta na primeira execução.

### BU. A queda suave dos cookies que não caía suave

O usuário escolheu Edge e o download falhou três vezes com `Could not copy Chrome cookie database` (o Edge é Chromium, por isso o yt-dlp fala em "Chrome"). O banco de cookies fica travado enquanto o navegador está aberto.

**Erro meu**: eu tinha prometido que, se a leitura falhasse, o programa seguiria sem cookies. Só que a detecção reconhecia apenas `'DPAPI'` e `'decrypt'` - e este erro não contém nenhum dos dois. A queda suave simplesmente não aconteceu.

Agora `_parece_problema_de_cookies()` reconhece a família toda: cópia do banco travado, criptografia, keyring, permissão. Testada contra seis mensagens reais, incluindo as que NÃO devem casar (403, vídeo indisponível).

**Cadeia completa de tentativas**, cada degrau trocando um pouco de qualidade por chance de funcionar:
1. **Com cookies** - melhor qualidade, exige navegador fechado
2. **Sem cookies** - se a leitura falhar
3. **Cliente android** - se o YouTube barrar por 403; passa pelo bloqueio mas só oferece formatos piores

Só desiste quando os três falham. Antes, cada degrau existia isolado e não levava ao seguinte.

**Recado útil no log** em vez de só o erro cru: explica que o navegador trava o arquivo e sugere fechá-lo ou usar o Firefox, que não trava.

### BV. Qualidade é essencial: parar de aceitar o primeiro download que funciona

O usuário baixou o álbum com mínimo de 60kbps e ficou com MP3s de **48kbps**, de um vídeo onde o YouTube oferece 138kbps. Dois erros somados, os dois meus.

**1. A conversão arredondava PRA BAIXO.** `taxa_mp3_para()` pegava a taxa mais próxima, e "mais próxima" às vezes é abaixo: fonte de 53k virava MP3 de 48k. Pior, `medir_bitrate_fonte()` descontava 12% do valor do contêiner (overhead que medi em testes), então uma fonte de 53k era lida como 46k e virava 48k. Os dois efeitos empurravam pra baixo.

Corrigido: desconto removido, e a regra passou a ser "nunca abaixo da fonte", com tolerância de 5% pra não inflar à toa (129k vira 128k, não 160k). Numa recompressão, perder é definitivo; sobrar custa alguns KB.

**2. O programa aceitava o primeiro download que funcionasse.** Num vídeo que oferece 138kbps, isso trazia 62kbps. Com "qualidade é essencial", essa é a política errada.

Agora `baixar_melhor_audio()` consulta quanto o YouTube anuncia de melhor (o ALVO), percorre os clientes do que dá melhor áudio pro que apenas funciona (`[None, 'tv', 'web_safari', 'mweb', 'android']`) e PARA no primeiro que chega a 90% do alvo. O android fica por último porque quase sempre passa e quase sempre em baixa qualidade.

No caso bom custa um download só. Quando os primeiros falham, tenta os seguintes e fica com o melhor que conseguiu - nunca volta de mãos vazias só por não achar o ideal.

Testado com o cenário do usuário simulado (vídeo oferecendo 138k, clientes entregando coisas diferentes): para no segundo cliente com 138kbps e nem chega no android. E o caso ruim, em que só o android funciona: ainda baixa, em 62kbps.

**Não verificável daqui**: se algum desses clientes de fato passa pelo bloqueio no YouTube real. A lista vem do comportamento conhecido do yt-dlp, mas só a execução mostra. O log agora diz qual cliente venceu e com quantos kbps.

### BW. Cookies: descobrir o navegador sozinho, uma vez e depois de cada falha

Ideia do usuário: em vez de ele escolher o navegador, o programa tenta todos. Com a ressalva dele mesmo - não a cada faixa, mas ao abrir o programa e depois de cada falha.

`_descobrir_navegador_com_cookies()` testa a LEITURA dos cookies (não o download): é instantâneo, não usa rede e não depende do YouTube. Percorre `['firefox', 'edge', 'chrome', 'brave', 'opera', 'vivaldi', 'chromium']` - **Firefox primeiro de propósito**, porque é o único que não trava o arquivo enquanto está aberto, ou seja, o único que funciona com o navegador em uso.

O resultado fica guardado, inclusive o fracasso (`''`), pra não retestar sete navegadores a cada download num computador onde nenhum serve. `esquecer_navegador_de_cookies()` limpa o cache depois de uma falha, porque o navegador pode ter sido aberto (travando) ou fechado (liberando) nesse intervalo.

"automático" virou o **padrão** nas Configurações. A descoberta roda no arranque pra já avisar no log qual navegador será usado, ou que nenhum serve - e nesse caso sugere fechar o navegador ou instalar o Firefox.

Testado: degrada com recado útil quando não há navegador; sete testes na primeira vez e ZERO nas cinco faixas seguintes; e volta a testar depois de `esquecer`.

### BX. O disco com 2 faixas: o nome do álbum casava com tudo

Pior que o bitrate: das 7 faixas do "Aja", **só 2 foram salvas**. As outras 5 foram identificadas como a faixa "Aja" e puladas como repetidas.

**Causa**: `_match_playlist_track` devolvia a PRIMEIRA faixa cujo título fosse parecido. Os vídeos dessa playlist se chamam "Steely Dan ~ Deacon Blues ~ Aja (Official Remaster) HQ Audio" - o nome do ÁLBUM aparece em todos. A faixa 2 ("Aja") casava com todos os sete vídeos e vencia por estar antes na lista.

**Correção**: pontua TODAS as faixas parecidas e fica com a melhor, por dois critérios:
1. **Duração** (peso maior) - se o áudio tem 7:37 e o Discogs diz que "Deacon Blues" tem 7:37 e "Aja" tem 8:00, não há ambiguidade.
2. **Tamanho do título** - "Deacon Blues" é mais específico que "Aja"; casar com o nome mais longo erra menos.

Testado com os sete títulos REAIS do log do usuário: 7/7 corretos e com números de faixa distintos. E sem duração nenhuma, só pelo título, também 7/7 - o critério de especificidade sozinho já resolve este caso.

Quando há mais de um candidato, o log agora mostra quais foram considerados, pra dar como conferir a escolha.

### BY. O Firefox nunca teve chance: o erro era do nosso logger

O usuário instalou o Deno, atualizou o yt-dlp, instalou e logou o Firefox. Continuou 48kbps, e perguntou com razão: "não há nada errado, não?"

**Havia, e era meu.** Pra investigar, fiz a descoberta de cookies mostrar POR QUE cada navegador falhava, em vez da frase genérica. O primeiro teste revelou:

    firefox: 'DummyLogger' object has no attribute 'info'
    edge:    'DummyLogger' object has no attribute 'info'
    chrome:  'DummyLogger' object has no attribute 'info'

A leitura de cookies do yt-dlp chama cinco métodos no logger - `debug`, `info`, `warning`, `error` e `progress_bar` - e o `DummyLogger` só tinha três. Toda leitura quebrava no NOSSO código antes de chegar ao navegador. O Firefox logado do usuário nunca foi lido. O erro esteve lá desde que os cookies foram adicionados, escondido por uma mensagem que só dizia "não deu".

Corrigido implementando a interface inteira (o `progress_bar` é opcional; devolver `None` faz o yt-dlp usar a barra silenciosa dele). Verificado: a leitura agora vai até o fim e só para por falta de navegador neste ambiente - no computador do usuário deve ler.

**Segundo achado, do lado do YouTube**: o `DummyLogger` também descartava os avisos do yt-dlp que EXPLICAM a qualidade baixa. No código do yt-dlp há mensagens como *"Some web client https formats have been skipped... YouTube is forcing SABR streaming"*. O novo `LoggerDiagnostico` guarda só esses avisos (formatos pulados, SABR, PO Token, DRM) e, quando o áudio fica abaixo do que o vídeo anuncia, o log mostra o motivo que o próprio yt-dlp deu.

**Progresso que o log escondia**: o Deno FUNCIONOU. Antes só o cliente android baixava; depois dele, `mweb` e `web_safari` também. Só não bastou, porque esses clientes caem na restrição SABR.

**Lição**: um logger silencioso que engole exceção transforma defeito do programa em "problema do usuário". Três rodadas de ajustes na máquina dele por causa de um método ausente aqui.

### BZ. Deno e yt-dlp automáticos, pensados pra leigos

**Resultado confirmado pelo usuário antes desta mudança**: com Deno instalado, yt-dlp atualizado e cookies do Firefox lidos, o Steely Dan saiu em 138-141kbps pelo cliente padrão, virando MP3 de 160kbps. "O som está mais claro."

Mas ele chegou lá instalando o Deno pelo PowerShell e atualizando o yt-dlp na mão. Pediu que o executável fizesse isso sozinho, porque leigos vão usar o programa. Novo módulo `dependencias.py`.

**O que faz**, na política que o usuário definiu pros cookies - ao abrir e depois de cada falha, nunca a cada faixa:
- **yt-dlp**: baixa a versão mais nova pra `%LOCALAPPDATA%\DiscoFacil\ferramentas\` e faz o programa usá-la em vez da embutida (que vira reserva). A versão nova vale a partir da próxima abertura.
- **Deno**: se o computador não tem, baixa uma cópia só pro programa (~40 MB, uma vez) e passa o caminho direto ao yt-dlp. Sem mexer no PATH, sem pedir administrador. Se o usuário já instalou (como fez pelo winget), usa o dele.
- No arranque, uma linha no log com o estado: `🔧 Componente do YouTube: yt-dlp X (atualizado|do programa) · Deno: ok|ausente`. Essa linha teria poupado dias de 48kbps sem explicação.

**Decisões com motivo, todas verificadas de verdade** (o GitHub é alcançável deste ambiente):
- **Versão pelo redirecionamento `/releases/latest`, não pela API.** A API tem limite de 60 consultas/hora por IP e, no teste, já veio estourada. Numa rede compartilhada um leigo esbarraria nisso sem entender. O redirecionamento não tem limite.
- **Localizador em `sys.meta_path[0]`, não só `sys.path`.** Num executável PyInstaller o importador dele vem antes do `sys.path`, e a cópia embutida sempre venceria - a atualização seria ignorada em silêncio. **Testado num executável PyInstaller real**: sem a cópia baixada usa a embutida; com ela, a baixada vence, submódulos incluídos.
- **O import é feito dentro da proteção.** Uma versão futura do yt-dlp pode exigir um Python mais novo que o do executável; se o import quebrasse depois, no downloader, o programa NÃO ABRIRIA. Testado com uma cópia que quebra no import: desfaz tudo, apaga o arquivo e abre com a embutida.
- **Downloads vão pra arquivo temporário e só trocam no fim.** Download interrompido nunca deixa arquivo pela metade no lugar do bom; arquivo corrompido é detectado e apagado.
- **Pasta do usuário, não do programa.** Se o DiscoFácil estiver em "Arquivos de Programas", escrever lá exigiria administrador.
- **O trabalhador espera as peças na primeira abertura** (até 3 min), porque começar sem o Deno faria os primeiros álbuns saírem em 48kbps. Nas aberturas seguintes passa direto.
- **Verificação após falha limitada a uma vez a cada 30 min**: se o GitHub caiu, não adianta tentar a cada faixa.

**Testes feitos**: detecção de versão (yt-dlp 2026.08.19, Deno v2.9.7); download real do yt-dlp com progresso; "em dia" sem baixar de novo; troca do import no Python normal e no executável congelado; instalação real do Deno, que roda (`deno 2.9.7`) e que o yt-dlp reconhece (`supported=True`); arquivo corrompido; cópia que quebra no import; integração na janela; e o trabalhador esperando as peças.

**Limite honesto**: testado em Linux. No Windows o caminho é o mesmo, mas o arquivo do Deno é outro (`deno-x86_64-pc-windows-msvc.zip`) e não pude executá-lo aqui. O `main.spec` já inclui o módulo novo.

### CA. Todas as faixas com o álbum inteiro (32 min cada) - erro meu no corte

O usuário mostrou o "William Bell - The Soul Of A Bell": 11 faixas, todas com ~32 min e ~37 MB. Era o álbum inteiro repetido em cada arquivo. "Está assim com todos."

**Causa**: o comando de corte do ffmpeg tinha DUAS saídas. O bloco antigo (qualidade VBR por formato) acrescentava uma, e o bloco que escrevi no item BP (taxa acompanhando a fonte) acrescentava outra, pro mesmo arquivo. No ffmpeg, `-ss`/`-to` colocados depois do `-i` valem só pra PRIMEIRA saída; a segunda, sem limites, gravava o álbum inteiro por cima. Reproduzido: faixa de 10s a 40s saindo com os 120s do arquivo.

**Por que só apareceu agora**: o bloco antigo só entrava pra `.webm/.m4a/.opus/.ogg/.aac`. Enquanto o áudio vinha em `.mp4`, ficava de fora. Quando o download passou a trazer o melhor áudio (item BV, opus em `.webm`), os dois blocos entraram juntos. As playlists não foram afetadas (usam outro caminho de conversão), e foram o que se testou desde então.

**Correção**:
- Uma saída só. A fonte é medida sempre (o corte sempre reencoda; `.mp4` ficava sem medição).
- **Conferência depois de cada corte**: mede a faixa gravada e compara com o trecho pedido. Se passar de 5s ou 5% de diferença, apaga o arquivo e falha o álbum. Teria pego este defeito na primeira faixa, em vez de deixar um álbum inteiro sair com "✓" em todas. Testado forçando uma faixa errada.
- Testado com um `.webm` real de 180s cortado em 60/75/45s: as três saem com a duração exata.

**Consequência pra quem já tem álbuns gravados errados**, e duas correções pra que dê pra refazê-los:
- A fila recusava reenfileirar item já processado ("Já processado antes"), então não havia como refazer um álbum. Agora pedido EXPLÍCITO (disco único, playlist) reabre o item. Só o canal não reabre - relistar 3000 vídeos não pode refazer tudo.
- O índice do acervo, montado ao abrir, continuava listando a pasta de um álbum apagado com o programa aberto, e o reenvio era pulado como "já está no acervo". Agora `has()` confere se a pasta ainda existe e esquece a entrada órfã.

## VERSÃO 12.0

A versão agora mora num lugar só (`versao.py`): título da janela, cabeçalho, ajuda, log de cada álbum, identificação no MusicBrainz e tutorial. Antes a janela dizia "v11.0" e o log de cada álbum "V10.8.4".

### CB. Corte pelo início real da faixa seguinte (melhorias 1 e 2)

Caso: "Gloria Lynne - Gloria, Marty & Strings", faixa 1 cortada uns segundos depois. O log mostrou a causa: o refinamento achou um silêncio bem mais fundo 3,3s ANTES do corte e o descartou só por ficar mais longe da duração do Discogs ("Refinamento não melhorou... mantém original"). A faixa 2 começa com uma introdução suave, abaixo de -35dB, que o detector leu como silêncio; o corte, que vai pro fim do silêncio, caiu dentro da faixa 2.

Isso também mudou a melhoria 2 que eu tinha proposto ("preferir o ponto mais próximo do Discogs"): foi exatamente essa preferência que causou o erro. A versão correta é o contrário - dentro de poucos segundos, o áudio decide, não o Discogs.

Novo passo final (`SmartCutter.ajustar_ao_inicio_da_proxima`), aplicado a todos os cortes de todos os métodos: acha o trecho mais fundo perto do corte e o instante em que o som volta. Travas pra não estragar os discos que já saem certos:
- só age se houver silêncio de verdade (20dB abaixo da música);
- recua no máximo 6s, e só se o corte atual estiver em som (não em silêncio) e se tudo entre o começo real e o corte for suave - um final alto de música bloqueia;
- avança só atravessando silêncio;
- diferenças abaixo de 0,8s não mexem; nenhuma faixa fica com menos de 20s;
- qualquer erro mantém os cortes (nunca falha um álbum).

Testado com áudio sintético em 10 situações (caso Gloria, introdução que cresce, silêncio limpo, acorde final antes do intervalo, corte dentro do fade, corte no meio do silêncio, faixas emendadas, vinil com chiado etc.). E o teste que responde ao lembrete do usuário ("os outros discos cortou legal"): o PIPELINE COMPLETO rodado lado a lado com a versão anterior, num álbum de 8 faixas com durações do Discogs erradas em até 2s - nos discos limpo e de vinil os cortes novos são IDÊNTICOS aos antigos, faixa por faixa; no disco com introdução suave o antigo corta 2,0s dentro da faixa 2 (o defeito relatado) e o novo 0,6s antes do começo real.

Junto: as amostras de áudio em memória passaram de float64 pra float32 - metade da memória num álbum longo (um disco de 60 min ocupava ~1,3 GB), sem diferença de resultado.

### CC. MusicBrainz funcionando de verdade (melhoria 3)

Já existia, mas nunca aparecia nos logs. Três causas: pegava só o PRIMEIRO resultado da busca (muitas vezes uma coletânea, com outro número de faixas, descartada sem aviso); se apresentava como "Mozilla/5.0" (o MusicBrainz pede identificação do programa e pode recusar pedidos genéricos); e fazia dois pedidos colados (o limite é 1 por segundo). Agora: se identifica como DiscoFacil/12.0, espera 1,1s entre pedidos, olha até 10 resultados e fica com uma edição que tenha o MESMO número de faixas do Discogs (testa até 3), e diz no log por que não usou quando não usar. Testado com respostas simuladas no formato da API (daqui não alcanço o MusicBrainz).

### CD. Discos sem Discogs (Track 1, Track 2...) com várias músicas num arquivo

Dois defeitos antigos, achados ao reproduzir o problema com o detector real:
1. Desde que o corte passou pro fim do silêncio, a "duração do silêncio" era calculada como `fim - posição`, que dá sempre 0,5s. O filtro "silêncio ≥ 1,0s" do modo sem Discogs descartava TODOS os intervalos. Nos discos com Discogs era só o texto do log ("silêncio 0.5s" em quase toda faixa). Corrigido com `duracao_do_silencio()`, que lê a duração que cada detector guarda.
2. Quando o Discogs tem os títulos mas não as durações, a tabela de conferência comparava os cortes com uma soma de zeros e recusava o disco com "100% offsets ruins". Agora só confere quando há durações.

E uma melhoria: LP digitalizado tem chiado no intervalo, que nunca fica abaixo do limite fixo do detector de silêncio. Novo `_completar_com_quedas_relativas`: procura quedas de volume em relação à música ao redor, só dentro de trechos longos demais pra uma faixa (ou até completar o número de faixas, quando o Discogs informa). Testado: LP sintético de 8 faixas com intervalos curtos e com chiado - antes recusado, agora 8/8 certas, com e sem o número de faixas; disco limpo sem nenhuma fronteira inventada; jazz com faixas de 9-12 min e pausas internas sem nenhuma divisão falsa.

### CE. Pequenos

- O verificador de componentes (Deno/yt-dlp) não pode mais ser derrubado por um erro ao escrever no log.
- Tutorial refeito pra versão 12.0: telas novas (Configurações com confiança e cookies, "Precisam de você", linha de situação), versão na capa e no rodapé, e uma nota sobre a primeira abertura.

## VERSÃO 12.1

### CF. "Não processou da Gloria Lynne" (erro "int + str")

Foi a primeira vez que o MusicBrainz achou o álbum de verdade - e o ajuste de durações quebrou. As faixas do Discogs, nesse ponto do processamento, já estão no formato de exibição ("3:22", texto), e o ajuste somava direto como se fossem números. O erro abortava o álbum inteiro.

Correções:
- Novo `segundos_da_faixa()`: lê a duração em qualquer formato que circula no programa (número, "M:SS", "H:MM:SS", `duration_seconds`) e nunca levanta erro. Usado no ajuste do MusicBrainz, na junção chapters + Discogs (que tinha o mesmo defeito escondido: comparava "3:22" com 0) e no reenfileiramento.
- Ao adotar o MusicBrainz, o valor exato vai para `duration_seconds` (o que o corte lê primeiro) e `duration` continua no mesmo formato de antes. Antes gravava um número onde o corte esperava texto, e o corte leria 0.
- O ajuste do MusicBrainz agora é protegido: qualquer falha ali só registra "ajuste pulado" e segue com o Discogs. É um ajuste fino - nunca pode derrubar um álbum.
- As mensagens de erro da fila agora dizem onde o erro aconteceu (arquivo:linha), pra diagnóstico mais rápido.

Testado: 12 faixas no formato real ("M:SS") com MusicBrainz simulado em 4 situações (encaixa melhor → adota; empate → mantém; sem resultado; falha de rede) - nenhuma exceção, formato preservado, soma adotada bate com o áudio. Conversor com 9 formatos. Suítes anteriores (20 testes de corte, discos sem Discogs, ponta a ponta limpo/vinil/Gloria) com resultados idênticos aos da 12.0. Tutorial refeito com a versão 12.1.

### CG. Gloria Lynne, faixa 7: o começo da faixa 8 ficava no fim da 7

A faixa 8 abre com cordas tão baixas que o detector leu ~4s de introdução como silêncio. A conferência de intervalos até acusou ("Faixa 8: faltam 4,3s"), mas o ajuste fino não recuou o corte. A trava "só recua se o corte estiver em som" exige 10dB acima do silêncio, e a introdução estava abaixo disso.

Novo `SmartCutter._recuo_pela_falta`: uma segunda busca, só no corte cuja faixa SEGUINTE ficou pelo menos 2s mais curta que a duração informada. Ela é mais sensível (começo do som 8dB acima do fundo em vez de 12; basta haver algum som no ponto de corte), mas nunca recua mais do que o que falta + 1,5s, e mantém as outras proteções: precisa haver silêncio de verdade (20dB abaixo da música) e nada alto entre o silêncio e o corte (o acorde final da faixa anterior continua protegido). Discos que já saem certos não têm falta, então nada muda para eles.

A mensagem da conferência também foi corrigida: dizia sempre que "o fim dela foi pro arquivo seguinte", mas a falta pode ser tanto o começo no arquivo anterior quanto o fim no seguinte.

Testado com áudio sintético reproduzindo o caso (chiado de fundo + introdução baixinha, corte 4s dentro dela): o ajuste antigo não mexia e o novo recua para 0,4s antes do começo real. Pega introduções a partir de ~9dB acima do chiado (a busca normal só a partir de ~19dB). Casos protegidos: sem falta, falta de só 1s, acorde alto no meio, faixas emendadas sem silêncio e recuo além do permitido. Nenhum deles mexeu. Suítes anteriores e ponta a ponta com cortes idênticos. Versão e tutorial mantidos (12.1).

### CH. Gloria Lynne, faixa 7: medido no áudio real, não era o que parecia

Com os MP3 das faixas 7 e 8 enviados pelo usuário ficou claro: no fim da faixa 7 há 2,5s de silêncio digital absoluto, e depois dele ~0,6s do começo da faixa 8 (o usuário ouvia "menos de 1 segundo"). O detector do ffmpeg (-35dB) contou essas cordas, a -36dB, como parte do silêncio, e o corte caiu depois delas.

O ajuste fino via o problema, mas a trava que protege acordes finais ("o som entre o começo real e o corte tem que ser suave, 12dB abaixo da música") barrou o recuo por 0,6dB. As duas faixas são baladas baixas, então as cordas não pareciam "suaves" em relação a elas.

Correção: quando há um silêncio fundo e LONGO (≥1,5s) terminando pouco antes do corte (≤1,5s) e o som CONTINUA depois do corte, o recuo é permitido mesmo sem ser "suave". Um silêncio desses é separação inequívoca entre faixas, e o que vem logo depois só pode ser o começo da próxima. A exigência de que o som continue impede que um acorde final isolado depois de uma pausa longa seja jogado para a faixa seguinte.

Testado com o áudio REAL das faixas 7 e 8: o corte vai de 2:54.2 para 2:53.0, dentro do silêncio digital; a faixa 7 termina sem nenhum som da 8, a 8 começa inteira (0,65s de respiro antes do primeiro som) e o final da música da 7 fica preservado. Novos casos sintéticos: réplica deste caso (recua) e acorde final depois de pausa longa (não recua). Todas as suítes anteriores e o ponta a ponta com cortes idênticos. Versão e tutorial mantidos (12.1).

### CI. Primeiro uso em outro computador: playlists não convertiam e Deno só na segunda abertura

**Playlists ("[WinError 2] O sistema não pode encontrar o arquivo" em toda faixa).** A conversão pra MP3 das playlists usava a biblioteca pydub, que procura o ffmpeg no PATH do Windows. No computador principal do usuário havia um ffmpeg instalado no PATH, e o problema nunca aparecia. No computador novo só existia o ffmpeg que vem com o programa. O plano B (mover o .webm renomeando pra .mp3) ainda dava "[WinError 32] arquivo em uso", porque a pydub deixava o arquivo aberto ao falhar. E o plano B era errado em si: gravaria um arquivo que não é MP3 com nome de MP3.
- `_usar_ffmpeg_do_programa()`, na abertura: põe a pasta do ffmpeg do programa no PATH do processo e aponta a pydub pra ele. Com isso as outras partes que usavam o ffmpeg do sistema também passam a achar o do programa: os detectores de silêncio e a análise de áudio, que no computador novo falhariam caladas.
- A conversão das playlists agora chama direto o ffmpeg do programa (igual ao corte de álbum) e confere a duração do MP3. Se falhar, a faixa falha limpa: não fica nenhum ".mp3" falso e o temporário é apagado.
- `_medir_duracao_audio` chamava "ffprobe" sem o caminho do programa. Corrigido.

**Deno só instalava na segunda abertura.** Sem o log da primeira abertura não dá pra saber qual das causas possíveis aconteceu, então foram cobertas todas:
- Windows recém-instalado vem com a lista de certificados incompleta, e a primeira conexão ao GitHub pode falhar com CERTIFICATE_VERIFY_FAILED. Agora, se isso acontecer, o download tenta de novo com a lista de certificados que vem com o programa (certifi, incluído no .exe pelo main.spec).
- Uma falha passageira só se resolvia reabrindo o programa. Agora são até 3 tentativas na mesma abertura (espera de 15s e depois de 45s).
- A fila esperava no máximo 3 min pelo Deno. Numa conexão lenta, os ~40 MB passavam disso e a fila começava sem ele. Agora espera até 10 min, e avisa se começar sem ele.
- O log agora diz o MOTIVO de cada falha (ex.: "URLError: timed out"), em vez de só "sem internet?".

Testado simulando o .exe num computador sem ffmpeg no sistema. O código antigo reproduz o erro do log e o novo converte a faixa em MP3 de verdade, com a duração certa e o temporário apagado. Arquivo corrompido falha limpa. Deno testado com falha de certificado (instala pelo certifi), sem internet (motivo no log), duas falhas passageiras (instala na 3ª tentativa, na mesma abertura) e três falhas (avisa e libera a fila). Suítes anteriores, teste com o áudio real da Gloria, ponta a ponta e abertura da janela: tudo igual. Versão e tutorial mantidos (12.1).

### CJ. "The page needs to be reloaded" em todas as faixas (outro computador)

Erro conhecido do yt-dlp (issues #17389 e #17405, agosto/2026). Com cookies de conta logada, o yt-dlp usa o cliente 'tv_downgraded', que o YouTube passou a responder como "injogável". O yt-dlp embutido (2026.08.19) já é a última versão publicada, então atualizar não resolve. No log do usuário a consulta SEM cookies (a do "Melhor áudio anunciado: 130kbps") funcionava, e TODOS os downloads com cookies falhavam, gastando as 3 tentativas de cada faixa.

Correção (downloader.py): quando esse erro aparece, tenta em dois degraus:
1. sem o cliente tv_downgraded (`player_client: default, -tv_downgraded`), ainda com os cookies;
2. sem os cookies do navegador.

O que funcionar fica valendo até o programa ser fechado, e as faixas seguintes já vão direto por esse caminho, sem erro e sem tentativas desperdiçadas. Vale tanto para a busca pelo melhor áudio quanto para o caminho antigo de download. Sem esse erro nada muda: nenhum cliente é forçado e os cookies continuam sendo usados, como no computador principal.

Testado com um yt-dlp simulado em 4 situações: erro sempre que há cookies (baixa sem cookies, e a faixa seguinte vai direto em 1 chamada); erro só com o cliente tv (resolve mantendo os cookies); falha em tudo (devolve "falhou" com o motivo, sem travar); e sem erro (chamadas idênticas às de antes). Suítes anteriores, teste de playlist sem ffmpeg no sistema, áudio real da Gloria e abertura da janela: tudo igual. Versão e tutorial mantidos (12.1).

### CK. Correção do CJ: o contorno parava no primeiro degrau

No primeiro uso real (playlist da Simone, 1980) o contorno entrou em ação, mas o degrau 1 (cookies sem o cliente tv_downgraded) respondeu com OUTRO erro: "Requested format is not available". Com cookies, os clientes que sobram não entregam áudio. O código tratava erro diferente como "não adianta insistir" e parava ali, sem chegar ao degrau 2 (sem cookies), justamente o que funciona nesse computador. Agora os dois degraus são sempre tentados, com qualquer erro.

Testado com o yt-dlp simulado reproduzindo exatamente essa sequência: chega ao degrau sem cookies e baixa, e a faixa seguinte vai direto em 1 chamada. Os casos anteriores continuam iguais.

### CL. Contorno sem cookies nunca salva áudio pior

O usuário apontou o risco certo: sem cookies o YouTube pode anunciar 130kbps e só liberar bem menos (já aconteceu: 138 anunciado, 62 entregue), e o mínimo das Configurações (80kbps) deixaria passar um álbum de 90kbps. Agora, quando o download foi feito sem cookies por causa do contorno, `download_audio` mede o arquivo e só aceita se tiver pelo menos 90% do melhor áudio anunciado (o mesmo "aceito a partir de" do log). Abaixo disso o arquivo é descartado, o motivo vai pro log ("Sem os cookies o YouTube só liberou Xkbps (o vídeo tem Ykbps) - não salvei pra não perder qualidade") e o álbum vai pra "Precisam de você", sem gastar tentativas repetidas. Downloads com cookies não mudam.

Testado: sem cookies com 45kbps num vídeo de 130 → descartado, sem sobrar arquivo; sem cookies com 119kbps → aceito (piso 117); com cookies → trava não interfere. Demais testes iguais.

### CM. Contorno sem cookies: vídeos com restrição de idade e vídeos que só liberam áudio bom com a conta

Primeiro uso real do contorno: Simone (1980) e Back to Black (21 faixas) saíram completos, com 128-150kbps. Dois problemas apareceram:

1. **"Frank", faixa 2:** sem cookies, todos os clientes falharam com "Requested format is not available", menos o android (48kbps). A trava de qualidade funcionou (nada foi salvo), mas o programa desistia sem tentar com a conta. Agora, se sem cookies não chegar à qualidade cheia, ele tenta ESTE vídeo com os cookies do navegador (sem o cliente que dá "recarregar a página") e fica com o melhor dos dois.
2. **Vídeo com restrição de idade ("Fuck Me Pumps"):** o YouTube exige login e o programa estava fixo em "sem cookies". Pior: a mensagem do YouTube ("Use --cookies-from-browser...") contém "cookies" e era lida como "não consegui ler os cookies do navegador". O programa então largava os cookies e redescobria o navegador a cada tentativa (as linhas "🍪 Usando cookies do firefox" repetidas). Corrigido:
   - o reconhecimento de falha de leitura de cookies não confunde mais a DICA do YouTube com falha de leitura;
   - vídeo com restrição de idade, com o contorno ativo, é baixado com a conta (só esse vídeo; os seguintes voltam ao caminho sem cookies), tanto na busca pelo melhor áudio quanto no caminho antigo.

Quando o áudio fica abaixo do anunciado, o log agora também mostra o erro de cada cliente, pra diagnóstico.

Testado com o yt-dlp simulado (agora nomeando os arquivos pelo código do formato, como o real): caso Frank (sem cookies só 45kbps → tenta com a conta → salva 119kbps), restrição de idade (baixa com a conta, sem a mensagem falsa, e a faixa seguinte volta ao caminho sem cookies), e o reconhecimento de cookies (dica do YouTube ≠ falha; falhas reais continuam reconhecidas). Os 18 casos anteriores/novos, as suítes de corte, o teste de playlist sem ffmpeg e a abertura da janela passam.

## VERSÃO 12.2

Primeira etapa do plano combinado (PLANO.md, itens 6, 7 e 10). Só interface e log; corte e identificação não mudaram, a não ser pelo CN.

### CN. Testes dentro do projeto + uma correção que eles acharam

- A pasta `testes/` roda de qualquer lugar: `python testes/rodar_todos.py` roda todos (cada um num processo, resumo no fim). Os caminhos fixos do ambiente antigo saíram; os arquivos de apoio (fonte.webm, ffmpeg.exe simulado, as faixas 7+8 da Gloria emendadas) são gerados sozinhos em `testes/.tmp`. `DF_PROJ=<pasta>` roda os mesmos testes contra outra cópia do programa (ex.: a versão anterior).
- O ponta a ponta agora compara os cortes com uma referência gravada da 12.1 (`testes/referencia_e2e.json`). Qualquer mudança no corte aparece como falha.
- **Correção (combinada com o usuário):** o teste da Gloria com o áudio real falhava aqui. O decodificador de MP3 deste ambiente deixa UMA amostra de valor mínimo (1/32768) no meio dos 2,5s de silêncio digital. O cálculo de volume tratava zero absoluto como -180dB e essa amostra como -133dB, e o "silêncio longo" virava dois curtos. Pode acontecer no Windows também, conforme a versão do ffmpeg. Agora qualquer volume abaixo de 1 amostra conta como silêncio total. O corte volta para 2:53.0, como na 12.1, e todos os outros cortes ficam idênticos. Teste novo: silêncio digital com uma amostra perdida (falha na 12.1, passa na 12.2).

### CO. Janela principal

- **Abre pronta pra usar:** já vem com o último modo usado (Vídeo Único na primeira vez). O campo de link e a linha de botões (Copiar Log, Abrir Pasta, Retomar fila, Precisam de você) ficam sempre visíveis, em qualquer modo. "Retomar (N)" e "Precisam de você (N)" já abrem com a contagem.
- **Um campo por modo:** Vídeo Único e Canal têm cada um o seu campo. Trocar de modo não leva mais o que estava escrito.
- **Reconhece o link colado:** watch?v= / youtu.be = vídeo; /@nome, /channel/ = canal; list= = playlist. Se não combinar com o modo, aparece um aviso abaixo do campo com um botão "Usar <modo certo>", que troca de modo e leva o link junto. Na lista de playlists, avisa quantas linhas não são playlist. No modo Canal, um link de vídeo ou playlist é recusado com explicação, como já era no modo Vídeo.
- **Campo limpo depois de enfileirar:** o link sai do campo assim que entra na fila e fica registrado no log. Na lista de playlists só saem as que entraram; as que deram erro ficam no campo, com aviso do motivo.
- **Pergunta ao abrir, se houver fila:** "Há N álbum(ns) na fila. [Retomar agora] [Depois]". Se o Deno ainda estiver instalando, a fila espera sozinha, como antes.
- **Menu do botão direito** em todos os campos de texto de todas as janelas (link, playlists, Configurações, busca): Colar, Copiar, Selecionar tudo. Nos campos de link e na lista de playlists, também Limpar. No log: Copiar e Selecionar tudo.

### CP. Log na tela

- **Rolagem:** o log só acompanha o fim se você já estiver no fim. Se rolar pra cima pra ler, ele fica parado e aparece "↓ N linha(s) nova(s)". Clicar nele, ou rolar até o fim, volta a acompanhar. A janela mudar de tamanho não tira o log do fim.
- **Em lotes:** as linhas entram ~10x por segundo, e não mais uma a uma redesenhando a janela. Também deixou de mexer na janela direto da thread do trabalhador, o que o Tkinter não garante (agora só a thread da janela toca nela).
- **Configurações no log**, no início e a cada vez que salvar: versão, pasta de saída, bitrate mínimo, confiança mínima, navegador dos cookies e as chaves só como "configurada"/"não configurada". Saiu a linha "Groq (apoio técnico de corte)", que era enganosa (o Groq não participa do corte).
- Uma chave que por engano apareça em qualquer mensagem é trocada por "***" na tela e no arquivo. O console também deixou de mostrar o começo da chave do Discogs (mostrava 20 caracteres).

### CQ. Arquivo de log por rodada (pra anexar quando algo der errado)

Cada abertura do programa grava `<pasta de saída>/logs/DiscoFacil_<data>_<hora>.log`, e o caminho aparece no log da tela. Tem tudo o que sai na tela, com a hora, e mais linhas de diagnóstico com etiqueta, pra achar com uma busca:
`[RODADA]` versão e sistema · `[CONFIG]` configurações (sem chaves) · `[DISCO]` cada disco (título e link) · `[FONTE]` edição escolhida (release, master, nº de faixas e quantas têm duração, confiança, score, quantas edições candidatas) · `[PENDENTE]` foi pra "Precisam de você", com o motivo · `[REJEITADO]`/`[FILA]` a fila desistiu ou vai tentar de novo, com o motivo · `[PRONTO]` · `[ERRO]` mensagem, arquivo:linha e o traceback completo.
Erros que antes sumiam sem rastro (dentro de botões da janela ou em tarefas de fundo) também vão pro arquivo, com o local.

Testado: todos os testes antigos passam, com os cortes idênticos à referência. Testes novos: `teste_interface.py` (48 conferências com a janela aberta de verdade: abertura, campos, avisos, limpeza, menu em todas as janelas, rolagem, último modo, pergunta da fila) e `teste_registro.py` (12 conferências do arquivo de log, com o trabalhador da fila rodando de verdade). Tutorial refeito (interface mudou).

## VERSÃO 12.3

### CR. Nova janela "Precisam de você" (PLANO.md, item 4)

Antes, cada clique (marcar, desmarcar, remover) apagava e redesenhava a lista inteira e regravava o arquivo, e remover pedia confirmação um por um. Agora a janela é uma tabela (`janela_pendentes.py`):

- **Colunas:** título, motivo, confiança, data e "▶ YouTube". Embaixo da tabela aparece o motivo completo da linha em foco, e o link. Clicar no título de uma coluna ordena por ela.
- **Seleção normal:** clique, Ctrl+clique, Shift+clique, Ctrl+A, "Selecionar tudo", "Todos com este motivo".
- **Filtro por motivo** (com a contagem de cada um) **+ busca** no topo. A busca procura no título, no motivo e no link.
- **Botões que agem nos selecionados**, com a quantidade no próprio botão: "➕ Enfileirar (N)", "🗑 Remover (N)" com UMA confirmação só, e "🔍 Buscar outra versão", que precisa de um único selecionado porque abre a busca preenchida com aquele disco. Enter enfileira e Delete remove.
- **"Abrir no YouTube" continua individual:** clicar em "▶ abrir" na linha abre aquele vídeo sem mexer na seleção. Duplo clique na linha também abre.
- **Resposta instantânea:** só as linhas afetadas mudam. Ao enfileirar, ganham ⏳ ("já está na fila"); ao remover, saem e a seleção passa pra linha seguinte. O arquivo é gravado uma vez por ação. Enfileirar 50 de uma vez também grava a fila de processamento uma vez só (antes: 50).
- **Remover não apaga mais de vez:** vai pra "Descartados" (botão no topo, com a contagem), de onde "↩ Recuperar" devolve à lista. Os descartados ficam em `pendentes_descartados.json`, na pasta de saída.
- A janela acompanha sozinha o que o trabalhador da fila faz: item novo aparece, item resolvido sai e o ⏳ some quando o item sai da fila. Uma janela só: abrir de novo traz a mesma pra frente.
- Ao enfileirar, a janela da fila não abre mais por cima desta. Aparece uma confirmação verde embaixo da tabela, e dá pra continuar selecionando e enfileirando.

Por baixo: `PendingQueue` ganhou trava (a janela e o trabalhador mexem nela de threads diferentes), gravação atômica (temporário + troca), ações em lote (`descartar`, `recuperar`, `remove_many`) e um contador de versão. `FilaUnica` ganhou `em_lote()` (várias mudanças, uma gravação).

Testado: `teste_pendentes.py` (41 conferências com a janela aberta de verdade): colunas e valores, clique na coluna do YouTube sem mexer na seleção, duplo clique, clique/Ctrl/Shift de verdade, selecionar tudo e por motivo, filtro, busca, enfileirar 3 (uma gravação da fila, só as 3 linhas mudam, sem redesenhar a tabela), remover 3 (uma confirmação, uma gravação de cada arquivo), Descartados e Recuperar (gravado em disco), mudanças feitas pelo trabalhador aparecendo sozinhas, e 3000 itens (abre em menos de 1s). Todos os testes anteriores passam. Tutorial refeito (interface mudou).

## VERSÃO 12.4

PLANO.md, itens 5 (nomes de faixa de playlist e álbum lido da descrição) e 9 (número do artista). A interface não mudou, então o tutorial continua o da 12.3.

### CS. Nomes das faixas de playlist (caso Simone)

7 das 10 faixas da playlist da Simone ficaram com o nome do vídeo. O casamento de títulos não entendia três coisas, e agora entende (`nomes.py`):
- o **nome do artista na frente** ("SIMONE PARA LENNON & McCARTNEY", "Simone • Encontros & Despedidas") e também no fim ("Começar de Novo - Simone");
- **títulos bilíngues com "="** ("Para Lennon Y McCartney = Para Lennon E McCartney"): cada lado é comparado separado;
- **"&" no lugar de "E"/"Y"/"and"**, e acentos ("TÔ QUE TÔ" = "Tô Que Tô").

A comparação nova SOMA à antiga: nada que casava antes deixa de casar. A escolha entre várias faixas parecidas continua pela duração e pelo título mais específico, então o caso Steely Dan (Aja) continua certo (7/7).
- **Sufixos de vídeo saem do nome do arquivo** quando a faixa não casa com o Discogs: "(Audio)", "(Official Music Video)", "[HD]", "- Lyric Video", "(Áudio Oficial)" etc. "Will You Still Love Me Tomorrow (Audio)" vira "05 - Will You Still Love Me Tomorrow.mp3". O que faz parte do nome fica: "(Live)", "(Remastered 2020)".
- Quando uma faixa não casa, o arquivo de log ganha uma linha `[AVISO]` com o título do vídeo e a tracklist inteira, pra diagnóstico.

### CT. Número depois do nome do artista ("Simone (3)", "Marina*")

É o desempate do Discogs pra artistas com o mesmo nome; o "*" marca variação de nome. Agora sai das **pastas** e das **tags** (artista e artista do álbum), em todos os caminhos: corte de álbum, playlist e a gravação de tags. O nome completo fica guardado só por dentro (`artists_discogs`, junto com master_id/release_id). Pastas já criadas com o número não são mexidas.

### CU. Título sem nome de álbum ("Wes Montgomery (Jazz)")

Quando o título do vídeo não traz o álbum (o "álbum" sai igual ao artista, ou é só um gênero como "Jazz" ou "Full Album"), o programa procura o álbum na **descrição do vídeo** antes de buscar no Discogs: "Álbum: X", uma linha "Artista - Álbum (ano)", 'do álbum "X"' / 'from the album "X"', '"X" (1962)'. O artista também perde o "(Jazz)". O log diz de onde veio o álbum ("achei na descrição"), e o arquivo de log registra em `[FONTE]`. Se a descrição também não disser, segue como antes. Título que já traz o álbum não é afetado.

Testado: `teste_nomes.py` (41 conferências): 11 formas de nome de artista; candidato do Discogs (respostas simuladas no formato da API) com nome limpo pra fora e completo por dentro; pasta e tags reais de uma faixa de playlist com "Simone (3)"; tags pelo gravador do corte de álbum; Simone 10/10 (a comparação antiga casava 3/10); 6 sufixos; arquivo sem "(Audio)"; Steely Dan 7/7; 8 descrições (5 com álbum, 3 sem nada confiável); o fluxo completo buscando no Discogs com o álbum da descrição, e um título com álbum sem interferência. Todos os testes anteriores passam.

Nos testes: eles agora rodam dentro de uma pasta descartável (`testes/.tmp/pasta_atual`). Motivo: um teste meu com uma configuração falsa que devolvia "" pra tudo fez o programa apagar a pasta atual. `process_single_video` limpa a pasta de `config.get('cache_directory', ...)`, e um caminho vazio é a pasta atual. No programa de verdade isso não acontece, porque essa chave não existe no config.json e vale o padrão. Fica o registro (ver observação na conversa).

## VERSÃO 12.5

PLANO.md, itens 1, 2 e 3: identificação × encaixe, outras edições, MusicBrainz e a retirada da passada repetida. A interface não mudou, então o tutorial continua o da 12.3.

### CV. Duas notas em vez de uma "confiança"

- **Identificação** ("é este o álbum?"): título do álbum, títulos das faixas, nº de faixas e duração total, com os mesmos pesos de antes e duas regras novas:
  - a duração total conta como coincidente dentro de **±5%** do áudio (antes era ±1% ou 10s). Passando disso, a nota cai aos poucos até 15%;
  - cadastro **sem durações** (ex.: Os Boêmios) é "sem informação", não falha. A nota fica pelos títulos.
  É essa nota que decide entre baixar sozinho e mandar pra "Precisam de você" (a "confiança mínima" das Configurações agora vale pra ela). O log mostra as partes: `Identificação: 100% (título do álbum 1.00 · títulos das faixas 9/10 · nº de faixas igual · duração total coincide (1.4%))`. A escolha da edição continua pela pontuação de sempre.
- **Encaixe** ("as durações deste cadastro servem pra cortar este áudio?"): medido **faixa a faixa** depois de detectar os silêncios (`encaixe.py`). Conta em quantas fronteiras a duração aponta pra um silêncio real a até 5s. A posição esperada parte do corte anterior confirmado, então o erro de uma faixa não contamina as seguintes. O log mostra o encaixe de cada edição: `Discogs 123 (escolhida): 10 faixas → 2/9 fronteiras num silêncio (22%)`.

### CW. Identificação alta + encaixe ruim: outras edições, MusicBrainz e silêncios

Quando a edição escolhida encaixa (3 de cada 4 fronteiras ou mais), o corte é feito com ela, **exatamente como antes**. Os discos do ponta a ponta, passando pelo caminho novo, saem com cortes idênticos aos da 12.1. Quando não encaixa:
1. **Outras edições do mesmo álbum no Discogs**, que a busca já tinha trazido (mesmo master ou título parecido). Não custa consulta nova.
2. **Edições do MusicBrainz** com o mesmo nº de faixas e títulos parecidos (pelo menos 70% casando). As durações vêm do MusicBrainz e os nomes continuam os do Discogs. O MusicBrainz também **desempata** quando duas edições do Discogs encaixam igual: fica a mais próxima dele.
3. Corta com a de **melhor encaixe** e troca a edição registrada (release, capa) pela que encaixou. A reavaliação antiga "pela soma das durações" não pode mais desfazer essa escolha.
4. Se nenhuma servir: **corta pelos silêncios e usa o Discogs só pros nomes**, casando cada pedaço com uma faixa pela duração, mesmo fora de ordem. A numeração segue a ordem do áudio, e o log mostra quando a ordem é diferente do cadastro. Se duas faixas têm quase a mesma duração e apareceriam trocadas, ele não arrisca.
5. Se o corte pelos silêncios achar **nº de faixas diferente** do Discogs (sinal de duas músicas emendadas), ou as durações não casarem, o disco vai pra **"Precisam de você"** com o motivo exato. Nada sai com nome trocado nem com duas músicas num arquivo.

As **edições candidatas** vão guardadas junto com o item em "Precisam de você" (até 20, com tracklist e durações), e a nova tentativa usa as guardadas sem refazer a busca. As notas também vão: o arquivo de log ganha uma linha `[NOTAS]` por disco (identificação, encaixe da escolhida, edição usada ou motivo da recusa).

Proteção: qualquer erro nesta avaliação nova registra o local e corta do jeito antigo. Nunca derruba um álbum.

### CX. Correções do item 3

- **Conta errada no corte pelos silêncios** (Nico Assumpção 1981): o "silêncio" a menos de 30s do fim, que deixaria um último pedaço de 0,5s, agora é descartado ANTES de comparar a contagem com o Discogs. Antes eram 10 cortes contra 9 esperados, e as faixas saíam "Track 1, Track 2…" mesmo com 10 faixas = 10 do Discogs.
- **Segunda passada inútil retirada:** "Usando detecção de silêncio com nomes do Discogs" refazia a mesma análise com a mesma entrada, e se acertasse gravaria artista/álbum como "Unknown". O lugar dela agora é o passo 4 acima. A tentativa pelos capítulos do YouTube, que vem antes, ficou.
- A detecção de silêncios roda uma vez por áudio; as tentativas seguintes reaproveitam o resultado e o áudio já decodificado.

Testado: `teste_encaixe.py` (40 conferências, com corte real em discos sintéticos de 8 faixas): encaixe da edição certa, da mesma edição em outra ordem (total igual, encaixe baixo) e com erro de 2s por faixa; casamento por duração fora de ordem e as 3 recusas (nº diferente, duração longe, faixas de mesma duração trocadas); identificação a 4%, 8% (antes ia pra pendências), 30%, sem durações com títulos que batem e que não batem; Discogs simulado usando a identificação como confiança; corte com a edição certa (nomes e durações conferidos); troca pra outra edição em memória; MusicBrainz com durações dele e nomes do Discogs; nada encaixando (recusa sem nome trocado); silêncios + nomes fora de ordem; duas músicas emendadas (recusa: "achou 7 faixas e o Discogs tem 8"); conta do Nico; ordem das tentativas sem a passada repetida; candidatas e notas guardadas e reaproveitadas; erro na avaliação nova; desempate pelo MusicBrainz; e os 3 discos do ponta a ponta pelo caminho novo, idênticos à 12.1. Todos os testes anteriores passam.

## VERSÃO 12.6

### CY. Baixar o próximo álbum enquanto o atual é cortado (PLANO.md, item 5)

Assim que o áudio de um álbum está baixado e o corte começa, o **próximo** da fila já vai baixando em segundo plano, na pasta `.temp/proximo` da pasta de saída. Quando a vez dele chega, o programa usa o arquivo pronto. Se o download antecipado ainda estiver em andamento, espera terminar em vez de começar outro. O log diz "Baixando o próximo em segundo plano…" e depois "Usando o áudio que já tinha sido baixado em segundo plano" (e o arquivo de log registra em `[FILA]`).

Regras (`pre_download.py`):
- **Só um à frente**, e só disco único (vídeo com o álbum inteiro, vindo da fila ou de um canal). Playlist e pendência não são antecipadas.
- **Os downloads nunca correm ao mesmo tempo:** o download normal e o antecipado passam pela mesma trava, porque o yt-dlp e o contorno de cookies guardam estado. O ganho vem de baixar enquanto o outro é CORTADO.
- Se o próximo não chegar a ser baixado de verdade (ficou pra "Precisam de você", já estava no acervo, ou a fila mudou de ordem porque você enfileirou outro disco na frente), o arquivo antecipado é **apagado**. Se o antecipado falhar, o álbum é baixado na vez dele, como sempre, com as mesmas conferências de qualidade.
- Com a fila pausada, nada é antecipado. Sobras de uma abertura anterior são apagadas ao abrir.

Testado: `teste_antecipado.py` (19 conferências): só disco único é antecipado, sem baixar duas vezes, espera o que está em andamento, descartar no meio do download apaga quando termina, falha no antecipado, troca de próximo; e o trabalhador da fila de verdade com 4 itens (um deles indo pra "Precisam de você"): cada disco baixado uma vez, o seguinte começa a baixar junto com o corte do anterior, downloads nunca simultâneos, nada sobra na pasta, e a fila termina com 3 feitos e 1 recusado. Todos os testes anteriores passam. A interface não mudou, então o tutorial continua o da 12.3.

## VERSÃO 12.7

### CZ. Groq (IA) usado de verdade, sempre só como sugestão (PLANO.md, item 8)

Antes, o Groq só entrava em dois casos raros, e duas funções que o usariam nunca eram chamadas. Agora ele ajuda em três pontos (`groq_ajuda.py`), e em todos quem confirma é outra coisa:
- **Álbum que o título não traz** ("Wes Montgomery (Jazz)"): se nem a descrição tem o álbum num formato reconhecível (12.4), o Groq lê título + descrição e sugere artista/álbum pra BUSCAR. Quem confirma é o Discogs, pela nota de identificação. Sugestão de álbum que não está escrito no título nem na descrição é descartada (o Groq pode inventar).
- **Nome de faixa de playlist difícil**, quando a comparação normal (12.4) falha: o Groq diz qual faixa do Discogs é o vídeo. Só vale se a **duração do vídeo** confirmar (a mesma tolerância da conferência de duração). Sem a duração, ou com duração diferente, fica o título do vídeo, como antes.
- **Ordem das faixas daquele vídeo**, lida da descrição: quando a edição escolhida não encaixa no áudio (12.5), as faixas do Discogs na ordem que a descrição lista viram mais uma opção de corte, usada só se ENCAIXAR nos silêncios. Se os padrões de sempre já leram a lista (chapters/descrição), nem precisa do Groq.

Regras: não ouve áudio (não corta nada); nunca decide sozinho; perguntas iguais não se repetem na mesma abertura; ao receber "limite atingido" do plano gratuito, fica 10 minutos sem perguntar e avisa uma vez. Cada resposta vai pro arquivo de log (`[AVISO] Groq (...) respondeu: ...`). O log da abertura diz pra que o Groq é usado. O texto antigo "Groq (apoio técnico de corte)" já tinha saído na 12.2.

Testado: `teste_groq.py` (19 conferências, com um Groq simulado): leitura do álbum, cache, álbum inventado descartado, escolha de faixa, ordem da descrição, limite do plano gratuito (pausa e aviso único), sem chave nada é perguntado; no fluxo, a sugestão vai pra busca no Discogs e, sem Groq, segue como antes; faixa de playlist aceita só com a duração confirmando (e o Groq nem é perguntado quando a comparação normal já casa); ordem da descrição pelos padrões e pelo Groq cortando com os nomes certos, e uma ordem errada do Groq recusada pelo encaixe (nada sai com nome trocado). Abertura conferida com a janela: a linha do Groq aparece, e a chave não aparece nem na tela nem no arquivo. Todos os testes anteriores passam. A interface não mudou, então o tutorial continua o da 12.3.

### DA. Pequeno

- Disco sem durações no Discogs que chega ao passo "silêncios + nomes pela duração" (12.5) agora vai pra "Precisam de você" com o motivo certo ("o Discogs não informa as durações deste disco…"). Antes dizia "as durações não casam". Teste novo em `teste_encaixe.py`.

## VERSÃO 12.8

### DB. Código organizado e documentado (PLANO.md, item 5, último tópico)

Nada muda na tela nem no corte: os 18 arquivos de teste passam, e o ponta a ponta sai idêntico à referência da 12.1. O mapa do código está no novo **`ARQUITETURA.md`** (o caminho de um álbum, o papel de cada arquivo, onde mexer pra mudar cada coisa).

- **main.py (11,5 mil linhas) virou um ponto de entrada de 40 linhas** e módulos de um assunto cada: janela, log, fila, modo álbum, modo playlist, escolha da edição, corte (análise, estratégias, álbum), catálogo e pontuação. O código movido foi conferido linha a linha pela árvore sintática.
- **Código morto removido** (~3.500 linhas): cinco módulos que ninguém chamava (`ai_analyzer`, `search_manager`, `audio_processor`, `hybrid_silence_detector`, `mega_detector_v5_1`) e dezenas de funções sem uso.
- **Multi-fonte antigo trocado por um caminho simples** (decisão do usuário). Quando você manda baixar uma pendência "não encontrado", o programa tenta, nesta ordem: Discogs de novo (aceita qualquer nota, porque você decidiu), capítulos do vídeo, tracklist com tempos na descrição, MusicBrainz e, por fim, só os silêncios ("Track 1, Track 2..."). **Saíram o Selenium/Chrome, o Last.fm, o Apple Music e o painel "Música" do YouTube**, e com eles `metadata_hunter_voting.py`, `api_cache.py` e `description_tracklist_extractor.py`. No lugar ficaram `catalogo.py` (Discogs + MusicBrainz) e `pontuacao.py` (notas). As pistas do vídeo (capítulos e descrição) agora vêm do que o yt-dlp já trouxe, sem outra consulta ao YouTube. `requirements.txt` e `main.spec` não instalam mais selenium, webdriver-manager, beautifulsoup e lxml.
- **As 5 estratégias de corte ficaram** (decisão do usuário), só organizadas e documentadas no topo de `corte_estrategias.py`. A única mudança nelas: a "segunda opinião" sobre uma faixa isolada consulta só o MusicBrainz (as outras fontes não existem mais).
- **Comentários e docstrings reescritos**: o que cada coisa faz e por quê, em poucas linhas, sem o histórico de conversa. Histórico continua aqui no MUDANCAS.md. Cores num lugar só (`ui_util.Cores`). Código repetido juntado em `saida.py` (nome da pasta, download com novas tentativas, capa).
- **Estado da janela simplificado**: sumiram as flags do tempo em que havia dois "donos" do processamento (`pending_processing`, `between_albums_idle`, `processing`, "modo convidado"...). Com o trabalhador único, o botão de pausa só tem três estados: Pausar fila / Retomar fila / Retomar (N).

### DC. Correções achadas na arrumação

- **Bloco perigoso removido**: no início de cada álbum, o programa apagava a pasta de `cache_directory`, com um caminho fixo de outro computador como padrão (`C:\Users\<outra pessoa>\...`). Com a configuração vazia, isso apagava a pasta atual — foi o que um teste antigo fez com a pasta `testes/`. O cache de APIs também saiu.
- **Capa dentro dos MP3 do modo álbum**: a capa era salva como `cover.jpg`, mas nunca entrava nos arquivos — o ffmpeg recusava gravar em `.mp3.tmp` sem o formato explícito, e o erro era engolido. Agora entra (teste novo).
- **Gênero (TCON) no modo álbum**: o Discogs trazia o gênero, mas ele se perdia antes do corte. Agora é gravado, como já era no modo playlist.
- **Fallback por capítulos com o nome certo**: quando o corte pelo Discogs falhava e os capítulos do vídeo salvavam o álbum, as tags saíam como artista/álbum "Unknown". Agora levam o artista e o álbum identificados.
- **Erro no meio de uma playlist** contava como "feito" na fila. Agora conta como falha, com o local do erro no log. O arquivo `.playlist_progress.txt` (do tempo em que várias playlists rodavam numa chamada só) saiu: a fila já guarda o progresso. A janela "Precisam de você" não abre mais sozinha ao fim de cada playlist.
- **Pendência de playlist com baixa confiança** agora usa a tracklist oficial e o gênero (antes ia só com artista/álbum/ano, e os nomes das faixas vinham do título do vídeo).
- `except:` sem tipo trocados por `except Exception:` (não engolem mais o Ctrl+C).

Testado: `teste_caminho_simples.py` (28 conferências) cobre a ordem do caminho sem Discogs (Discogs, capítulos, descrição com inícios ou com durações, MusicBrainz, silêncios), a falta de Selenium e dos módulos antigos, as pistas do vídeo, a ida e volta dos dados pras pendências, o nome da pasta, a capa embutida, as tags do corte de álbum, a playlist (nota baixa, nº de faixas diferente, uma faixa que falha) e a fila (despacho por tipo e erro dentro da playlist). Janela aberta e conferida (igual à 12.7). A interface não mudou, então o tutorial continua o da 12.3.

## VERSÃO 12.9

### DD. Groq com o modelo novo

O Groq aposentou o modelo `llama-3.3-70b-versatile` em 16/08/2026, e toda pergunta passou a dar erro 404 ("Groq: não respondeu (NotFoundError…)"). Agora o programa usa `openai/gpt-oss-120b`, que é o substituto indicado pelo Groq. Se um modelo sair do ar, ele passa sozinho para o próximo da lista (`openai/gpt-oss-20b`, depois o antigo), avisa uma vez no log e continua com ele até fechar. Os modelos gpt-oss "pensam" antes de responder, então o pedido vai com raciocínio curto e escondido e com folga de tokens; sem isso, a resposta poderia sair vazia. A regra continua a mesma: o Groq só sugere, e quem confirma é o Discogs, a duração ou o encaixe.

### DE. "Precisam de você": Corrigir busca

Novo botão **✏️ Corrigir busca**, que funciona com um item selecionado. Ele abre uma caixinha com o artista e o álbum atuais. Você corrige (por exemplo, quando o título do vídeo não traz o nome do álbum) e clica em **Buscar de novo**. O que tinha sido achado antes é descartado e o álbum entra na fila. Na vez dele, a busca no Discogs é refeita com os nomes digitados e aceita qualquer nota, porque você decidiu. Se o Discogs não achar, segue o caminho da 12.8: capítulos, descrição, MusicBrainz e silêncios. Vale para vídeo e para playlist. O arquivo de log registra a correção (`[PENDENTE] busca corrigida pelo usuário`).

### DF. Pequenas melhorias

- **Limite de pedidos do Discogs**: um álbum que foi para "Precisam de você" só porque o Discogs não respondeu volta sozinho para a fila depois de 10 minutos, até 3 vezes por abertura. Ele entra como "nova tentativa", na frente do canal. Se agora a nota for baixa, continua pendente, mas com o motivo certo. A fila não é iniciada sozinha por isso: o álbum só espera a vez dele.
- **Tempos com hora na descrição** ("1:02:15 Faixa") agora são lidos. Antes, álbuns com mais de 1 hora perdiam essa pista, porque o "1:" era ignorado. Traços e barras antes do nome ("03:20 - Faixa") também saem.
- **Medidas do áudio uma vez por álbum**: decodificação, volume, duração e silêncios do disco inteiro passam a ser reaproveitados por todas as tentativas de corte do mesmo álbum (capítulos, edição que encaixa, silêncios + nomes). Antes, cada tentativa decodificava o áudio de novo, o que leva uns 7 s num álbum em opus. Os cortes saem idênticos aos da 12.8: conferi em 10 discos, em WAV e em opus.
- **Tags num lugar só** (`metadata_manager.gravar_tags`, ID3 v2.3): o modo álbum e o modo playlist gravam as mesmas tags do mesmo jeito. Antes, o álbum gravava pelo ffmpeg (v2.4), a capa entrava por outra cópia do arquivo e os IDs do Discogs eram gravados em v2.4; agora é tudo v2.3, que o Windows lê melhor. A capa não é duplicada se for embutida de novo.
- **config.json antigo convertido ao abrir**: o bloco "apis" (inclusive o Last.fm), a pasta de saída repetida dentro de "settings" e três ajustes que nada lia saem. Uma chave antiga só preenche uma chave nova que esteja vazia. O arquivo original fica guardado em `config.json.antigo`. O log diz o que mudou, sem mostrar as chaves.
- **Bitrate mínimo inválido** nas Configurações agora volta para 80 kbps, o padrão anunciado. Antes voltava para 128.
- **Cabeçalho**: em janela estreita, o botão "Configurações" saía cortado. Agora quem encolhe é o subtítulo, que ficou mais curto ("Álbuns do YouTube separados em faixas").
- **Mensagens do log** sem números de versões antigas ("Estratégia v10.8" virou "Estratégia CONSENSO", e assim por diante). Restos de código das estratégias de corte foram tirados: uma conferência repetida, variáveis e um parâmetro sem uso.

Testado: `teste_melhorias.py` (28 conferências) e as novas conferências em `teste_groq.py` (modelo fora do ar, raciocínio curto e o pedido real da biblioteca do Groq interceptado sem rede). Todos os testes passam. Os cortes dos 10 discos de conferência, em WAV e em opus, saem idênticos aos da 12.8. A interface mudou (botão novo e subtítulo), então o tutorial foi refeito: `Tutorial_DiscoFacil_12.9.pdf`.

## VERSÃO 12.10

### DG. Disco sem durações: nomes pela ordem (palpite marcado)

Caso do "Luiz Loy e Sua Juventude Musical" (1962). O Discogs achou o disco (12 músicas), mas nenhuma das duas edições cadastradas informa as durações, e o MusicBrainz não tem o álbum. Os silêncios do áudio davam 14 pedaços, e o programa gravava "Track 1…14".

Os 2 pedaços a mais eram pausas dentro de músicas: a faixa 1 (72 s, metade de "Delilah Jones") e a faixa 10 (36 s, começo de "Samba de Uma Nota Só"). O silêncio dessa segunda pausa foi o mais fraco do disco: só 2 dos 3 detectores o acharam, e ele durou 1,1 s. Você ouviu e confirmou as duas.

O que o programa faz agora quando não há duração em lugar nenhum (`encaixe.juntar_pedacos_curtos`):
- Se sobram poucos pedaços, pega o mais curto e o junta ao vizinho do lado da fronteira mais fraca (menos detectores, silêncio mais curto). Repete até dar o número de músicas e nomeia pela ordem do Discogs. Com o mesmo número de pedaços e de músicas, nomeia direto pela ordem.
- Só junta quando sobram no máximo 3 pedaços (e até 1/4 das músicas), e quando cada pedaço juntado tem menos de 60% da duração mediana do disco: uma pausa, não uma faixa de verdade. Fora disso, ou com menos pedaços que músicas, continua como antes: vai para "Precisam de você" e, se você mandar processar mesmo assim, sai "Track N".
- **É palpite, e vai marcado**: o log mostra quais pedaços foram juntados ("🔗 pedaços 1+2 juntados (1:12 + 2:13) → 'Delilah Jones'"), o arquivo da rodada registra em `[AVISO] nomes por ordem, sem durações (conferir)`, e cada faixa recebe a tag `TXXX:DISCOFACIL_NOTA = nome por palpite (disco sem durações) - conferir`.
- Vale no corte automático e também quando você manda processar mesmo assim uma pendência de disco sem durações: antes de cair em "Track N", o programa tenta o palpite.

Também: o log "✓ Separação concluída: N faixas" passa a contar os arquivos gravados (antes dizia 12 com 14 arquivos e 0 num disco sem Discogs).

Testado: um "Luiz Loy" sintético (12 músicas, duas com pausa no meio, 14 pedaços) sai com as 12 músicas certas e inteiras nos dois caminhos, automático e "processar mesmo assim", com a marca no log, no arquivo da rodada e na tag. Também conferi os casos em que o programa não junta: pedaço sobrando de duração normal, sobra demais, e menos pedaços que músicas. Os Boêmios (8 pedaços = 8 músicas, sem durações) agora sai com os nomes pela ordem. Todos os testes passam, e os cortes dos discos de conferência saem idênticos aos da 12.8. A interface não mudou, então o tutorial continua o da 12.9.

## VERSÃO 12.11

### DH. Ray Charles "Forever" (2013): edição errada e um "Track 7" de 34 s

O vídeo "Ray Charles – Forever – 2013" foi identificado como a coletânea **Forever Gold** (1999, 14 faixas). Dois motivos: o título só era comparado num sentido ("Forever" aparece inteiro em "Forever Gold"), e as duas coletâneas somam uns 49 minutos. No corte, 6 das 13 trocas de faixa não tinham silêncio nenhum por perto, e o disco foi para "Precisam de você" como "corte não bateu". Mandado processar mesmo assim, o último recurso completou o número do cadastro errado com uma "queda de volume" 30 s depois de um silêncio de verdade, e saiu um pedaço de 34 s com o começo da música seguinte.

- **Título comparado nos dois sentidos** (`pontuacao.palavras_a_mais`): palavras do título do Discogs que não estão no título do vídeo tiram até 20 pontos ("Forever Gold" contra "Forever": 'gold'). Assim um disco com o título exato passa na frente. Não contam: o que está entre parênteses ou colchetes ("Kind Of Blue (Legacy Edition)"), palavras de edição (remastered, deluxe…) e o nome do artista. A nota de identificação mostra a palavra a mais no log.
- **Ano de coletânea**: numa coletânea, o ano do título do vídeo bem diferente do ano do cadastro (mais de 2 anos) tira 15 pontos. Em disco normal não pesa, porque reedição costuma trazer o ano original no título.
- **Pendência "Talvez outro disco"** (motivo novo na tabela): quando o corte é recusado e menos da metade das trocas de faixa do Discogs cai num silêncio do áudio, o motivo diz "Provavelmente é outro disco… use ✏️ Corrigir busca", em vez de "corte não bateu". Processar mesmo assim continua possível e funciona como antes (nomes genéricos).
- **Queda de volume não vira faixa curta**: no último recurso, uma fronteira achada só por queda de volume não pode deixar pedaço com menos de 60 s. Além disso, o número de faixas de um cadastro COM durações (que já não encaixou) não é mais usado como meta para pedir cortes extras. Para disco SEM durações (Luiz Loy, Os Boêmios), o número continua valendo.

Testado: num disco sintético com uma pausa curta e funda 30 s depois do começo de uma música, a 12.10 dava 7 pedaços, um deles de 31 s; a 12.11 dá os 6 certos, tanto com cadastro errado com durações quanto com cadastro sem durações. Também testados: "Forever" pontua bem acima de "Forever Gold"; edição entre parênteses não conta como palavra a mais; o ano não pesa fora de coletânea; e a pendência "talvez outro disco" sai com 4/13 trocas num silêncio, mas não com 8/13. Todos os testes passam, e os cortes dos discos de conferência (WAV e opus) continuam idênticos aos da 12.8. A janela só ganhou um rótulo novo de motivo, então o tutorial continua o da 12.9.

## VERSÃO 12.12

### DI. Edição reconhecida pelo áudio (Ray Charles "Forever", de novo)

Com a 12.11, o disco foi escolhido errado de novo, mas o log mostrou por quê. A busca no Discogs trouxe 5 edições de "Forever" (2013) e o "Forever Gold". As de "Forever" perderam porque a soma das durações delas não batia com o vídeo. O motivo: o vídeo não tem a última faixa do CD (13 faixas no CD, 12 no vídeo). Os 12 pedaços cortados pelos silêncios batem, um a um, com as 12 primeiras faixas de "Forever" (diferença de 1 a 4 s). O "Forever Gold" só coincidia na soma, com 2 de 13 trocas de faixa num silêncio. O programa recusou e mandou para "Precisam de você" como "Talvez outro disco" (12.11), sem olhar as outras edições que já tinha nas mãos.

Agora, quando o disco escolhido não encaixa, o programa faz um último passo antes de desistir (`escolha_edicao._reidentificar_pelo_audio`):
- Corta o áudio só pelos silêncios e procura, entre os candidatos da busca **com exatamente o título do vídeo**, um cujas durações casem com os pedaços, **cada um** dentro de 4 s ou 3%. É a mesma regra que garante que nenhum nome sai trocado.
- Aceita o vídeo **sem a(s) última(s) faixa(s)** do cadastro, se a soma das primeiras fechar com o áudio. O log diz quais faltam.
- Também tenta sem as fronteiras achadas só por queda de volume (pausa dentro da música).
- Achou: corta com essa edição, numa pasta com o nome dela, com capa e IDs dela. O arquivo da rodada registra `[FONTE] outra edição, casada pelo áudio…`.
- Vale no automático e também em "processar mesmo assim": antes de cair em "Track N", o programa tenta essa edição.

Também: o título das edições do Discogs agora sai sem o espaço sobrando do fim ("Forever ").

Testado com um "Forever" sintético (12 músicas no vídeo, 13 no cadastro, o "Forever Gold" escolhido primeiro com a mesma duração total). Nos dois caminhos, automático e "processar mesmo assim", sai a pasta "Ray Charles - Forever (2013)" com as 12 faixas certas, e o log diz que falta a 13ª. Todos os testes passam, e os cortes dos discos de conferência continuam idênticos aos da 12.8. A interface não mudou.

## VERSÃO 12.13

### DJ. Faixas de mesma duração não travam mais o reconhecimento pelo áudio

Na 12.12, o Ray Charles "Forever" foi recusado mesmo com a edição certa entre os candidatos. Os 12 pedaços do vídeo batiam com as 12 primeiras faixas de "Forever" (2013) com 1 a 4 s de diferença. Mas o disco tem faixas de mesma duração: a 2 e a 4 têm 3:42, e a 6 e a 7 têm 4:09 e 4:08. Ao casar pedaços com faixas, a escolha entre as duas iguais era arbitrária. Às vezes saía "pedaço 2 = faixa 4 e pedaço 4 = faixa 2", e a conferência de segurança ("duas faixas parecidas fora de ordem pode dar nome trocado") recusava o disco inteiro.

Agora, em empate de duração, vale a ordem do disco: o pedaço 2 fica com a faixa 2 (`encaixe.casar_por_duracao`). A ordem só muda quando a duração realmente aponta outra faixa, como no Nico Assumpção, que continua funcionando. O log também diz quando a busca por outra edição pelo áudio não achou nenhuma.

Testado com os números de verdade do log (pedaços medidos × "Forever" 2013): a 12.12 recusava, e a 12.13 casa as 12 faixas na ordem. Todos os testes passam, e a interface não mudou.

## VERSÃO 12.14

### DK. Disco sem nenhuma duração: o Deezer as dá (Neco, "Coquetel Bossa Nova")

O Discogs tem as 12 músicas do "Coquetel Bossa Nova", mas sem nenhuma duração, e o MusicBrainz também não tem o álbum. O áudio só tem 6 pausas claras, então saíam 7 pedaços "Track N", um deles de 14 min com umas 5 músicas grudadas.

Agora, quando o disco não tem duração nenhuma, o programa consulta o Deezer, que tem API pública e não pede chave (`catalogo.Catalogo.deezer`, `processo_album._duracoes_do_deezer`). O Deezer só fornece as **durações**: os nomes continuam os do Discogs. Ele só entra se:
- o álbum tem o mesmo título e artista e o mesmo nº de faixas;
- **cada** título do Discogs acha a sua faixa no Deezer (aceita diferença de acento, "(Remastered)" e ordem trocada). Se um título fica sem par, o Deezer não é usado;
- a soma bate com o áudio (até 20 s ou 5%). Se não bater, pode ser outra gravação, e o Deezer também não é usado.

Com as durações, o disco segue o caminho normal (encaixe, corte com durações). O log diz "🎵 Deezer: durações das N faixas…", e o arquivo da rodada registra `[FONTE] durações do Deezer`. Quando não dá, o log diz o motivo e o disco segue como antes.

Não deu para testar contra o Deezer de verdade daqui, porque o ambiente de testes não acessa o site. O cliente segue o formato público da API e foi testado com respostas simuladas.

### DL. "Processar mesmo assim" com músicas emendadas (Tocando Victor Assis Brasil)

O disco tem 7 músicas. O corte pelas durações achou silêncio em 5 das 6 trocas de música, mas a 1→2 (Waltz for Phil → Arroio) não tem pausa. No automático, o programa recusou, o que estava certo. Mas quando você mandou processar, ele caiu no consenso, que esquece o Discogs e corta em toda pausa. Saíram 11 "Track N", com 2 pedaços de 30 s (pausas no começo de "Balada for Nadia") e cortes no meio de 3 músicas.

Agora, **só quando você manda processar**, o corte pelas durações estima as poucas fronteiras sem silêncio antes de desistir (`SmartCutter._estimar_fronteiras`):
- A fronteira vai pela proporção das durações entre os cortes confirmados vizinhos, no ponto de menor energia a até 8 s.
- O limite é de no máximo 2 fronteiras e 1/3 delas. Cada buraco precisa de âncora dos dois lados (corte confirmado, começo do disco, ou fim do arquivo quando a soma bateu). Fora disso, segue como antes.
- As duas faixas da emenda ficam marcadas para conferir: no log, no arquivo da rodada (`[AVISO] corte estimado pela duração`) e na tag (`TXXX:DISCOFACIL_NOTA`).
- No automático nada muda: fronteira sem silêncio continua mandando o disco para "Precisam de você".

### DM. Consenso: nenhum pedaço menor que 60 s quando se sabe quantas músicas o disco tem

É a mesma regra que a 12.11 criou para a queda de volume, agora valendo também para os silêncios. Se dois cortes vizinhos deixam um pedaço menor que 60 s, sai o mais fraco dos dois: vale primeiro o que já foi confirmado pelas durações, depois o que tem mais votos, depois o silêncio mais longo (`SmartCutter._tirar_pedacos_curtos`). Sem cadastro nenhum, nada muda. No Luiz Loy, a pausa de 35 s dentro do "Samba de Uma Nota Só" agora sai já no consenso, e o resultado continua o mesmo: 12 músicas com nome.

### DN. Compacto com o mesmo nome da coletânea ("Can't Play A Playgirl")

O vídeo é a coletânea "Can't Play A Playgirl (1960's Girl Goodies Lost & Found)", com 34 faixas e 77 min. O programa escolheu o compacto das Jillettes com o mesmo nome, que tem 2 faixas e 5 min, e cortou o vídeo inteiro em 2 arquivos. Havia dois motivos:
- **A coletânea nem entrou na disputa.** Candidato com mais de 30 faixas era descartado como box set. Agora o limite cresce com o vídeo: 1 faixa a cada 100 s, até 60 (77 min → 46). O log diz quando algum candidato fica de fora por isso (`catalogo.limite_de_faixas`).
- **Duração muito diferente não pesava.** O compacto soma 6% do vídeo e mesmo assim ficava com 63% de identificação, só pelo título. Agora, se a duração total do cadastro fica a mais de 60% de distância do vídeo (menos de 40% ou mais de 160% dele), o candidato perde 40 pontos, na pontuação e na identificação: é outro disco (`pontuacao.DURACAO_OUTRO_DISCO`). Um LP num vídeo com 2 LPs (50%) não é afetado.

Conferido nos logs que você mandou (35 buscas): só a do "Playgirl" muda de escolha. As outras continuam iguais.

Testado com discos sintéticos: Neco, que sai sozinho com as 6 músicas nomeadas pelas durações do Deezer; Tocando, que no automático continua recusado e quando você manda processar sai com 7 músicas com nome, a emenda a 1 s do lugar e as 2 faixas marcadas; e o Luiz Loy, que continua igual. Também com os números do "Playgirl". Todos os testes passam, e os cortes dos discos de conferência continuam idênticos aos da 12.8. A interface não mudou.

### DO. Tutorial refeito para quem não é do ramo

O tutorial tinha as telas, mas explicava pouco, e as janelas de ajuda (?) nunca apareciam nele. O novo (`Tutorial_DiscoFacil_12.14.pdf`, 10 páginas) continua curto, mas agora tem:
- o que o programa faz e o caminho em 4 passos;
- as duas abas das Configurações, com cada campo explicado e o valor recomendado, o que é uma "chave" e quais são obrigatórias;
- as janelas de ajuda: a geral, a da chave do Discogs (como conseguir) e a da confiança mínima;
- a janela principal parte por parte, incluindo as cores do log;
- os 3 modos com o tipo de link de cada um;
- as janelas **Fila** e **Buscar Playlists**, que não estavam no tutorial;
- o que fica na pasta (nomes, tags, capa, "Track N", faixas a conferir, disco já no acervo);
- em "Precisam de você", uma tabela com cada motivo, o que ele quer dizer e o que fazer.

Dois textos de ajuda do programa estavam desatualizados e foram corrigidos:
- O "?" geral falava em "Álbuns pendentes (botão no rodapé)". Agora diz "Precisam de você".
- O "?" da chave do YouTube não dizia que **Buscar Playlists** precisa dela.

## VERSÃO 12.15

### DP. Ray Charles "Ingredients In A Recipe For Soul": músicas emendadas com o nome certo

O disco foi identificado certo (10 faixas, soma a 34 s do vídeo), mas as músicas emendam quase sem pausa. O corte pelas durações confirmou 5 das 9 trocas. As outras 4 estavam em dois buracos de 2, com corte confirmado dos dois lados. A estimativa da 12.14 aceitava no máximo 2, então o programa caiu no consenso, que cortou em quedas de volume no meio das músicas. Saíram 6 "Track N", um de 13 min.

Agora, quando você manda processar:
- A estimativa pela duração vale para **até metade das trocas**, desde que no máximo **2 seguidas**, com corte confirmado dos dois lados. Assim o erro fica preso entre dois cortes de verdade. Todas as faixas das emendas ficam marcadas "conferir" (log, arquivo da rodada e tag).
- **Disco com durações não sai mais em "Track N" cortado só pelas pausas.** O consenso só é aceito se der o mesmo número de músicas do cadastro, e aí as faixas saem com os nomes. Se não der, o disco fica em "Precisam de você" em vez de sair com cortes no meio das músicas.
- "Track N" fica só para disco sem duração nenhuma.

### DQ. Os Cobras: mais lugares para achar as durações

O Discogs tem as 11 músicas certas (11/11 com a descrição do vídeo), mas sem durações, e a descrição não tem os tempos. O Deezer achou 3 discos "Os Cobras", mas nenhum com as 11 faixas exatas, e por isso recusou todos. Agora:
- **Edição com faixas bônus a mais serve.** O que vale é cada uma das músicas do Discogs achar a sua pelo título; as faixas a mais ficam de fora. A edição com o número exato continua tendo preferência. Quando nenhuma serve, o log diz quantas faixas tinham as encontradas.
- **iTunes/Apple Music** entra depois do Deezer: é uma busca pública, sem chave, primeiro na loja do Brasil e depois na dos EUA. As regras são as mesmas: nomes do Discogs, todos os títulos casados e a soma batendo com o áudio (`catalogo.Catalogo.itunes`, `processo_album._duracoes_de_fora`).

Como na 12.14, não deu para testar contra o Deezer e o iTunes de verdade daqui. Os clientes seguem o formato público das APIs e foram testados com respostas simuladas. Se o Os Cobras não estiver em nenhuma das duas lojas, ele continua sem nomes.

Testado com um "Ingredients" sintético (10 músicas, 4 trocas sem pausa em 2 buracos de 2): quando você manda processar, saem as 10 músicas com nome, a no máximo 5 s do lugar, e as 6 faixas das emendas marcadas. Com 3 trocas seguidas sem pausa, o disco fica pendente, sem "Track N". Também com o Deezer recusando e o iTunes respondendo. O tutorial foi atualizado na tabela de "Precisam de você". Todos os testes passam, e os cortes dos discos de conferência continuam idênticos aos da 12.8. A interface não mudou.

## VERSÃO 12.16

### DR. Nunca trocar por outro disco (Milton Banana "Vê", Os Cobras)

O programa identificava o disco certo, cortava e, depois do corte, "reavaliava" a escolha comparando as durações dos pedaços com as edições guardadas da busca, que incluíam **outros discos**. O "Vê" (sem durações no Discogs) virou "Aos Amigos Tom, Chico e Vinicius" (outro LP do Milton Banana, que por acaso encaixava), com os nomes juntados desse outro disco ("Chega De Saudade / Desafinado…"), a capa e os IDs dele. O "Os Cobras" virou "Cobras Criadas", de outro artista.

Agora existe uma regra única de "é o mesmo disco?" (`pontuacao.mesmo_disco`), usada em **todo** lugar onde o programa troca de edição: a reavaliação depois do corte, as outras edições no encaixe, o MusicBrainz e a edição reconhecida pelo áudio. A regra:
- Mesmo master do Discogs = mesmo disco. Masters **diferentes** = discos diferentes, mesmo com o nome igual (artista com vários LPs com o nome dele).
- Sem master de um dos lados: título equivalente e artista parecido. "Vol. 2", "II" e "Ao Vivo" contam até entre parênteses; "(2013 Remaster)" e as palavras de edição não contam. No artista, "Trio", "Orquestra" e "and his" não contam ("Zimbo Trio" ≠ "Tamba Trio"); "V.A." só bate com "Various".
- Trocar de edição exige ainda que a nova passe na identificação contra o vídeo, com a sua confiança mínima. O ano continua o do lançamento, não o da reedição.
- Os nomes só vão para os arquivos já cortados com prova pela duração: o mesmo número de faixas com cada pedaço casando com a sua, ou a soma de faixas vizinhas fechando com cada pedaço. Antes bastava ter uma faixa a mais ou a menos, e os nomes saíam deslocados.

### DS. Deezer/iTunes: o log mostra o título que não bateu

O Os Cobras foi achado nas duas lojas, mas algum título não bateu com o do Discogs, e o log não dizia qual. Agora o log mostra os títulos sem par e o que a loja tinha no lugar. Se a loja tem o mesmo número de faixas e todos os outros títulos casam **na mesma posição**, a que sobrou só pode ser aquela e vale pela posição (no máximo 2, e no máximo 1/4 do disco).

### DT. Tempos nos comentários do vídeo

Muito vídeo de disco inteiro tem um comentário com "0:00 Música 1 / 3:12 Música 2…". O programa lê os comentários mais curtidos (`downloader.comentarios`) em dois casos: quando o disco não tem duração em lugar nenhum (antes do corte) e quando o corte falha, por exemplo com músicas sem pausa (antes de desistir). Disco que corta pelo caminho normal nem consulta, então nada fica mais lento.

A lista só vale se for **deste** disco:
- o mesmo número de faixas do Discogs;
- pelo menos 80% dos títulos batendo na mesma posição, o primeiro e o último inclusive, e nunca dois seguidos sem bater (assim, uma lista que pulou uma música não desloca os nomes);
- se o Discogs tem durações, as durações parecidas;
- linhas como "Total 40:20" e "Side B" não contam.

O corte vai para a pausa real a até 6s do tempo do comentário; sem pausa, para o ponto de menor energia a até 3s. Se o áudio tem pausas claras e os tempos não caem nelas, a lista é de outro upload e é recusada. As faixas sem pausa perto ficam marcadas "conferir". Os nomes são os do Discogs. O log diz "💬 …", e o arquivo da rodada registra `[FONTE] tempos de um comentário do vídeo`.

### DU. Botão "⏱ Informar tempos" em "Precisam de você"

Para quando você faz questão de um disco que o programa não conseguiu separar sozinho: cole a lista das músicas com o tempo de cada uma, uma por linha. Vale o início ("0:00 Nome") ou a duração ("Nome 3:12"). O disco entra na fila e é cortado nesses tempos, ajustados à pausa mais próxima e sem marca "conferir", porque os tempos são seus. O nome escrito em cada linha decide qual faixa é; o Discogs só dá a grafia oficial. Linha sem nome usa o Discogs na mesma posição, se o número de linhas bate. Os botões de ação da janela foram para uma linha própria, para caberem todos.

### DV. Revisão independente

Um segundo agente, que não escreveu o código, revisou todos os pontos onde o programa troca de disco ou dá nomes às faixas. Foram corrigidos:
- A regra de mesmo disco (acima) estava frouxa demais em volumes, "ao vivo", masters diferentes e artistas.
- No "processar mesmo assim" de disco com durações, o consenso só dá os nomes pela posição se **cada** pedaço tiver a duração da sua faixa. Antes, duas músicas grudadas e um corte a mais nos aplausos deslocavam os nomes do meio.
- Capítulos do vídeo, quando o Discogs não tem durações: o nome oficial só vai para o capítulo de mesmo nome (um capítulo "Intro" a mais deslocava todos).
- A estimativa pela duração é recusada quando o trecho entre os dois cortes confirmados não comporta as faixas (música a mais ou a menos no vídeo).
- Lista de tempos com introdução ("0:45 Música 1…") é entendida como inícios, não como durações; e "0:00 - 3:12 Nome" sai com o nome limpo.

Ficou como estava, por decisão anterior sua (12.10): o disco sem durações em lugar nenhum, com o número de pedaços batendo, sai com os nomes pela ordem, marcados "conferir".

Os logs que você mandou viraram testes com os números de verdade (`testes/teste_casos_reais.py`: Vê, Os Cobras, Playgirl, a regra de mesmo disco e cada achado da revisão). Contra a 12.15 esses testes falham; na 12.16 passam. Todos os testes passam, e os cortes dos discos de conferência continuam idênticos aos da 12.8. O tutorial ganhou o botão novo e a explicação dos comentários.

### DW. Correções de 04/10 (ainda 12.16, sem trocar o número)

- **Conexão com o Discogs que cai não é mais "álbum não encontrado".** No log de 04/10, o "Vê" nem foi procurado: o Discogs fechou a conexão e o disco foi para "Precisam de você" como "não achado no Discogs", com 0%. Agora isso vira "Discogs não respondeu (a conexão caiu)" e volta sozinho para a fila em 10 minutos, como o limite de pedidos. Vale também quando a conexão cai no meio da leitura das edições.
- **Títulos do vídeo que não batem derrubam a confiança.** O "Milton Banana - 1967" foi para o LP de 1973 com 100%, só porque a duração batia, mesmo com 0 das 12 músicas da descrição no disco. Agora, se o vídeo lista 4 músicas ou mais e menos de 1/4 delas está no disco, a nota fica em no máximo 40%, e o disco vai para "Precisam de você".
- **Capa que não entra num arquivo aparece no log.** Por exemplo, quando o arquivo está aberto noutro programa. Antes isso ia só para o console. Agora o log avisa quantos arquivos ficaram sem capa e quais, e o arquivo da rodada registra `[AVISO]`.
- **"VA", "V.A.", "V/A", "Vários Artistas" = Various.** O título "V.A. - Can't Play A Playgirl" agora busca no Discogs com o artista "Various", como o Discogs cadastra as coletâneas.

Testado em `testes/teste_casos_reais.py`, com a conexão caindo na busca e na leitura das edições, o "1967" com os títulos reais, a capa num arquivo quebrado e as grafias de "vários artistas".

---

## VERSÃO 12.17

### DX. Tela "Conferir cortes": ouvir o disco e acertar os cortes

Uma janela própria, para ouvir o disco inteiro e conferir cada corte:
- **Desenho do disco inteiro** no alto (clique para ir a um ponto) e o **trecho ampliado** embaixo, com as pausas em cinza e os cortes coloridos: azul = numa pausa, laranja tracejado = estimado pela duração (é o que precisa ouvir), verde = marcado por você.
- **Tocar/Pausar** a partir do cursor, até o fim do disco se quiser. **◀ marca / marca ▶** levam o cursor ao corte anterior ou ao próximo; ◀◀ 10s, 10s ▶▶, início e fim; zoom.
- **✂ Marcar corte** (em destaque, longe do Tocar), **🎧 Ouvir a emenda** (5s antes e 5s depois do corte escolhido), ⇤ 0,5s / 0,5s ⇥ para empurrar, **🧲 Ao silêncio mais perto**, **🗑 Apagar marca**.
- Teclas: espaço toca/pausa, ←/→ andam 1s, Ctrl+←/→ vão às marcas, M marca, Del apaga, E ouve a emenda, Esc fecha.
- **Tabela das músicas**: nome (duplo clique para mudar), início, duração e a do Discogs. Avisos em cima dela: corte faltando (com a faixa longa demais em vermelho), corte sobrando, quantos estão estimados ou "tudo confirmado".
- O som sai pela biblioteca `sounddevice` (nova no `requirements.txt` e no `main.spec`). Sem ela, a tela abre e funciona, só não toca, e diz por quê.

### DY. "✂ Editar" em "Precisam de você"

Novo botão na janela de pendentes, que abre a tela acima para o disco escolhido. O "?" da tela principal também explica o Editar e o Editar disco. O motivo de cada disco que não cortou agora diz que dá para "usar ✂ Editar pra ouvir e acertar os cortes".
- O áudio de um disco que vai para "Precisam de você" fica guardado em **`.audios_pasta_pendencia`** na pasta de saída (o ponto põe a pasta na frente da lista e fora do acervo). Assim, nem o Editar nem o processamento baixam de novo. Se o disco não tem áudio guardado, o Editar baixa uma vez.
- Ao salvar, os cortes viram tempos **exatos**: o disco entra na fila e é cortado exatamente onde você marcou, sem ajuste à pausa, e com os nomes da tabela. O arquivo da rodada registra `[FONTE] cortes do editor`.
- O áudio guardado é apagado quando o disco sai de "Precisam de você" (processado, removido ou descartado).

### DZ. "✂ Editar disco" na tela principal: corrigir disco já cortado

Novo botão na tela principal. Você escolhe a pasta de um disco já cortado (antes da 12.17 também). O programa junta as faixas, abre a mesma tela com os cortes de agora e os nomes das tags, e ao salvar regrava a pasta:
- recorta nos pontos novos (pode juntar duas faixas, separar uma ou mover um corte);
- grava com a mesma taxa (kbps) de antes, as mesmas tags do álbum, o número/total certo, a capa e os IDs do Discogs;
- guarda os arquivos de antes em `.audios_pasta_pendencia/antes_da_edicao/<disco> <data>`, para voltar atrás se quiser.

As faixas são recodificadas uma vez (MP3 só se corta exatamente recodificando).

### EA. Correções desta versão (testes e revisão independente)

Achado nos testes:
- A tabela da tela entrava num laço sem fim ao clicar numa música (a seleção refeita pelo programa disparava outro clique).
- O tocador contava os instantes de espera do disco como música tocada, e o cursor andava à frente do som.
- A linha de botões da tela principal (agora com o "✂ Editar disco") não cabia na largura mínima. A largura mínima agora é calculada pelos botões, com a fonte do computador.

Um segundo agente, que não escreveu o código, revisou o editor. Foi corrigido:
- **Cortes do editor que se perdiam.** Os tempos `#exato` passavam pelo mesmo leitor da lista colada à mão, que pula linhas como "Side by Side", "Lado a Lado" ou "Total Eclipse" e lê "5:15" no nome como tempo. Agora têm leitor próprio. Um corte em 59,9996 s virava "0:00:60.000" e era recusado; agora sai "0:01:00.000". Duas marcas a exatamente 1 s uma da outra faziam o processamento ignorar todos os cortes.
- **Tocar logo depois de outro tocar** (← → seguidos, cliques rápidos) às vezes parava o som sozinho: o ffmpeg do toque anterior se misturava com o novo. Cada toque agora tem o seu.
- **Sem saída de som** (fone tirado, placa ocupada): a tela agora avisa, em vez de não fazer nada.
- **Regravar a pasta com segurança.** Se um arquivo do disco está aberto noutro programa, nada é mexido e o aviso diz qual. Se a troca falhar no meio, os arquivos de antes voltam pro lugar. Tag que não grava interrompe antes de tocar na pasta.
- **A tela só fecha depois de gravar.** Se a gravação falhar, as marcas continuam lá. Salvar sem mudar nada não regrava (MP3 recodificado à toa perde qualidade).
- **Nomes que acompanham os pedaços** no disco já cortado: separar uma faixa dá "Nome" e "Nome (2)", juntar duas dá "A / B" (antes, tudo virava "Track N"). Um nome editado continua na mesma música quando se põe ou tira um corte antes dela.
- **Cada faixa mantém o seu artista e a sua capa** ao regravar (discos feitos de playlist podem ter um por faixa).
- **Esc na caixa do nome** só cancela o nome; antes fechava a tela.
- **Downloads e arquivos de trabalho com nome próprio**: dois ✂ Editar ao mesmo tempo não pegam o áudio um do outro. Sobras de trabalho interrompido (programa fechado no meio) são apagadas na abertura seguinte.
- **Vídeo muito longo**: o desenho do volume é medido aos pedaços, sem carregar o áudio inteiro na memória.

Testado em `testes/teste_editor.py` (69 verificações), com um disco sintético de 10 músicas, três delas emendadas, e um tocador falso no lugar da placa de som. Testa a tela, os botões e as teclas, o corte exato, a regravação de uma pasta, os dois botões novos e cada achado da revisão. O som de verdade não dá para testar aqui: confira no Windows.

Todos os testes passam (22 arquivos), e os cortes dos discos de conferência continuam idênticos aos da 12.8. O tutorial ganhou a seção 8 (a tela, os botões e o salvar), o botão na janela principal e o Editar em "Precisam de você".

---

## VERSÃO 12.18

### EB. O editor tem a última palavra

O que você salva no ✂ Editar é o que sai. Se você apagar um corte, juntar músicas ou deixar menos faixas do que o Discogs diz, o disco sai assim, com os nomes da tabela. Antes, ao mudar o número de pedaços, os nomes viravam "Track N".

Os nomes agora acompanham os cortes:
- juntar duas músicas dá "A / B";
- um corte novo no meio de uma música dá "A (2)";
- marcar de novo um corte apagado devolve os nomes, inclusive os que você tinha escrito;
- mover um corte nunca troca nomes.

Vale também quando o disco abre faltando um corte: assim que você marca o que faltava, os nomes do Discogs entram e passam a acompanhar.

Se os cortes salvos não puderem ser aplicados, o programa não corta o disco "por conta própria" de outro jeito: ele continua em "Precisam de você".

### EC. Guias no desenho: amarelo (Discogs) e roxo (o som muda)

Guias não cortam nada, só ajudam a achar o corte:
- **Amarelo:** onde o Discogs poria cada corte, somando as durações das músicas, com a duração de cada uma escrita em cima. Um tracinho amarelo sem corte perto costuma ser o corte que falta.
- **Roxo:** onde o som muda de repente, sem pausa (outro instrumento, outro andamento). Pode ser a troca de duas músicas emendadas, ou só um solo. O aviso de "faixa longa demais" diz onde estão.

Clicar perto de uma guia leva o cursor exatamente para ela. A tabela do Tk não deixa pintar uma coluna só de outra cor, por isso o amarelo está no desenho e não na coluna "Discogs". A sugestão roxa é só do editor: o corte automático continua igual.

### ED. Nomes: lista de candidatos e "📋 Colar nomes"

- **Duplo clique no nome:** além de escrever, dá para escolher numa lista com os nomes achados no Discogs, nos capítulos, na descrição e nos comentários do vídeo. Os da mesma posição vêm primeiro.
- **📋 Colar nomes:** cole a lista inteira, um nome por linha. Número, lado ("A1") e tempo na frente saem sozinhos, mas só quando a lista é numerada ("99 Luftballons" fica inteiro). Linhas vazias e "Total" não contam.

### EE. Disco que o Discogs não confirmou (o caso Ruth Brown)

No "Ruth Brown - Sotfly", com 0% de confiança, o editor usava o palpite errado do Discogs ("Peaks Iration - Zen Garden", 6 faixas): no título, nos nomes e em "falta 1 corte". Agora, em "Confiança baixa", "Não achado" e "Talvez outro disco", o palpite não entra:
- **Artista, álbum e ano** vêm do título do vídeo, num quadro amarelo na tela para você conferir e corrigir ("Sotfly" → "Softly"). Em "Talvez outro disco", o item guardava o nome do disco errado, e agora também se usa o título do vídeo.
- **Cortes e nomes** vêm dos capítulos, da tracklist da descrição ou de uma lista com tempos num comentário, se houver. Senão, só das pausas, com "Track N".
- **Ao salvar**, o disco é cortado e gravado com o artista, o álbum e o ano da tela, sem o palpite do Discogs. Sem artista ou álbum, a tela pede para escrever.

Se depois você usar "Corrigir busca", a busca nova vale.

### EF. Arquivo de correções do editor

Cada vez que você salva no editor, o programa anota numa linha de `logs\correcoes_do_editor.txt`:
- o que sugeriu e o que você deixou: cortes mantidos, movidos (e quanto), apagados e novos;
- o que havia perto de cada corte: pausa, guia do Discogs, mudança no som;
- os nomes trocados.

O log mostra o resumo, por exemplo "📊 Editor: nas últimas 12 edições, 85% dos cortes sugeridos ficaram onde estavam". De tempos em tempos, mande esse arquivo na conversa de suporte: é com ele que os cortes automáticos serão ajustados. Desliga nas Configurações ("Guardar as correções feitas no ✂ Editar"), e o log do início diz se está ligado.

### EG. O editor abre mais rápido

O volume, os silêncios e as mudanças no som ficam guardados em `.audios_pasta_pendencia\_medidas`. Os silêncios já medidos pelo processamento vão junto quando o disco vai para "Precisam de você". Abrir de novo o mesmo disco leva cerca de 0,3 s em vez de 6 s. Se o áudio mudar, as medidas antigas não são usadas. Elas são apagadas com o áudio.

### EH. Revisão independente

Um segundo agente revisou as mudanças desta versão. Os achados foram corrigidos e testados:
- nomes perdidos quando o disco abria faltando um corte;
- nome escrito que voltava errado depois de juntar e separar;
- "A (2)" que virava "B" ao apagar o corte seguinte;
- caixa do nome aberta que ia para a linha errada quando os cortes mudavam;
- dois tempos na mesma pausa que viravam dois cortes no mesmo lugar;
- nomes colados com parênteses ou números de verdade cortados;
- "talvez outro disco" com o nome do disco errado no quadro;
- "Corrigir busca" depois do editor que era ignorado;
- cortes do editor ilegíveis que caíam no corte automático.

Testado em `testes/teste_editor.py` (agora 107 verificações), com:
- o "Ruth Brown - Sotfly" e o palpite "Zen Garden" de verdade, até a pasta "Ruth Brown - Softly" gravada;
- trocas sem pausa sintéticas, achadas no segundo exato, e nenhuma numa música só;
- as guias e o roxo na tela, a lista de nomes, o "Colar nomes" e o arquivo de correções.

O som de verdade e o roxo em discos reais só dá para conferir no Windows. Todos os testes passam, e os cortes dos discos de conferência continuam idênticos aos da 12.8. O tutorial (seções 1 e 8) ganhou as guias, os nomes, o quadro do disco sem Discogs e o arquivo de correções.
