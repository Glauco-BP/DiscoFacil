# 💿 DiscoFácil

Transforma vídeos de **disco inteiro do YouTube** ("Full Album") em **faixas MP3 separadas**, com o nome de cada música, o número, o artista, o álbum, o ano e a capa.

> **Por enquanto, só para Windows 64 bits** (Windows 10 ou 11).

O programa descobre qual disco é pelo [Discogs](https://www.discogs.com), acha onde cada música começa (pelas pausas, pelas durações oficiais, pelos capítulos ou pelos tempos que alguém postou nos comentários) e grava cada uma num arquivo. Quando não tem certeza, **não grava nada errado**: o disco vai para a lista **"Precisam de você"**, onde você decide — e pode **ouvir o disco e acertar os cortes** numa tela própria.

## Baixar e usar

1. Vá em **[Releases](../../releases)** e baixe o `DiscoFacil_<versão>.zip` mais recente.
2. Descompacte numa pasta e abra o **`DiscoFacil.exe`**. Não precisa instalar Python nem FFmpeg.
3. Na primeira vez, abra **Configurações** e:
   - escolha a pasta onde os discos serão gravados;
   - cole a sua **chave do Discogs** (grátis: crie uma conta em discogs.com → *Settings → Developers → Generate new token*). Cada pessoa usa a sua.
4. Cole o link do vídeo e clique em **Enfileirar**.

**Para experimentar**: dois canais com muitos discos completos, bons para testar (modo **Canal Inteiro**, ou um vídeo de cada vez):
- [MultiWoking](https://www.youtube.com/@MultiWoking)
- [Discos Redondos (Full Albums)](https://www.youtube.com/@discosredondosfullalbum)

O **tutorial em PDF** (no zip e [aqui](Tutorial_DiscoFacil_12.18.pdf)) explica cada tela, com figuras.

> **"O Windows protegeu o computador"**: o .exe não tem assinatura digital paga, então o Windows desconfia. Clique em **Mais informações → Executar assim mesmo**. Alguns antivírus também reclamam de programas gerados com PyInstaller; o código está todo aqui para quem quiser conferir.

## O que ele faz

- **Vídeo único, canal inteiro ou playlist** (um disco em que cada vídeo é uma música).
- **Identificação pelo Discogs**, com nota de confiança; abaixo do mínimo configurado, pergunta antes.
- **Corte nas pausas reais**, conferido com as durações oficiais; músicas emendadas sem pausa são separadas pela duração e marcadas "a conferir".
- **✂ Conferir cortes**: uma tela para ouvir o disco inteiro, ver a onda, as pausas e as guias (onde o Discogs poria cada corte; onde o som muda de repente), mover, marcar e apagar cortes e trocar nomes. Serve também para **corrigir discos já cortados**.
- **Não baixa de novo** o que já está na pasta (pelo número do disco no Discogs).
- **Fila guardada**: pode fechar no meio e continuar depois.
- Tags ID3 completas e capa dentro de cada MP3.

## Aviso legal

O DiscoFácil é para **uso pessoal**. Ele não vem com música nenhuma: baixa o que **você** escolher, e baixar conteúdo do YouTube pode ir contra os termos de uso do YouTube e contra os direitos autorais de quem gravou o disco. **A responsabilidade pelo uso é de quem usa.** Prefira discos que você já tem, que estão em domínio público ou cujo dono permite a cópia.

## Para quem programa

Python 3.12 + Tkinter. O programa é feito e testado para Windows 64 bits; os testes também rodam no Linux. Para rodar a partir do código:

```
pip install -r requirements.txt
python main.py
```

Precisa do `ffmpeg` e do `ffprobe` no PATH (o .exe já vem com eles).

- **Como funciona por dentro:** [ARQUITETURA.md](ARQUITETURA.md) (o caminho de um disco, os módulos e onde mexer).
- **O que mudou em cada versão:** [MUDANCAS.md](MUDANCAS.md). **Planos:** [PLANO.md](PLANO.md).
- **Testes:** `python testes/rodar_todos.py` (precisa de `ffmpeg`; no Linux, de `xvfb-run` para as telas). Nenhum teste usa a internet. Ver [testes/LEIA.md](testes/LEIA.md).
- **Gerar o .exe:** `build_exe.bat` no Windows, ou automático aqui no GitHub: ao marcar uma versão (`git tag v12.19` + `git push --tags`), o GitHub gera o .exe e publica em Releases ([.github/workflows/release.yml](.github/workflows/release.yml)).

## Licença

[GPL-3.0](LICENSE). Você pode usar, estudar, modificar e redistribuir, desde que as versões modificadas continuem abertas sob a mesma licença. As bibliotecas e programas usados, com as licenças de cada um, estão em [TERCEIROS.md](TERCEIROS.md).

Elaborado por Glauco — Barra do Piraí, RJ.
