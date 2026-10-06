"""
Ajustes do corte (CutTuning): todos os limiares numéricos da detecção de
silêncios e das estratégias de corte, num lugar só, cada um com o porquê.
Mudou um número aqui, rode os testes (testes/rodar_todos.py) - vários casos
reais dependem deles.
"""



class CutTuning:
    """
    Limiares, margens, janelas e pesos do corte de faixas (SmartCutter e
    AnaliseDeAudio). Quase todos vieram de um álbum real que cortava errado;
    o histórico está em MUDANCAS.md.

    Ficam fora daqui: bitrate mínimo (downloader.py), escolha de candidato
    do Discogs (pontuacao.py) e confiança mínima pra processar sem revisão
    (FullTracksDownloaderGUI.AUTO_PROCESS_MIN_CONFIDENCE_PCT).
    """

    # --- Onde cortar dentro do silêncio (posicao_de_corte_no_silencio) ---
    # O corte cai perto do FIM do silêncio: o silêncio fica no fim da faixa
    # anterior (soa natural) e a seguinte começa logo, como um CD rippado.
    # Meio segundo antes do som voltar, pra não comer o ataque da 1ª nota.
    SILENCE_CUT_LEAD_IN_SEC = 0.5

    # --- Ajuste final pelo início real da faixa seguinte ---
    # ver AnaliseDeAudio._inicio_real_da_proxima
    ONSET_BUSCA_ATRAS_SEC = 6.0     # quanto pode recuar o corte
    ONSET_BUSCA_FRENTE_SEC = 3.0    # quanto pode avançar (só atravessando silêncio)
    ONSET_SILENCIO_MIN_DB = 20.0    # o fundo precisa estar 20dB abaixo da música
    ONSET_PLATO_DB = 6.0            # quanto acima do fundo ainda conta como silêncio
    ONSET_SUBIDA_DB = 12.0          # subida que marca o começo do som
    ONSET_SUSTENTA_SEC = 0.25       # a subida precisa durar isso
    ONSET_CORTE_EM_SOM_DB = 10.0    # recuar só se o corte atual estiver em som
    ONSET_SUAVE_DB = 12.0           # e se o trecho pulado for suave (introdução)
    ONSET_MUDANCA_MIN_SEC = 0.8     # abaixo disso não mexe
    ONSET_FAIXA_MIN_SEC = 20.0      # nenhuma faixa fica menor que isso
    # Silêncio longo e fundo logo antes do corte = separação inequívoca: o som
    # entre ele e o corte é da faixa seguinte, mesmo sem ser "suave" (Gloria
    # Lynne 7->8: cordas 0,6dB acima do limite de "suave").
    ONSET_PLATO_LONGO_SEC = 1.5     # silêncio fundo pelo menos deste tamanho
    ONSET_INVASAO_CURTA_SEC = 1.5   # e o corte até isto depois do som voltar
    # Segunda busca, só quando a conferência acusa que a faixa seguinte ficou
    # curta (introdução tão baixa que parecia silêncio). Ver _recuo_pela_falta.
    ONSET_FALTA_MIN_SEC = 2.0       # a faixa seguinte precisa estar curta pelo menos isso
    ONSET_FALTA_FOLGA_SEC = 1.5     # recua no máximo o que falta + esta folga
    ONSET_FALTA_SUBIDA_DB = 8.0     # começo do som mais sensível (introdução baixinha)
    ONSET_FALTA_CORTE_DB = 4.0      # no ponto de corte ainda precisa haver algum som

    # --- Quedas de volume relativas, pros discos sem Discogs ---
    # ver AnaliseDeAudio._quedas_relativas
    QUEDA_REL_DB = 18.0                # abaixo da música ao redor, pra contar como queda
    QUEDA_REL_PROFUNDA_DB = 20.0       # sem nº de faixas: o ponto mais fundo precisa chegar a isso
                                       # (com nº de faixas conhecido basta QUEDA_REL_DB - o número protege)
    QUEDA_REL_MIN_SEC = 0.3            # duração mínima da queda
    QUEDA_REL_TRECHO_LONGO_SEC = 300.0 # trecho acima disso não cabe numa faixa típica
    QUEDA_REL_PEDACO_MIN_SEC = 90.0    # nenhum pedaço novo menor que isso
    # Com o nº de faixas do cadastro: queda que deixaria pedaço menor que isso
    # é pausa dentro da música (Ray Charles "Forever": queda 30s depois de um
    # silêncio de verdade virou um "Track 7" de 34s com o começo da faixa 8).
    QUEDA_REL_PEDACO_MIN_COM_N_SEC = 60.0
    # Piso: nunca cortar antes disso a partir do início do silêncio (em
    # silêncio curtíssimo, fim - 0,5s cairia antes do próprio começo).
    SILENCE_CUT_MIN_OFFSET_SEC = 0.2

    # --- Filtros básicos de silêncio ---
    MIN_SILENCE_DURATION_SEC = 1.0        # descarta silêncio mais curto que isso
    EARLY_GAP_FILTER_SEC = 60.0           # ignora "gaps" nos primeiros N segundos (falso positivo comum, ex: intro/clap)
    MIN_GAP_SPACING_SEC = 30.0            # espaçamento mínimo entre gaps aceitos (evita contar o mesmo silêncio 2x)
    # Com o nº de músicas do cadastro conhecido, nenhum pedaço do consenso
    # fica menor que isto: sobra o corte mais forte (pausa dentro da música
    # virava faixa de 30s - "Tocando Victor Assis Brasil")
    PEDACO_MIN_COM_N_SEC = 60.0
    ULTIMO_PEDACO_MIN_SEC = 30.0          # pedaço final menor que isso não é faixa

    # Desvio máximo entre um corte e a posição esperada pelo Discogs: acima
    # disso o disco é rejeitado (ou só avisado, ver REJEITAR_QUANDO_DURACAO_DIVERGE)
    # e o refinamento nem é tentado.
    MAX_DELTA_ALLOWED_SEC = 30.0

    # --- Confiança por votos (quantos detectores concordam num silêncio) ---
    MIN_VOTES_TO_TRUST = 2                # menos que isso é evidência fraca demais pra aceitar sozinha
    HIGH_VOTES_THRESHOLD = 4              # a partir de quantos votos um candidato vira "alta confiança"
    TRUST_DISTANCE_HIGH_VOTES_SEC = 30.0  # distância máx. aceita p/ candidatos de alta confiança
    TRUST_DISTANCE_LOW_VOTES_SEC = 15.0   # distância máx. aceita p/ candidatos de baixa confiança

    # --- find_closest_gap: janela de busca adaptativa (mais votos, janela menor) ---
    WINDOW_HIGH_CONFIDENCE_SEC = 30.0     # >=3 votos
    WINDOW_MEDIUM_CONFIDENCE_SEC = 45.0   # >=2 votos
    WINDOW_LOW_CONFIDENCE_SEC = 60.0      # <2 votos
    WINDOW_DEFAULT_SEC = 45.0             # modo não-adaptativo
    WINDOW_LAST_RESORT_SEC = 90.0         # último recurso, se nada foi achado na janela normal

    # --- find_closest_gap: pontuação combinada (silêncio + energia + proximidade + votos) ---
    SILENCE_SCORE_TIERS = [(2.0, 100), (1.0, 70), (0.5, 40), (0.2, 20)]  # (duração mín. em s, pontos)
    ENERGY_SCORE_TIERS = [(0.80, 30), (0.70, 20), (0.60, 10)]            # (queda de energia mín., pontos)
    PROXIMITY_SCORE_MAX = 50              # pontos a distância=0, perde 1 ponto por segundo de distância
    VOTES_SCORE_PER_VOTE = 5              # pontos por voto
    VOTES_SCORE_MAX = 50                  # teto de pontos vindos de votos

    # --- Refinamento fino (_refine_gap): a janela cobre a distância até o
    # esperado + a base, até o teto - um raio fixo não alcançava o esperado
    # quando o candidato já estava longe ---
    REFINE_WINDOW_BASE_SEC = 10.0         # janela mínima de refinamento (e usada quando não há posição esperada)
    REFINE_WINDOW_CAP_SEC = 30.0          # janela máxima de refinamento

    # --- Reataque local: buraco de 1 faixa, ancorado por cortes confirmados ---
    LOCAL_REATTACK_MAX_TRUST_DISTANCE_SEC = 25.0   # só aceita achado a até essa distância da posição esperada
    # Janela quando NÃO há âncora depois do buraco (vai até o fim do disco).
    # Igual à máxima com âncora; o filtro de distância acima ainda vale.
    LOCAL_REATTACK_NO_ANCHOR_WINDOW_SEC = 150.0
    LOCAL_REATTACK_WINDOW_MIN_SEC = 20.0  # janela com âncoras = metade do trecho entre elas,
    LOCAL_REATTACK_WINDOW_MAX_SEC = 150.0 # limitada a [MIN, MAX]
    LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC = 15.0  # evita reconhecer o MESMO silêncio do corte anterior como se fosse novo

    # --- Estimativa pela duração: SÓ quando o usuário manda processar mesmo
    # assim. Fronteira sem silêncio (músicas emendadas) entre cortes
    # confirmados vai pela proporção das durações, no ponto de menor energia
    # a até ESTIMATIVA_JANELA_SEC; as faixas ficam marcadas "conferir".
    # Até metade das fronteiras, no máximo ESTIMATIVA_MAX_SEGUIDAS seguidas
    # (o erro fica preso entre dois cortes confirmados). "Tocando Victor Assis
    # Brasil": 1 de 6; Ray Charles "Ingredients": 4 de 9, em 2 buracos de 2 ---
    ESTIMATIVA_MAX_SEGUIDAS = 2
    # o trecho entre os dois cortes confirmados tem de comportar as faixas do
    # buraco (diferença até max(isto, 8%)); senão há música a mais/menos ali
    ESTIMATIVA_FOLGA_TRECHO_SEC = 15.0

    # --- Corte em posições informadas (comentário do vídeo, tempos digitados
    # pelo usuário): o tempo de quem digitou costuma errar 1-3s; a fronteira
    # vai pro silêncio real perto, senão pro ponto de menor energia perto ---
    POSICAO_JANELA_SILENCIO_SEC = 6.0
    POSICAO_JANELA_RMS_SEC = 3.0
    ESTIMATIVA_JANELA_SEC = 8.0

    # --- cut_directly_on_gaps: uma pausa curta dentro da faixa não deve
    # vencer um silêncio real mais longo só por estar um pouco mais perto ---
    LONGER_SILENCE_PREFERENCE_MARGIN_SEC = 1.5        # vantagem mínima de duração pra valer a troca
    LONGER_SILENCE_EXTRA_DISTANCE_TOLERANCE_SEC = 15.0  # até quantos segundos a mais vale considerar

    # --- RMS mínimo (_find_rms_minimum): onde cortar dentro do platô de silêncio ---
    RMS_WINDOW_SIZE_SEC = 0.5              # tamanho de cada janela de RMS
    RMS_HOP_SIZE_SEC = 0.1                 # passo entre janelas (resolução do corte)
    RMS_PLATEAU_TOLERANCE_FACTOR = 0.15    # tolerância do platô = min_rms * este fator
    RMS_RECOVERY_THRESHOLD_FACTOR = 5      # limiar de "voltou ao volume normal" = min_rms * este fator
    RMS_RECOVERY_MAX_SEARCH_SEC = 8.0      # não procura recuperação além disso, de cada lado do platô
    RMS_BIAS_BASE = 0.85    # posição dentro do platô quando simétrico (menos silêncio sobrando antes da próxima)
    RMS_BIAS_MAX = 0.98     # quando a assimetria aponta claramente um fade out (favorece o fim do platô)
    RMS_BIAS_MIN = 0.15     # quando a assimetria aponta o oposto, um fade-in (favorece o início do platô)

    # Falhas até tirar o item da fila de pendentes. A falha que mandou o disco
    # pra fila já foi a 1ª tentativa; rede já tem 3 tentativas no download.
    MAX_FALHAS_NA_FILA = 1
    # Falta (s) a partir da qual se tenta o alinhamento global por intervalos.
    # Sem risco: ele só troca os cortes se medir uma falta menor que a atual.
    INTERVAL_ALIGNMENT_TRY_SEC = 4.0
    # False: delta grande e intervalo curto viram AVISO no log, não rejeição
    # (pedido do usuário: disco com corte torto é melhor que disco nenhum).
    # Falta de corte numa faixa continua rejeitando. True volta a rejeitar.
    REJEITAR_QUANDO_DURACAO_DIVERGE = False

    # --- Validação por intervalo (_validar_intervalos e cut_with_durations) ---
    # Entre dois cortes cabe a faixa inteira + o silêncio, então o intervalo
    # nunca pode ser MENOR que a duração do Discogs (seria corte cedo). Não
    # acumula deriva como comparar com a posição esperada (soma das durações).
    # Tolerância: durações do Discogs vêm arredondadas (m:ss) e às vezes erradas.
    INTERVAL_SHORTFALL_TOLERANCE_SEC = 4.0
    # Falta grave o bastante pra rejeitar em vez de só avisar (abaixo disso
    # pode ser imprecisão do catálogo).
    INTERVAL_SHORTFALL_REJECT_SEC = 10.0

    # Silêncios de detectores diferentes a até esta distância viram um cluster
    # (um voto por detector).
    CLUSTER_TOLERANCE_SEC = 3.0

    # --- Aviso de "faixa suspeitosamente longa" (2+ faixas grudadas, sem
    # silêncio entre elas): vale se passar do multiplicador E da margem ---
    SUSPICIOUS_LENGTH_VS_MEDIAN_MULTIPLIER = 2.0    # vs. mediana das faixas do álbum
    SUSPICIOUS_LENGTH_VS_MEDIAN_MARGIN_SEC = 90
    SUSPICIOUS_LENGTH_VS_EXPECTED_MULTIPLIER = 1.6  # vs. duração do Discogs da própria faixa
    SUSPICIOUS_LENGTH_VS_EXPECTED_MARGIN_SEC = 60

    # --- Detecção de silêncio (AlbumCutter.detect_gaps): 3 limiares em
    # paralelo, do mais rigoroso (só silêncio limpo) ao mais sensível (pega
    # ruído baixo); a concordância entre eles são os votos ---
    FFMPEG_THRESHOLDS_DB = [-35, -30, -25]
    FFMPEG_MIN_SILENCE_DURATION_SEC = 1.0  # silêncio mais curto que isso não é intervalo entre faixas
    FFMPEG_DETECT_TIMEOUT_SEC = 180        # por limiar; disco longo leva tempo

    # --- Silêncios do disco inteiro de uma vez (_detect_all_silences_full_disk):
    # limiar único e moderado, visão geral antes de refinar faixa a faixa ---
    FFMPEG_FULL_DISK_THRESHOLD_DB = -40
    FFMPEG_FULL_DISK_MIN_DURATION_SEC = 1.0  # silêncios reais, não respiros
    FFMPEG_FULL_DISK_TIMEOUT_SEC = 120
