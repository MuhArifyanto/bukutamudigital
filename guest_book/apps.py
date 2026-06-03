from django.apps import AppConfig


class GuestBookConfig(AppConfig):
    name = 'guest_book'

    def ready(self):
        import guest_book.signals
