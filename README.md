# ecoibeu mouse

Interface GTK3 em Python para gravar o mapeamento dos dois botões laterais
do mouse **WKPC-S44 / EVISION 3-mode** direto no dispositivo,
usando o protocolo de 64 bytes do fabricante.

O mesmo conjunto aparece como `320f:226e` (cabo) ou `320f:226f`
(receptor 2.4G). O app testa o protocolo em todos os hidraw da EVISION e
usa o que responder.

- **Forward** = entrada 3 do keymap
- **Back** = entrada 4 do keymap
- Keymap: `config[5] * 3` = **126 bytes** neste mouse
- Catálogo: 91 teclas extraídas da tabela do executável do fabricante
  (`app/WKPC-S44 MOUSE.exe`, offset `0x2d2e38`) + botões do mouse + Desativado

## Como rodar

```sh
./run.sh
```

ou:

```sh
/usr/bin/python3 app.py
```

> Use `/usr/bin/python3`. O `python3` do `mise` não tem o módulo `gi`
> (PyGObject), mas o Python do sistema tem GTK3 e os typelibs instalados.

## Como usar

1. Clique no botão **+** (canto superior direito) para criar um perfil.
2. Dê um nome ao perfil.
3. Escolha as teclas de **forward** e **back**. Os campos são dropdowns com
   busca: digite parte do nome da tecla para filtrar.
4. Clique no botão **▶** do perfil para aplicar no mouse.

### Perfil padrão

- Clique na **estrela** de um perfil para marcá-lo como padrão.
- O botão **▶** ao lado do **+** aplica diretamente o perfil padrão.
- Só existe um padrão por vez; ao apagar o perfil padrão, o primeiro perfil
  restante vira o novo padrão.
- O `default_id` fica salvo junto com os perfis.

Todos os botões usam apenas ícones, com tooltip explicando a ação:

| Ícone | Ação |
|---|---|
| `+` | Novo perfil |
| `★` / `☆` | Perfil padrão / definir como padrão |
| `▶` | Aplicar perfil (na linha) ou aplicar o padrão (no cabeçalho) |
| lixeira | Apagar perfil |

Ao aplicar, o app chama `apply_helper.py` como root usando `sudo -A`. O
`SUDO_ASKPASS` é um script temporário que abre o **zenity** pedindo a senha.
A interface em si nunca roda como root.

## Empacotar como AppImage

O `appimagetool` já está na pasta. Para gerar o AppImage:

```sh
make            # ou: make appimage
```

Saída: `ecoibeu-mouse-x86_64.AppImage` (~1 MB).

Outros alvos:

```sh
make check      # compila os fontes e confere PyGObject/GTK3
make appdir     # monta apenas o AppDir em build/
make icons      # regera os PNGs do ícone a partir do SVG
make run        # roda direto do código-fonte
make clean      # apaga o AppDir e o AppImage gerado
```

O AppImage **não embute Python/GTK**: ele usa o `/usr/bin/python3` do sistema,
que precisa ter PyGObject e GTK3 instalados (o mesmo requisito para rodar
`./run.sh`). Isso mantém o arquivo pequeno. Na primeira execução do
`appimagetool` pode ser necessário internet para baixar o runtime do AppImage.

O ícone do aplicativo é gerado a partir de `packaging/ecoibeu-mouse.svg`
(um mouse com os dois botões laterais destacados). Os PNGs (16, 24, 32, 48,
64, 128 e 256 px) são rasterizados com **librsvg + cairo** por
`packaging/render-icons.py`, preservando gradientes e cantos arredondados.

## Instalar no app grid (Ubuntu/GNOME)

```sh
make install
```

Isso:

- copia o AppImage para `~/.local/bin/ecoibeu-mouse.AppImage`;
- instala `~/.local/share/applications/ecoibeu-mouse.desktop`;
- instala os ícones em `~/.local/share/icons/hicolor/`;
- atualiza os caches (`update-desktop-database` e `gtk-update-icon-cache`).

Depois procure por **ecoibeu mouse** no app grid ou no menu de aplicativos.
Para remover:

```sh
make uninstall
```

Alternativas que fazem a mesma integração automaticamente:
**AppImageLauncher** ou **Gearlever** (Flatpak).

### Por que o ícone não aparecia no dock

No Wayland, o GNOME identifica a janela pelo **app_id** que o cliente anuncia
e procura um arquivo `.desktop` com esse mesmo nome. O GTK3 usa o
`g_get_prgname()` para o app_id; como o app era executado como
`python3 app.py`, o app_id virava `app.py`, então não existia `.desktop`
correspondente e o dock mostrava o ícone genérico.

O app agora define, antes de criar a janela:

```python
GLib.set_prgname("ecoibeu-mouse")
Gdk.set_program_class("ecoibeu-mouse")
```

E o `.desktop` se chama `ecoibeu-mouse.desktop`, com
`StartupWMClass=ecoibeu-mouse` para o caso do X11. O
`Gtk.Window.set_icon_name()` / `set_icon_from_file()` também é definido, mas
no Wayland quem manda é o par **app_id + nome do .desktop**.

> Se o app já estava aberto antes da correção, feche e abra novamente para o
> dock atualizar o app_id.

## O que o helper faz

1. Descobre o `/dev/hidraw*` com VID `320F` (`226E` ou `226F`) que responde
   ao protocolo.
2. Lê a config (`0x03`) e obtém `config[5] = 42` → keymap de 126 bytes.
3. Lê o keymap atual (`0x07`) e salva um backup local.
4. Troca somente as entradas 3 (forward) e 4 (back).
5. Grava com a sequência do fabricante:

   `BEGIN (0x01)` → `SET_KEYMAP (0x09)` em chunks de 56 → `COMMIT (0x02)`

### Helper fora do AppImage

O AppImage é montado via FUSE e o mount só é acessível ao usuário que o
montou; o root do `sudo` recebe `EACCES` ao abrir arquivos em
`/tmp/.mount_*`. Por isso, antes de chamar o `sudo`, o app copia
`apply_helper.py` e `wkpc_protocol.py` para
`~/.cache/ecoibeu-mouse/helper/` (diretório 755, arquivos 644) e executa essa
cópia. Assim o root lê o helper sem precisar acessar o mount do AppImage.

> Observação: neste mouse o `GET_KEYMAP (0x07)` pode continuar retornando o
> valor antigo mesmo depois de uma gravação aceita. O app não trata isso como
> erro nem mostra aviso; considera a gravação bem-sucedida pelos ACKs
> (`status 0x00`) e pelo funcionamento dos botões.

## Onde ficam os dados

- Perfis + perfil padrão: `~/.config/ecoibeu-mouse/profiles.json`
- Backups do keymap: `~/.local/share/ecoibeu-mouse/backups/`
- Script askpass temporário: `~/.cache/ecoibeu-mouse/askpass.sh`
- Cópia do helper usada pelo sudo: `~/.cache/ecoibeu-mouse/helper/`

## Arquivos

| Arquivo | Função |
|---|---|
| `app.py` | Interface GTK3, perfis, perfil padrão, dropdowns com busca, apply/delete |
| `wkpc_protocol.py` | Protocolo hidraw, descoberta, leitura/gravação do keymap |
| `apply_helper.py` | Executado como root; aplica e devolve JSON |
| `key_catalog.py` | Catálogo de teclas extraído do EXE do fabricante |
| `run.sh` | Atalho para rodar com `/usr/bin/python3` |
| `Makefile` | Empacotamento do AppImage e instalação no app grid |
| `packaging/` | `AppRun`, launcher, `.desktop`, SVG e ícones do AppImage |
