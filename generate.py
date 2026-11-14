from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import BOOK_DIR, NUM_CTX, OLLAMA_MODEL, OLLAMA_URL

BIBLE = BOOK_DIR / "bible"
CHAPTERS = BOOK_DIR / "chapters"
MEMORY = BOOK_DIR / "memory"
BOOK = BOOK_DIR / "book.md"
FACTS = MEMORY / "facts.md"
PREMISE = BIBLE / "premise.md"
CHARACTERS = BIBLE / "characters.md"
OUTLINE = BIBLE / "outline.json"


def chat(prompt: str, *, temperature: float, num_predict: int, timeout: int = 600) -> str:
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": "2h",
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": NUM_CTX,
                "repeat_penalty": 1.12,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Ollama HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError("Ollama не отвечает. Запусти ollama serve.") from error
    text = str(result.get("message", {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama вернула пустой текст")
    print(f"llm {int(time.time() - started)}s {len(text)} chars", flush=True)
    return _strip_meta(text)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def generate_bible() -> None:
    BIBLE.mkdir(parents=True, exist_ok=True)
    MEMORY.mkdir(parents=True, exist_ok=True)
    CHAPTERS.mkdir(parents=True, exist_ok=True)
    prompt = """Ты редактор русскоязычного интеллектуального детектива для публикации как самиздат.

Придумай ОРИГИНАЛЬНЫЙ замысел современной повести (не копия известных книг и сериалов).
Место: Белград, зима, Дунай и Сава, район Савамала и Нови Београд.
Главный герой: Илья Корин, 42 года, бывший следователь из России, сейчас переводчик-консультант при белградской полиции. Не циник-пародия, живой человек.
Жертва: архивист культурного фонда.
Убийство связано с поддельными провенансами картин, не с серийным маньяком.
Убийца — один из круга жертвы, мотив корыстный и личный одновременно.
Должны быть ложные следы, улика-предмет, сцена на воде.

Верни СТРОГО JSON без markdown:
{
  "title": "...",
  "logline": "2-3 предложения",
  "tone": "коротко про тон",
  "secret": "кто убийца и как это доказывается, спойлер",
  "characters": [
    {"name": "", "role": "герой|жертва|убийца|свидетель|полицейский", "bio": "4-6 предложений"}
  ],
  "chapters": [
    {"n": 1, "title": "", "beats": "что происходит, 4-6 предложений, без финала книги", "ends_with": "крючок"}
  ]
}
Нужно ровно 14 глав. Глава 13 — разоблачение. Глава 14 — послевкусие, не мораль учебника.
Имена сербские и русские, без знаменитостей. Только русский язык в строках JSON."""
    raw = chat(prompt, temperature=0.55, num_predict=3500, timeout=900)
    data = _json_object(raw)
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) < 10:
        raise RuntimeError("План глав слишком короткий")
    title = str(data.get("title") or "Белградский архив")
    logline = str(data.get("logline") or "")
    tone = str(data.get("tone") or "")
    secret = str(data.get("secret") or "")
    write(
        PREMISE,
        f"# {title}\n\n{logline}\n\nТон: {tone}\n\n## Спойлер (не в текст глав напрямую)\n\n{secret}\n",
    )
    people = data.get("characters") if isinstance(data.get("characters"), list) else []
    lines = [f"# Персонажи — {title}", ""]
    for person in people:
        if not isinstance(person, dict):
            continue
        lines.append(f"## {person.get('name') or '—'}")
        lines.append(f"Роль: {person.get('role') or '—'}")
        lines.append(str(person.get("bio") or ""))
        lines.append("")
    write(CHARACTERS, "\n".join(lines))
    write(OUTLINE, json.dumps(data, ensure_ascii=False, indent=2))
    if not FACTS.is_file():
        write(FACTS, f"# Факты сюжета\n\nКнига: {title}\n")
    print(f"bible: {title}, глав {len(chapters)}", flush=True)


def generate_next_chapter() -> bool:
    if not OUTLINE.is_file():
        generate_bible()
    data = json.loads(OUTLINE.read_text(encoding="utf-8"))
    plan = [row for row in data.get("chapters") or [] if isinstance(row, dict)]
    done = sorted(CHAPTERS.glob("*.md"))
    index = len(done)
    if index >= len(plan):
        print("все главы уже есть", flush=True)
        return False
    item = plan[index]
    number = index + 1
    prev_text = done[-1].read_text(encoding="utf-8") if done else ""
    prev_tail = prev_text[-1800:] if prev_text else "Это первая глава."
    facts = FACTS.read_text(encoding="utf-8") if FACTS.is_file() else ""
    premise = PREMISE.read_text(encoding="utf-8")
    characters = CHARACTERS.read_text(encoding="utf-8")
    prompt = f"""Пиши художественную главу детективной повести на русском.

Это глава {number} из {len(plan)}. Название главы: {item.get("title") or number}.

Канон книги (не пересказывать читателю списком, вшить в сцены):
{premise}

Персонажи:
{characters}

План ЭТОЙ главы (обязательно случится):
{item.get("beats")}
Глава должна закончиться так: {item.get("ends_with")}

Уже установленные факты:
{facts[-2500:]}

Хвост предыдущей главы:
{prev_tail}

Правила:
- Только русский. Никакого китайского, английского, пояснений «я сейчас напишу главу».
- Литературная проза, не канцелярит, не список буллетов.
- Показывай через действие, диалог, детали Белграда зимой. Не пиши «в этой главе».
- 900–1300 слов. Законченные абзацы, не обрывай на полуфразе.
- Не называй убийцу. Не раскрывай секрет до главы 13. Не меняй канон и имена.
- Никаких метакомментариев и markdown внутри сцен.

Верни только текст главы, первой строкой заголовок: Глава {number}. {item.get("title")}
"""
    text = ""
    for attempt in range(2):
        text = chat(prompt, temperature=0.78 if attempt == 0 else 0.55, num_predict=2200, timeout=1200)
        text = text.replace("```", "").strip()
        if not _has_junk(text):
            break
        print(f"глава {number}: отбраковка, повтор", flush=True)
        prompt += "\n\nПовтор: только русская проза, без служебных фраз и без других языков."
    if _has_junk(text):
        raise RuntimeError(f"глава {number}: модель снова дала мусор")
    path = CHAPTERS / f"{number:02d}.md"
    write(path, text)
    summary_prompt = f"""Сложи саммари главы {number} для памяти сюжета. 8–12 коротких фактических строк на русском.
Только факты: кто где был, что нашли, что солгали, какие предметы, какие обещания сюжету.
Не пиши оценку стиля.

Глава:
{text[:6000]}
"""
    summary = chat(summary_prompt, temperature=0.2, num_predict=500, timeout=400)
    with FACTS.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## Глава {number}\n{summary.strip()}\n")
    print(f"wrote {path.name} ({len(text)} chars)", flush=True)
    return True


def _strip_meta(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if re.search(r"[\u4e00-\u9fff]", line):
            continue
        if "продолж" in line.casefold() and "требован" in line.casefold():
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n---+\n", "\n\n", cleaned)
    return cleaned


def _has_junk(text: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", text):
        return True
    if "я сейчас" in text.casefold() or "как ии" in text.casefold():
        return True
    return len(text) < 1200


def assemble() -> None:
    if not OUTLINE.is_file():
        raise RuntimeError("нет плана")
    data = json.loads(OUTLINE.read_text(encoding="utf-8"))
    title = str(data.get("title") or "Детектив")
    parts = [f"# {title}", "", str(data.get("logline") or ""), ""]
    for path in sorted(CHAPTERS.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8").strip())
        parts.append("")
    write(BOOK, "\n".join(parts))
    words = len(BOOK.read_text(encoding="utf-8").split())
    print(f"assembled {BOOK} ~{words} слов", flush=True)


def _json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("модель не вернула JSON")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("JSON не объект")
    return payload


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "bible":
        generate_bible()
        return
    if cmd == "chapter":
        generate_next_chapter()
        assemble()
        return
    if cmd == "assemble":
        assemble()
        return
    if cmd == "all":
        if not OUTLINE.is_file():
            generate_bible()
        while generate_next_chapter():
            assemble()
        assemble()
        return
    raise SystemExit("bible | chapter | all | assemble")


if __name__ == "__main__":
    main()
