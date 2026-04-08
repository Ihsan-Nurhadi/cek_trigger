from django.apps import AppConfig


class ApiAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api_app'

    def ready(self):
        """
        Auto-start background monitor threads saat Django siap.
        Guard menggunakan RUN_MAIN agar tidak double-run di dev server
        (Django dev server spawns 2 proses: 1 reloader + 1 main).
        """
        import os
        # Di dev server: RUN_MAIN='true' hanya ada di proses utama (bukan reloader)
        # Di production (gunicorn/uwsgi): RUN_MAIN tidak di-set, tapi aman karena
        # tidak ada reloader. Kita start monitor di kedua kondisi tersebut.
        run_main = os.environ.get('RUN_MAIN')
        if run_main == 'false':
            return  # Skip di proses reloader

        # Defer import ke dalam method agar tidak jalan sebelum app registry siap
        def _start_monitors():
            try:
                from .hikvision_monitor import monitor_manager
                monitor_manager.start_all()
            except Exception as e:
                print(f'[ApiAppConfig] Monitor startup error: {e}')

        # Jalankan setelah Django siap penuh (delay minimal via thread)
        import threading
        t = threading.Thread(target=_start_monitors, daemon=True, name='monitor-starter')
        t.start()
