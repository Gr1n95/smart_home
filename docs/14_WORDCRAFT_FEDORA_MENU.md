# WordCraft в меню приложений Fedora

WordCraft ([storytold/wordcraft](https://github.com/storytold/wordcraft)) — Rust-приложение (eframe/egui).
У него **нет установщика, который сам добавляет пункт в меню**, если вы просто склонировали репозиторий и
собрали его `cargo` — в меню приложение появляется только из пакета (`.rpm`, Flatpak) или из
`.desktop`-файла, который нужно положить руками. Ниже — три способа, от самого простого.

## Вариант 0 (самый простой): готовый `.rpm`

Если исходники не нужны, релиз уже содержит пакет для Fedora — он сам кладёт бинарник в `/usr/bin`,
иконки в `/usr/share/icons`, `.desktop` в `/usr/share/applications` и обновляет кэши:

```bash
# https://github.com/storytold/wordcraft/releases/latest
sudo dnf install ~/Downloads/wordcraft-0.16.0-linux-x86_64.rpm
```

Или AppImage — но у AppImage `.desktop`-файл внутри, наружу его никто не выкладывает, поэтому его
всё равно надо зарегистрировать (см. вариант 2; скрипт ниже умеет и это).

## Вариант 1: скрипт из этого репозитория

```bash
cd ~/smart_home
scripts/desktop/install-wordcraft-desktop.sh                  # найдёт ~/wordcraft и target/release
scripts/desktop/install-wordcraft-desktop.sh --app-dir ~/wordcraft
scripts/desktop/install-wordcraft-desktop.sh --bin ~/wordcraft/target/release/wordcraft
scripts/desktop/install-wordcraft-desktop.sh --dry-run        # только показать, ничего не менять
scripts/desktop/install-wordcraft-desktop.sh --check          # проверить, что всё на месте
scripts/desktop/install-wordcraft-desktop.sh --uninstall      # убрать пункт из меню
```

Скрипт не требует `sudo` и трогает только пользовательские каталоги:

| Что | Куда |
|---|---|
| `.desktop` | `~/.local/share/applications/ai.storyteller.wordcraft.desktop` |
| иконки 16…512 px + SVG | `~/.local/share/icons/hicolor/<size>/apps/ai.storyteller.wordcraft.png` |
| кэши | `gtk-update-icon-cache`, `update-desktop-database`, `kbuildsycoca6/5` (если есть) |

Иконки он берёт из `assets/app-icon/hicolor` клона WordCraft, а если клона нет, а есть AppImage —
распаковывает их из самого AppImage (`--appimage-extract`, FUSE не нужен).
В `Exec=` подставляется абсолютный путь; кириллица и пробелы в пути экранируются по спецификации
desktop-entry.

## Вариант 2: руками, без скрипта

1. **Соберите (если ещё не собрано).** В `~/wordcraft`:

   ```bash
   sudo dnf install cargo rustup gcc gcc-c++ make pkgconf-pkg-config \
       libxkbcommon-devel wayland-devel libX11-devel libXcursor-devel libXrandr-devel \
       libXi-devel gtk3-devel fontconfig-devel freetype-devel vulkan-loader mesa-vulkan-drivers git
   rustup default stable            # нужен rustc >= 1.95 (edition 2024)
   cargo build --release -p wordcraft
   ```

   Бинарник появится в `~/wordcraft/target/release/wordcraft`.

2. **Положите `.desktop`-файл** в `~/.local/share/applications/ai.storyteller.wordcraft.desktop`:

   ```ini
   [Desktop Entry]
   Type=Application
   Name=WordCraft
   GenericName=Word Processor
   Comment=Write and design documents; open and save Word files
   Exec=/home/gr1n/wordcraft/target/release/wordcraft %F
   TryExec=/home/gr1n/wordcraft/target/release/wordcraft
   Icon=ai.storyteller.wordcraft
   Terminal=false
   StartupNotify=true
   StartupWMClass=ai.storyteller.wordcraft
   Categories=Office;WordProcessor;
   MimeType=application/vnd.openxmlformats-officedocument.wordprocessingml.document;application/msword;application/rtf;text/markdown;text/html;
   ```

   Готовый шаблон лежит рядом: [`wordcraft.desktop.in`](./wordcraft.desktop.in)
   (в нём же русские `GenericName`/`Comment`/`Keywords`).

3. **Иконки** (без них пункт меню будет с иконкой-заглушкой):

   ```bash
   ID=ai.storyteller.wordcraft
   for s in 16 24 32 48 64 128 256 512; do
     install -Dm644 ~/wordcraft/assets/app-icon/hicolor/${s}x${s}/apps/$ID.png \
       ~/.local/share/icons/hicolor/${s}x${s}/apps/$ID.png
   done
   install -Dm644 ~/wordcraft/assets/app-icon/hicolor/scalable/apps/$ID.svg \
     ~/.local/share/icons/hicolor/scalable/apps/$ID.svg
   ```

4. **Обновите кэши и права** (без этого пункт может не появиться сразу):

   ```bash
   update-desktop-database ~/.local/share/applications
   gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor
   desktop-file-validate ~/.local/share/applications/ai.storyteller.wordcraft.desktop  # по желанию
   chmod +x ~/.local/share/applications/ai.storyteller.wordcraft.desktop
   # GNOME: пометить как доверенный (иначе может не появиться в меню / не запускаться)
   gio set ~/.local/share/applications/ai.storyteller.wordcraft.desktop metadata::trusted true
   ```

   На KDE Plasma дополнительно: `kbuildsycoca6 --noincremental` (или `kbuildsycoca5`),
   в крайнем случае — выход из сеанса и вход.

## Обновление после `git pull` + пересборки

Пункт меню ссылается на путь `~/wordcraft/target/release/wordcraft`, поэтому достаточно пересобрать —
файлы меню переустанавливать не нужно. Если вы перенесли каталог, запустите скрипт ещё раз с новым
`--app-dir`/`--bin`.

## Если пункт в меню не появился

| Симптом | Причина / что делать |
|---|---|
| `Super` → поиск «WordCraft» пусто | `desktop-file-validate` покажет ошибку в `.desktop`; чаще всего забыли `%F`‑путь (`Exec=wordcraft` без полного пути) |
| Пункт есть, но не запускается | `Exec=` указывает на несуществующий файл: проверьте `--check`, `TryExec` должен быть исполняемым |
| Иконка-заглушка | иконки не попали в `~/.local/share/icons/hicolor`, либо не обновлён `gtk-update-icon-cache` |
| В GNOME поиск не видит, в файловом менеджере `.desktop` открывается как текст | `chmod +x` + `gio set ... metadata::trusted true` |
| «Приложение не запускается из меню, а из терминала работает» | в меню другой `PATH`: в `Exec` должен быть **абсолютный путь**, а не `wordcraft` |
| `error while loading shared libraries: libxkbcommon.so.0` | `sudo dnf install libxkbcommon libxkbcommon-x11 libwayland-client libX11 libXcursor libXi libXrandr` |
| Приложение падает/чёрное окно на Vulkan | `sudo dnf install vulkan-loader mesa-vulkan-drivers`; для отладки `WGPU_BACKEND=gl wordcraft` |
| AppImage не стартует | `sudo dnf install fuse-libs` (или запускать с `--appimage-extract-and-run`) |
| Хочется чистый Wayland (вместо XWayland) | `WORDCRAFT_WAYLAND=1` в `Exec`/`~/.config/environment.d/` — в XWayland не работает drag-and-drop файлов |

Проверка, что система вообще видит запись:

```bash
gio info ~/.local/share/applications/ai.storyteller.wordcraft.desktop | head
xdg-mime query default application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

Последняя команда покажет, какой программой открываются `.docx` — если пусто, ассоциацию можно
поставить через «Открыть с помощью → Всегда» в файловом менеджере.

## Связанное

- Релизы и форматы поставки: <https://github.com/storytold/wordcraft/releases/latest>
- В репозитории WordCraft уже есть готовые `packaging/linux/ai.storyteller.wordcraft.desktop`,
  `packaging/icons.sh` и `packaging/linux/nfpm.yaml` — этот каталог повторяет их логику для
  локальной (per-user) установки без пакетного менеджера.
