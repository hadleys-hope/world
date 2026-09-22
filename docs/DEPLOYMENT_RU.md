# Совместимость с сервером и автоматическим обновлением

Сохранена текущая схема: два соседних репозитория `infra/` и `world/`.
`infra/rst` выполняет `git pull --ff-only` для обоих, затем
`docker compose up -d --build --remove-orphans`. Существующий systemd timer
продолжает вызывать тот же скрипт.

## Что перенести в репозитории

Содержимое каталога `world/` из архива нужно положить в корень существующего
репозитория world. Аналогично содержимое `infra/` — в корень infra.
Не создавайте дополнительную вложенность `world/world/`. Архивы не содержат
`.git`, `.env`, данных мира и ключей; существующие каталоги Git и серверные
настройки остаются на месте. В коммит должны попасть все новые каталоги,
а не только два старых Python-файла.

Отдельные команды установки npm, компиляции фронтенда или миграции базы на
сервере не требуются. Контейнер сам устанавливает Python-зависимости из
`requirements.txt`. Dockerfile копирует пакет `hadleys/`, `web/`, `vendor/`
и обе совместимые точки входа. Сервис houses использует тот же образ.

## Что осталось прежним

- `compose.yaml`, имена сервисов, порты, MQTT topics и Caddy.
- `python3 hadleys_hope.py --speed 20` и `python3 houses_runtime.py`.
- `MQTT_URL`, `DATA_DIR`, `PORT`, `ADMIN_TOKEN`, `DOMAIN`.
- Volume `world-data`, файлы `world.pkl` и `history.db`.
- Адреса страниц и JSON API, включая `/attractors`.

## CI и timer — разные механизмы

GitHub Actions теперь выполняет Python-регрессии, проверку JS-импортов,
браузерный smoke, сборку Docker-образа и сутки симуляции внутри образа.
Node и Playwright нужны только разработке и CI, а не production-контейнеру.

Как и раньше, серверный timer ориентируется на изменения Git и **не ожидает
результата GitHub Actions**. Разделение кода это не меняет. Чтобы деплой был
строго после зелёного CI, потребуется отдельная схема продвижения проверенной
ветки/тега или доставка собранного образа; такого изменения здесь нет.

В `rst` исправлен случай неудачной сборки: успешные ревизии записываются в
`${XDG_STATE_HOME:-$HOME/.local/state}/hadleys-hope/deployed-heads` только после
успешного `compose up`. Если сборка упала, следующий запуск timer повторит
её, даже если новых коммитов уже нет. При первом запуске обновлённого скрипта
выполняется одна сборка для создания отметки. Рабочая директория Compose
задана явно, чтобы поиск `.env` не зависел от места вызова `rst`.

## Проверка без обращения к production

```sh
# Из world/
python3 -m unittest discover -s tests -v
npm ci
npm run check
npx playwright install chromium
npm run test:browser
docker build -t hadleys-world:local .
docker run --rm hadleys-world:local python3 hadleys_hope.py --headless 1440
docker run --rm hadleys-world:local python3 houses_runtime.py --help

# Из infra/
python3 -m unittest discover -s tests -v
```

В этой рабочей среде проверены Python, JS и браузерный запуск. Docker CLI и
engine отсутствуют, поэтому Docker build и сам GitHub Actions здесь не
запускались; эти проверки включены в обновлённый workflow.

Перед первым обновлением сохраните текущий `world.pkl` обычным способом
резервного копирования сервера. Обновлённый пакет читает старое сохранение;
при откате на прежний монолит понадобится и прежний файл состояния.
