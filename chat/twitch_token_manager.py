import os
import requests

from dotenv import load_dotenv

from core.config import Config

class TokenManager:
    def __init__(self, env_path='.env.twitch'):
        self.env_path = env_path
        self._load_env()

    def _load_env(self):
        load_dotenv(self.env_path)
        self.client_id = Config.TWITCH_CLIENT_ID
        self.client_secret = Config.TWITCH_CLIENT_SECRET
        self.refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")
        self.access_token = os.getenv("TWITCH_ACCESS_TOKEN")

    def refresh_twitch_token(self):
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        resp = requests.post(url, params=params)
        data = resp.json()
        new_access_token = data["access_token"]
        new_refresh_token = data.get("refresh_token", self.refresh_token)
        # Перезаписываем .env
        with open(self.env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(self.env_path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.startswith("TWITCH_ACCESS_TOKEN="):
                    f.write(f"TWITCH_ACCESS_TOKEN={new_access_token}\n")
                elif line.startswith("TWITCH_REFRESH_TOKEN="):
                    f.write(f"TWITCH_REFRESH_TOKEN={new_refresh_token}\n")
                else:
                    f.write(line)
        print("Токен обновлён и .env.twitch перезаписан.")
        # Обновляем переменные
        self.access_token = new_access_token
        self.refresh_token = new_refresh_token
        return new_access_token

    def get_token(self):
        return self.access_token
    

if __name__ == "__main__":
    token_manager = TokenManager()
    print(token_manager.refresh_twitch_token())