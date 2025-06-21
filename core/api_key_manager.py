# core/api_key_manager.py
import json
import os

API_KEYS_FILE = "api_keys.json"

class ApiKeyManager:
    def __init__(self):
        self.keys = self._load()

    def _load(self):
        if not os.path.exists(API_KEYS_FILE):
            return {}
        try:
            with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save(self):
        with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.keys, f, indent=4)

    def get_key_names(self):
        return list(self.keys.keys())

    def get_key_value(self, name):
        return self.keys.get(name, "")

    def add_or_update_key(self, name, value):
        if not name or not value:
            return False, "Имя и ключ не могут быть пустыми."
        self.keys[name] = value
        self._save()
        return True, f"Ключ '{name}' сохранен."

    def delete_key(self, name):
        if name in self.keys:
            del self.keys[name]
            self._save()
            return True, f"Ключ '{name}' удален."
        return False, "Ключ не найден."