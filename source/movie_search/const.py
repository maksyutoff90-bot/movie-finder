"""Справочники жанров и стран (единые для офлайн-базы и TMDb)."""

from __future__ import annotations

# Жанры TMDb: id -> каноническое русское название в нижнем регистре.
GENRE_IDS: dict[int, str] = {
    28: "боевик",
    12: "приключения",
    16: "мультфильм",
    35: "комедия",
    80: "криминал",
    99: "документальный",
    18: "драма",
    10751: "семейный",
    14: "фэнтези",
    36: "история",
    27: "ужасы",
    10402: "музыка",
    9648: "детектив",
    10749: "мелодрама",
    878: "фантастика",
    53: "триллер",
    10752: "военный",
    37: "вестерн",
}

# Порядок жанров в интерфейсе.
GENRE_ORDER: list[str] = [
    "боевик",
    "приключения",
    "комедия",
    "драма",
    "триллер",
    "детектив",
    "криминал",
    "фантастика",
    "фэнтези",
    "ужасы",
    "мелодрама",
    "семейный",
    "мультфильм",
    "история",
    "военный",
    "вестерн",
    "музыка",
    "документальный",
]

GENRE_BY_NAME = {name: gid for gid, name in GENRE_IDS.items()}

# Английские подписи для интерфейсного переключателя; в базе жанры остаются каноническими русскими.
GENRE_NAMES_EN: dict[str, str] = {
    "боевик": "Action",
    "приключения": "Adventure",
    "мультфильм": "Animation",
    "комедия": "Comedy",
    "криминал": "Crime",
    "документальный": "Documentary",
    "драма": "Drama",
    "семейный": "Family",
    "фэнтези": "Fantasy",
    "история": "History",
    "ужасы": "Horror",
    "музыка": "Music",
    "детектив": "Mystery",
    "мелодрама": "Romance",
    "фантастика": "Science fiction",
    "триллер": "Thriller",
    "военный": "War",
    "вестерн": "Western",
}

COUNTRIES_EN: dict[str, str] = {
    "US": "United States", "RU": "Russia", "SU": "USSR", "GB": "United Kingdom",
    "FR": "France", "DE": "Germany", "IT": "Italy", "ES": "Spain",
    "CA": "Canada", "AU": "Australia", "JP": "Japan", "KR": "South Korea",
    "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "IN": "India",
    "BR": "Brazil", "MX": "Mexico", "AR": "Argentina", "CL": "Chile",
    "CO": "Colombia", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "IS": "Iceland", "NL": "Netherlands", "BE": "Belgium",
    "CH": "Switzerland", "AT": "Austria", "PL": "Poland", "CZ": "Czechia",
    "SK": "Slovakia", "HU": "Hungary", "RO": "Romania", "BG": "Bulgaria",
    "RS": "Serbia", "HR": "Croatia", "SI": "Slovenia", "LT": "Lithuania",
    "LV": "Latvia", "EE": "Estonia", "UA": "Ukraine", "KZ": "Kazakhstan",
    "GE": "Georgia", "AM": "Armenia", "TR": "Turkey", "IL": "Israel",
    "IR": "Iran", "IE": "Ireland", "NZ": "New Zealand", "ZA": "South Africa",
    "EG": "Egypt", "TH": "Thailand", "ID": "Indonesia", "PH": "Philippines",
    "VN": "Vietnam", "PT": "Portugal", "GR": "Greece",
}

CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "all": ("Любая", "Any"),
    "uplifting": ("Настроение · Воодушевляющее", "Mood · Uplifting"),
    "light": ("Настроение · Лёгкое и смешное", "Mood · Light & funny"),
    "tense": ("Настроение · Напряжённое", "Mood · Suspenseful"),
    "romantic": ("Настроение · Романтическое", "Mood · Romantic"),
    "thoughtful": ("Настроение · На подумать", "Mood · Mind-bending"),
    "family_night": ("Настроение · Для семейного вечера", "Mood · Family night"),
    "horror": ("Тема · Ужасы", "Theme · Horror"),
    "zombies": ("Тема · Зомби и эпидемии", "Theme · Zombies & outbreaks"),
    "aliens": ("Тема · НЛО и пришельцы", "Theme · UFOs & aliens"),
    "science_fiction": ("Тема · Фантастика и космос", "Theme · Sci-fi & space"),
    "mystery": ("Тема · Детективы и тайны", "Theme · Mystery & crime"),
    "adventure": ("Тема · Приключения", "Theme · Adventure"),
    "historical": ("Тема · История и война", "Theme · History & war"),
    "documentary": ("Тема · Документальное кино", "Theme · Documentary"),
    "disasters": ("Тема · Катастрофы и выживание", "Theme · Disasters & survival"),
    "vampires": ("Тема · Вампиры и оборотни", "Theme · Vampires & werewolves"),
    "ghosts": ("Тема · Призраки и потустороннее", "Theme · Ghosts & supernatural"),
    "witchcraft": ("Тема · Магия и ведьмы", "Theme · Magic & witches"),
    "time_travel": ("Тема · Путешествия во времени", "Theme · Time travel"),
    "ai_robots": ("Тема · Роботы и ИИ", "Theme · Robots & AI"),
    "heists": ("Тема · Ограбления", "Theme · Heists"),
    "spies": ("Тема · Шпионы и разведка", "Theme · Spies & espionage"),
    "martial_arts": ("Тема · Боевые искусства", "Theme · Martial arts"),
    "sports": ("Тема · Спорт", "Theme · Sports"),
    "pirates": ("Тема · Пираты", "Theme · Pirates"),
    "revenge": ("Тема · Месть", "Theme · Revenge"),
    "mythology": ("Тема · Мифы и легенды", "Theme · Mythology & legends"),
    "monsters": ("Тема · Монстры", "Theme · Monsters"),
}

CATEGORY_ORDER: list[str] = [
    "uplifting", "light", "tense", "romantic", "thoughtful", "family_night",
    "horror", "zombies", "aliens", "science_fiction", "mystery", "adventure",
    "historical", "documentary", "disasters", "vampires", "ghosts", "witchcraft",
    "time_travel", "ai_robots", "heists", "spies", "martial_arts", "sports",
    "pirates", "revenge", "mythology", "monsters",
]

