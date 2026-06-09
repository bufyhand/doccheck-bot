# DocCheck Manager Bot

Telegram-бот для сверки заказа поставщику и счета по машинному справочнику
штрихкодов. Проект создан с нуля по `Agent.md`, не использует БД и миграции.

Основная сверка полностью детерминирована. GigaChat формирует только резюме и
отвечает на вопросы по результату текущей сверки.

## Быстрый запуск

Требуется Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `TELEGRAM_BOT_TOKEN` и, при необходимости, `GIGACHAT_CREDENTIALS` в
`.env`. Без GigaChat бот продолжит сверку и сформирует локальное резюме.

Если из вашей сети недоступен `api.telegram.org:443`, задайте прокси:

```text
TELEGRAM_PROXY=http://user:password@host:port
```

## Подготовка справочника

Исходный Excel должен содержать колонки `Наименование товара`, `Штрих-код` и
`Дополнительные штрих-коды`.

```powershell
python prepare_catalog.py "Все шк.xlsx"
```

Результат будет сохранен в `data/catalog_index.json`. Конфликтные штрихкоды
попадут в блок `conflicts` и не будут использоваться для автосопоставления.

## Локальная сверка

```powershell
python check_documents.py order.xlsx invoice.xlsx
```

Отчет создается в `temp/reports/doccheck_report.xlsx`.

## Telegram

```powershell
python -m bot.main
```

Команды: `/start`, `/help`, `/new`, `/reset`, `/catalog_status`.

## GigaChat

Интеграция использует официальный Python SDK `gigachat`. В GigaChat передается
структурированный результат текущей сверки, а не исходные документы. Модель не
может менять статусы или принимать решение о согласовании/оплате.

Настройки:

```text
GIGACHAT_CREDENTIALS=
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat
GIGACHAT_VERIFY_SSL_CERTS=true
```

## Проверка

```powershell
python -m unittest discover -v
python -m compileall bot core prepare_catalog.py check_documents.py
```
