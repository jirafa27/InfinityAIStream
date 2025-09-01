import re
from transliterate import translit

def transliterate_and_replace_symbols(text):
    symbol_map = {
        '_': 'нижнее подчеркивание ',
    }
    # Сначала заменяем символы
    def replace_symbols(match):
        ch = match.group(0)
        return symbol_map.get(ch, ch)
    text = re.sub(r'[_.,!?:;\-\(\)"\'/@#$%&*+=<>\[\]{}^`~|]', replace_symbols, text)
    # Транслитерация латиницы в кириллицу
    text = translit(text, 'ru')
    return text.lower()


if __name__ == "__main__":
    text = "jirafa_bekvak"
    print(transliterate_and_replace_symbols(text))