import re
import socket
from transliterate import translit


def is_tcp_port_in_use(host: str, port: int) -> bool:
    """True, если порт уже занят (слушает другой процесс)."""
    check_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((check_host, port))
            return False
        except OSError:
            return True


def transliterate_and_replace_symbols(text):
    symbol_map = {
        "_": " ",
    }

    # Сначала заменяем символы
    def replace_symbols(match):
        ch = match.group(0)
        return symbol_map.get(ch, ch)

    text = re.sub(r'[_.,!?:;\-\(\)"\'/@#$%&*+=<>\[\]{}^`~|]', replace_symbols, text)
    text = translit(text, "ru")
    return text


if __name__ == "__main__":
    text = "jirafa_bekvak"
    print(transliterate_and_replace_symbols(text))
