from modules.settings.models.base import BaseConfig


class General(BaseConfig):
    RefreshSeconds: int = 15

    def as_dict(self) -> dict:
        return {
            "RefreshSeconds": self.RefreshSeconds
        }
