
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Faz scraping dos jogos do Predictz usando Selenium. Permite buscar por hoje, amanhã ou data específica.'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default='today', help="Data no formato YYYYMMDD, 'today' ou 'tomorrow'")

    def handle(self, *args, **options):
        date_arg = options['date']
        from app.utils_selenium import scrape_predictz_selenium
        result = scrape_predictz_selenium(date_arg, stdout=self.stdout)
        self.stdout.write(f"Scraping Selenium finalizado: {result}")
