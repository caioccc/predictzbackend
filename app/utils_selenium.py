import os
import re
import time
from datetime import datetime

import cloudscraper
from bs4 import BeautifulSoup
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import requests

from app.models import League, Match, Team


def get_chrome_options():
    """
    Configura as opções do Chrome para funcionar no Heroku
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-images')
    chrome_options.add_argument('--disable-javascript')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36')

    # Usar perfil do usuário local do Chrome (Windows)
    # chrome_options.add_argument('--user-data-dir=C:/Users/caiom/AppData/Local/Google/Chrome/User Data')
    # chrome_options.add_argument('--profile-directory=Default')

    # Configurações específicas para Heroku
    if os.environ.get('DYNO'):
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--single-process')
        chrome_options.binary_location = '/app/.chrome-for-testing/chrome-linux64/chrome'

    return chrome_options


def get_chrome_driver_path():
    """
    Detecta se está rodando no Heroku e retorna o caminho correto do ChromeDriver
    """
    if os.environ.get('DYNO'):  # Verifica se está no Heroku
        # No Heroku com heroku-buildpack-chrome-for-testing
        return '/app/.chrome-for-testing/chromedriver-linux64/chromedriver'
    else:
        # Desenvolvimento local - usa webdriver_manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            return ChromeDriverManager().install()
        except ImportError:
            return None


def create_chrome_driver():
    """
    Cria uma instância do ChromeDriver configurada para o ambiente
    """
    chrome_options = get_chrome_options()
    driver_path = get_chrome_driver_path()

    if driver_path:
        service = Service(driver_path)
        return webdriver.Chrome(service=service, options=chrome_options)
    else:
        return webdriver.Chrome(options=chrome_options)


def scrape_predictz_selenium(date_arg='today', stdout=None):
    if date_arg == 'today':
        url = 'https://www.predictz.com/predictions/'
    elif date_arg == 'tomorrow':
        url = 'https://www.predictz.com/predictions/tomorrow/'
    else:
        url = f'https://www.predictz.com/predictions/{date_arg}/'

    try:
        driver = create_chrome_driver()
        driver.get(url)
        print(f'Acessando URL: {url}')
        time.sleep(5)  # Aguarda carregamento

        # Usa BeautifulSoup para parsear o HTML renderizado

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        # Tenta encontrar a tabela principal de jogos
        print('Procurando tabela de jogos...')
        pttable = soup.find('div', {'class': 'pttable'})
        if not pttable:
            # fallback para variações
            pttable = soup.find('div', {'class': 'pttable mb30'})
        if not pttable:
            # fallback para qualquer div que contenha jogos
            candidates = soup.find_all('div', {'class': lambda x: x and 'pttable' in x})
            pttable = candidates[0] if candidates else None
        if not pttable:
            if stdout:
                stdout.write('Tabela de jogos não encontrada.')
            driver.quit()
            return {'added': 0, 'updated': 0, 'error': 'Tabela de jogos não encontrada'}

        elements = pttable.find_all(recursive=False)
        league_name = None
        added, updated = 0, 0

        for el in elements:
            class_attr = el.get('class', [])
            # Liga
            if 'pttrnh' in class_attr and 'ptttl' in class_attr:
                h2 = el.find('h2')
                league_name = h2.get_text(strip=True) if h2 else None

            # Partida padrão
            elif 'pttr' in class_attr and 'ptcnt' in class_attr:
                try:
                    home_team = el.find('div', {'class': 'ptmobh'}).get_text(strip=True)
                    away_team = el.find('div', {'class': 'ptmoba'}).get_text(strip=True)
                    pred_box = el.find('div', {'class': 'ptprd'})
                    pred_text = pred_box.get_text(strip=True) if pred_box else ''
                    m = re.match(r'(Home|Away|Draw)\s*(\d+)-(\d+)', pred_text)
                    if m:
                        predictz_home_score = int(m.group(2))
                        predictz_away_score = int(m.group(3))
                    else:
                        predictz_home_score = None
                        predictz_away_score = None

                    match_link = None
                    ptgame_div = el.find('div', {'class': 'pttd ptgame'})
                    if ptgame_div:
                        a_tag = ptgame_div.find('a')
                        if a_tag and a_tag.has_attr('href'):
                            match_link = a_tag['href']

                    match_date = datetime.strptime(date_arg, '%Y%m%d') if date_arg not in ['today', 'tomorrow'] else datetime.today()
                    match_datetime = timezone.make_aware(match_date, timezone.get_current_timezone())
                    print(f'Processando: {league_name} | {home_team} x {away_team} em {match_datetime} | Previsão: {predictz_home_score}-{predictz_away_score}')

                    league_obj, _ = League.objects.get_or_create(name=league_name or '')
                    home_team_obj, _ = Team.objects.get_or_create(name=home_team)
                    away_team_obj, _ = Team.objects.get_or_create(name=away_team)

                    # Dados reais do resultado
                    actual_home_score = None
                    actual_away_score = None
                    # Define status conforme a data
                    if match_date.date() < datetime.today().date():
                        status = 'SCHEDULED'  # será ajustado para FINISHED se resultado encontrado
                    elif match_date.date() == datetime.today().date():
                        status = 'IN_PROGRESS'
                    else:
                        status = 'SCHEDULED'
                    # Só busca resultado se data anterior a hoje e houver link
                    if match_link and match_date.date() < datetime.today().date():
                        try:
                            scraper = cloudscraper.create_scraper(browser='chrome', delay=1)
                            response = scraper.get(match_link)
                            detail_html = response.text
                            detail_soup = BeautifulSoup(detail_html, 'html.parser')
                            result_box = detail_soup.find('div', {'class': 'predodds'})
                            if result_box:
                                score_tag = result_box.find('p', {'class': 'ptxtscore'})
                                outcome_tag = result_box.find('p', {'class': 'ptxtteam'})
                                if score_tag:
                                    score_text = score_tag.get_text(strip=True)
                                    score_match = re.match(r'(\d+)-(\d+)', score_text)
                                    if score_match:
                                        actual_home_score = int(score_match.group(1))
                                        actual_away_score = int(score_match.group(2))
                                        status = 'FINISHED'
                        except Exception as e:
                            print(f'Erro ao buscar resultado: {e}')

                    match_obj, created = Match.objects.update_or_create(
                        home_team=home_team_obj,
                        away_team=away_team_obj,
                        match_date=match_datetime,
                        defaults={
                            'league': league_obj,
                            'predictz_home_score': predictz_home_score or 0,
                            'predictz_away_score': predictz_away_score or 0,
                            'match_link': match_link,
                            'actual_home_score': actual_home_score,
                            'actual_away_score': actual_away_score,
                            'status': status,
                        }
                    )
                    if created:
                        added += 1
                    else:
                        updated += 1
                except Exception as e:
                    if stdout:
                        stdout.write(f'Erro ao processar jogo: {e}')

            # Bloco especial: jogos dentro de w100p
            if 'pttrnh' in class_attr and el.find('div', {'class': 'w100p'}) is not None:
                extra_container = el.find('div', {'class': 'w100p'})
                # Para cada bloco de liga dentro do w100p
                extra_blocks = extra_container.find_all('div', recursive=False)
                current_league = None
                for block in extra_blocks:
                    block_class = block.get('class', [])
                    # Se for título de liga
                    if 'pttrnh' in block_class and 'ptttl' in block_class:
                        h2 = block.find('h2')
                        current_league = h2.get_text(strip=True) if h2 else None
                    # Se for partida
                    elif 'pttr' in block_class and 'ptcnt' in block_class:
                        try:
                            home_team = block.find('div', {'class': 'ptmobh'}).get_text(strip=True)
                            away_team = block.find('div', {'class': 'ptmoba'}).get_text(strip=True)
                            pred_box = block.find('div', {'class': 'ptprd'})
                            pred_text = pred_box.get_text(strip=True) if pred_box else ''
                            m = re.match(r'(Home|Away|Draw)\s*(\d+)-(\d+)', pred_text)
                            if m:
                                predictz_home_score = int(m.group(2))
                                predictz_away_score = int(m.group(3))
                            else:
                                predictz_home_score = None
                                predictz_away_score = None

                            match_link = None
                            ptgame_div = block.find('div', {'class': 'pttd ptgame'})
                            if ptgame_div:
                                a_tag = ptgame_div.find('a')
                                if a_tag and a_tag.has_attr('href'):
                                    match_link = a_tag['href']

                            match_date = datetime.strptime(date_arg, '%Y%m%d') if date_arg not in ['today', 'tomorrow'] else datetime.today()
                            match_datetime = timezone.make_aware(match_date, timezone.get_current_timezone())
                            print(f'Processando EXTRA: {current_league} | {home_team} x {away_team} em {match_datetime} | Previsão: {predictz_home_score}-{predictz_away_score}')

                            league_obj, _ = League.objects.get_or_create(name=current_league or '')
                            home_team_obj, _ = Team.objects.get_or_create(name=home_team)
                            away_team_obj, _ = Team.objects.get_or_create(name=away_team)

                            actual_home_score = None
                            actual_away_score = None
                            status = 'SCHEDULED'
                            if match_link and match_date.date() < datetime.today().date():
                                try:
                                    scraper = cloudscraper.create_scraper(browser='chrome', delay=1)
                                    response = scraper.get(match_link)
                                    detail_html = response.text
                                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                                    result_box = detail_soup.find('div', {'class': 'predodds'})
                                    if result_box:
                                        score_tag = result_box.find('p', {'class': 'ptxtscore'})
                                        outcome_tag = result_box.find('p', {'class': 'ptxtteam'})
                                        if score_tag:
                                            score_text = score_tag.get_text(strip=True)
                                            score_match = re.match(r'(\d+)-(\d+)', score_text)
                                            if score_match:
                                                actual_home_score = int(score_match.group(1))
                                                actual_away_score = int(score_match.group(2))
                                                status = 'FINISHED'
                                    # Retorna para página principal
                                    driver.get(url)
                                    time.sleep(1)
                                except Exception as e:
                                    print(f'Erro ao buscar resultado: {e}')

                            match_obj, created = Match.objects.update_or_create(
                                home_team=home_team_obj,
                                away_team=away_team_obj,
                                match_date=match_datetime,
                                defaults={
                                    'league': league_obj,
                                    'predictz_home_score': predictz_home_score or 0,
                                    'predictz_away_score': predictz_away_score or 0,
                                    'match_link': match_link,
                                    'actual_home_score': actual_home_score,
                                    'actual_away_score': actual_away_score,
                                    'status': status,
                                }
                            )
                            if created:
                                added += 1
                            else:
                                updated += 1
                        except Exception as e:
                            if stdout:
                                stdout.write(f'Erro ao processar jogo extra: {e}')
        driver.quit()
        if stdout:
            stdout.write(f'Jogos adicionados: {added} | Jogos atualizados: {updated}')
        return {'added': added, 'updated': updated}
    except ImportError as e:
        if stdout:
            stdout.write(f'Erro de importação: {e}')
        return {'added': 0, 'updated': 0, 'error': str(e)}
