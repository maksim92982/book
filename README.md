# Книги

Репозиторий черновиков. Сейчас первая книга: **Песни Дуная** (`books/01-pesni-dunaya`). Следующая будет `02-…`.

Генерация идёт локально (Ollama). После каждого круга разбора/правки пайплайн сам коммитит и пушит сюда. Vercel читает этот репозиторий — с телефона смотришь ход, не localhost.

## Локально

```text
python start.py
```

Дашборд: http://127.0.0.1:8765

Env: `OLLAMA_URL`, `OLLAMA_MODEL`, `LITRESS_BOOK`, `LITRESS_GIT_REMOTE`, `LITRESS_GIT_SYNC=0` если пуш не нужен.

## Vercel (делаешь сам)

1. Import GitHub-репозитория `maksim92982/book`.
2. Framework Preset: **Other**.
3. Root Directory: `.`
4. Build Command: пусто.
5. Output: не нужен, это статика (`index.html`, `books.json`, `books/…`).
6. Deploy.

После деплоя напиши — скажу, нужно ли ещё что-то (обычно нет, кроме домена).
