import os
import asyncio
import aiohttp
from datetime import date
from bs4 import BeautifulSoup
from vkbottle.bot import Bot, Message

# --- Конфигурация из переменных окружения ---
TOKEN = os.environ["TOKEN_VK"]
GROUP_ID = os.environ.get("GROUP_ID", "")

# --- Инициализация бота ---
bot = Bot(token=TOKEN)


async def fetch_schedule_html(group: str):
    """Скачивает HTML-страницу расписания."""
    url = f"https://rasp.pskgu.ru/k/groups/{group}.html"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            raw = await resp.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1251", errors="replace")


def parse_schedule(html: str):
    """Разбирает HTML и возвращает список недель с занятиями."""
    soup = BeautifulSoup(html, "lxml")
    weeks = []
    for week_div in soup.select("div.week"):
        week_num = week_div.get("data-schedule-week", "?")
        days = []
        for row in week_div.select("tr.schedule-day-row"):
            date_str = row.get("data-schedule-date", "")
            iso = row.get("data-schedule-date-iso", "")
            day_name = row.get("data-schedule-day-name", "").strip().rstrip(",")
            lessons = []
            for td in row.select("td.lesson"):
                box = td.select_one("div.lesscount1")
                if not box:
                    continue
                ltype = box.select_one("h3.lessontype")
                subject = box.select_one("div.lessonsubject")
                teacher = box.select_one("div.lessonprep h6")
                aud = box.select_one("div.lessonaud h6")
                lessons.append({
                    "pair": td.get("data-pair-index", ""),
                    "start": td.get("data-start", ""),
                    "end": td.get("data-end", ""),
                    "type": ltype.get_text(strip=True) if ltype else "",
                    "subject": subject.get_text(strip=True) if subject else "",
                    "teacher": teacher.get_text(" ", strip=True) if teacher else "",
                    "aud": aud.get_text(strip=True) if aud else "",
                })
            if lessons:
                days.append({"date": date_str, "iso": iso, "day": day_name, "lessons": lessons})
        if days:
            weeks.append({"num": week_num, "days": days})
    return weeks


def format_week(week: dict, group: str) -> str:
    """Форматирует одну неделю в читаемый текст."""
    lines = [f"📚 Расписание группы {group.upper()} — неделя {week['num']}", ""]
    for d in week["days"]:
        lines.append(f"📅 {d['day']}, {d['date']}")
        for l in d["lessons"]:
            lines.append(f"  {l['pair']}) {l['start']}–{l['end']}  {l['type']} {l['subject']}")
            extra = []
            if l["teacher"]:
                extra.append(f"👤 {l['teacher']}")
            if l["aud"]:
                extra.append(f"🚪 {l['aud']}")
            if extra:
                lines.append("     " + "   ".join(extra))
        lines.append("")
    return "\n".join(lines).strip()


def pick_week(weeks: list):
    """Выбирает текущую неделю (по сегодняшней дате), иначе первую."""
    today_iso = date.today().isoformat()
    for w in weeks:
        for d in w["days"]:
            if d["iso"] == today_iso:
                return w
    return weeks[0] if weeks else None


@bot.on.message(text=["начать", "start", "привет", "/start", "помощь", "help"])
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я бот расписания ПсковГУ.\n\n"
        "Напиши мне название группы — и я пришлю расписание на текущую неделю.\n"
        "Например: 301reu"
    )


@bot.on.message()
async def schedule_handler(message: Message):
    group = (message.text or "").strip().lower()
    if not group:
        await message.answer("Напиши название группы, например: 301reu")
        return

    await message.answer(f"⏳ Ищу расписание для группы {group}...")
    try:
        html = await fetch_schedule_html(group)
        if html is None:
            await message.answer(f"❌ Группа «{group}» не найдена или сайт недоступен.")
            return
        weeks = parse_schedule(html)
        if not weeks:
            await message.answer("В расписании нет занятий.")
            return
        week = pick_week(weeks)
        text = format_week(week, group)
        if len(text) > 4000:
            text = text[:3990] + "\n… (обрезано)"
        await message.answer(text)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")


if __name__ == "__main__":
    print("Бот запущен. Жду сообщения...")
    try:
        asyncio.run(bot.run_polling())
    except KeyboardInterrupt:
        print("Бот остановлен.")