# Каждая подборка объединяет жанры и ключевые слова (RU/EN) из описаний и TMDb keywords.
CATEGORY_FILTERS: dict[str, dict[str, tuple[str, ...]]] = {
    "uplifting": {
        "genres": ("комедия", "драма", "приключения", "семейный"),
        "terms": ("uplifting", "inspiring", "inspirational", "feel-good", "feel good", "hope", "friendship", "overcoming", "triumph", "воодушев", "вдохнов", "надежд", "дружб", "преодол"),
    },
    "light": {
        "genres": ("комедия", "семейный", "мультфильм"),
        "terms": ("feel-good", "feel good", "lighthearted", "funny", "humorous", "feelgood", "лёгк", "легк", "смешн", "добрая комедия"),
    },
    "tense": {
        "genres": ("триллер", "ужасы", "боевик", "криминал"),
        "terms": ("suspense", "survival", "chase", "cat and mouse", "high stakes", "выживан", "погон", "напряж", "охотится"),
    },
    "romantic": {
        "genres": ("мелодрама", "комедия", "драма"),
        "terms": ("romance", "romantic", "love story", "relationship", "wedding", "влюб", "любов", "романтичес", "свадьб"),
    },
    "thoughtful": {
        "genres": ("фантастика", "детектив", "драма", "триллер"),
        "terms": ("mind-bending", "time loop", "time travel", "parallel universe", "identity", "conspiracy", "philosophical", "временная петля", "путешеств во времени", "параллельная вселенная", "заговор", "личность"),
    },
    "family_night": {
        "genres": ("семейный", "мультфильм", "приключения", "комедия"),
        "terms": ("family-friendly", "family film", "for the whole family", "семейный просмотр", "для всей семьи"),
    },
    "horror": {
        "genres": ("ужасы",),
        "terms": ("horror", "haunted", "supernatural", "ghost", "demon", "vampire", "werewolf", "ужас", "призрак", "демон", "вампир", "оборотень", "нечисть"),
    },
    "zombies": {
        "genres": (),
        "terms": ("zombie", "zombies", "undead", "living dead", "walking dead", "infected", "infection", "outbreak", "viral outbreak", "zombie apocalypse", "pandemic", "epidemic", "plague", "зомби", "живые мертвецы", "ходячие мертвецы", "эпидемия", "пандем", "чума", "заражён", "заражен", "вирус"),
    },
    "aliens": {
        "genres": (),
        "terms": ("ufo", "u.f.o.", "alien", "aliens", "extraterrestrial", "extraterrestrials", "flying saucer", "alien invasion", "alien abduction", "first contact", "unidentified flying object", "нло", "инопланет", "пришелец", "пришельцы", "внеземн", "летающая тарелка", "контакт с пришельцами"),
    },
    "science_fiction": {
        "genres": ("фантастика",),
        "terms": ("science fiction", "sci-fi", "space travel", "space exploration", "dystopia", "artificial intelligence", "robot", "космическ", "будущего", "антиутоп", "искусственный интеллект", "робот"),
    },
    "mystery": {
        "genres": ("детектив", "криминал", "триллер"),
        "terms": ("detective", "mystery", "investigation", "whodunit", "murder mystery", "расследован", "убийств", "загадочн", "тайна", "сыщик"),
    },
    "adventure": {
        "genres": ("приключения", "боевик", "фэнтези"),
        "terms": ("adventure", "quest", "journey", "expedition", "путешеств", "экспедиц", "приключен", "поиски"),
    },
    "historical": {
        "genres": ("история", "военный"),
        "terms": ("historical drama", "based on a true story", "world war", "civil war", "историческ", "основан на реальных событиях", "мировая война", "гражданская война"),
    },
    "documentary": {
        "genres": ("документальный",),
        "terms": ("documentary", "документальн"),
    },
    "disasters": {
        "genres": (),
        "terms": ("disaster", "natural disaster", "earthquake", "tsunami", "volcano", "hurricane", "tornado", "flood", "asteroid", "meteor", "catastrophe", "post-apocalyptic", "post apocalyptic", "apocalypse", "survival", "катастроф", "землетряс", "цунами", "извержен", "наводнен", "апокалипс", "постапокалип", "конец света", "выживан"),
    },
    "vampires": {
        "genres": (),
        "terms": ("vampire", "vampires", "vampire hunter", "dracula", "werewolf", "werewolves", "lycanthrope", "вампир", "дракул", "оборотн", "вервольф"),
    },
    "ghosts": {
        "genres": (),
        "terms": ("ghost", "haunted", "haunting", "haunted house", "poltergeist", "paranormal", "spirit", "призрак", "привид", "дом с привидениями", "полтергейст", "паранормаль", "дух"),
    },
    "witchcraft": {
        "genres": (),
        "terms": ("witch", "witchcraft", "wizard", "sorcery", "magic", "magic spell", "magical powers", "ведьм", "колдун", "магия", "волшеб", "заклинан", "чародей", "колдов"),
    },
    "time_travel": {
        "genres": (),
        "terms": ("time travel", "time traveler", "time machine", "time loop", "time paradox", "temporal paradox", "путешеств во времени", "машина времени", "временная петля", "петля времени", "временной парадокс"),
    },
    "ai_robots": {
        "genres": (),
        "terms": ("artificial intelligence", "a.i.", "robot", "android", "cyborg", "sentient machine", "искусственный интеллект", "робот", "андроид", "киборг"),
    },
    "heists": {
        "genres": (),
        "terms": ("heist", "bank robbery", "bank heist", "robbery", "caper", "jewel theft", "ограблен", "кража", "налёт на банк"),
    },
    "spies": {
        "genres": (),
        "terms": ("spy", "espionage", "secret agent", "undercover agent", "intelligence agency", "cold war spy", "шпион", "шпионаж", "секретный агент", "разведчик", "тайный агент"),
    },
    "martial_arts": {
        "genres": (),
        "terms": ("martial arts", "kung fu", "karate", "judo", "taekwondo", "ninja", "samurai", "боевые искусства", "кунг-фу", "карате", "дзюдо", "тхэквондо", "ниндзя", "самурай"),
    },
    "sports": {
        "genres": (),
        "terms": ("sports film", "sports movie", "sports team", "boxing", "football", "soccer", "basketball", "baseball", "ice hockey", "racing", "athlete", "спортивн", "бокс", "футбол", "баскетбол", "бейсбол", "хоккей", "гонки", "спортсмен"),
    },
    "pirates": {
        "genres": (),
        "terms": ("pirate", "pirates", "piracy", "pirate ship", "pirate captain", "пират", "пиратский корабль"),
    },
    "revenge": {
        "genres": (),
        "terms": ("revenge", "vengeance", "revenge killing", "revenge motive", "vigilante", "месть", "отомст", "самосуд"),
    },
    "mythology": {
        "genres": (),
        "terms": ("mythology", "greek mythology", "norse mythology", "egyptian mythology", "folklore", "legend", "мифолог", "миф", "легенд", "фольклор"),
    },
    "monsters": {
        "genres": (),
        "terms": ("monster", "monsters", "giant monster", "sea monster", "kaiju", "creature feature", "чудовище", "монстр", "гигантское чудовище", "кайдзю"),
    },
}

# Страны: ISO-код -> название по-русски.
COUNTRIES: dict[str, str] = {
    "US": "США",
    "RU": "Россия",
    "SU": "СССР",
    "GB": "Великобритания",
    "FR": "Франция",
    "DE": "Германия",
    "IT": "Италия",
    "ES": "Испания",
    "CA": "Канада",
    "AU": "Австралия",
    "JP": "Япония",
    "KR": "Южная Корея",
    "CN": "Китай",
    "HK": "Гонконг",
    "TW": "Тайвань",
    "IN": "Индия",
    "BR": "Бразилия",
    "MX": "Мексика",
    "AR": "Аргентина",
    "CL": "Чили",
    "CO": "Колумбия",
    "SE": "Швеция",
    "NO": "Норвегия",
    "DK": "Дания",
    "FI": "Финляндия",
    "IS": "Исландия",
    "NL": "Нидерланды",
    "BE": "Бельгия",
    "CH": "Швейцария",
    "AT": "Австрия",
    "PL": "Польша",
    "CZ": "Чехия",
    "SK": "Словакия",
    "HU": "Венгрия",
    "RO": "Румыния",
    "BG": "Болгария",
    "RS": "Сербия",
    "HR": "Хорватия",
    "SI": "Словения",
    "LT": "Литва",
    "LV": "Латвия",
    "EE": "Эстония",
    "UA": "Украина",
    "KZ": "Казахстан",
    "GE": "Грузия",
    "AM": "Армения",
    "TR": "Турция",
    "IL": "Израиль",
    "IR": "Иран",
    "IE": "Ирландия",
    "NZ": "Новая Зеландия",
    "ZA": "ЮАР",
    "EG": "Египет",
    "TH": "Таиланд",
    "ID": "Индонезия",
    "PH": "Филиппины",
    "VN": "Вьетнам",
    "PT": "Португалия",
    "GR": "Греция",
}

# Названия стран так, как они пишутся в «Википедии» (для разбора инфобоксов не нужно,
# но удобно для офлайн-каталога).
COUNTRY_BY_LABEL = {label.lower(): code for code, label in COUNTRIES.items()}

MIN_YEAR = 1874
MAX_YEAR = 2026

# Диапазон фоновой загрузки из TMDb: 150+ лет по 3 страницы — это слишком долго,
# поэтому каталог скачивается с 1990 года, а старые фильмы приходят из импорта.
SYNC_FROM_YEAR = 1990
SYNC_TO_YEAR = 2026

SORT_LABELS: dict[str, str] = {
    "rating": "Сначала высокий рейтинг",
    "votes": "Сначала популярные",
    "year_new": "Сначала новые",
    "year_old": "Сначала старые",
    "title": "По алфавиту",
}


def genre_label(name: str) -> str:
    """'фантастика' -> 'Фантастика'."""
    return name[:1].upper() + name[1:]


def category_label(name: str, english: bool = False) -> str:
    """Возвращает подпись подборки на русском или английском языке."""
    russian, english_name = CATEGORY_LABELS[name]
    return english_name if english else russian


def country_label(code: str) -> str:
    """'US' -> 'США'; неизвестный код возвращается как есть."""
    return COUNTRIES.get(code.upper(), code.upper())


def country_title(codes: str) -> str:
    """',US,GB,' -> 'США, Великобритания'."""
    items = [c for c in codes.split(",") if c]
    return ", ".join(country_label(c) for c in items)
