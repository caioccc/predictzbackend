import csv
import datetime

from django.db.models import Count, F, Q, Subquery, OuterRef
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import League, Match, Team
from .serializers import MatchSerializer, TeamSerializer, TeamStatsSerializer, LeagueSerializer
from .utils_selenium import scrape_predictz_selenium


class LeagueViewSet(viewsets.ModelViewSet):
    queryset = League.objects.all().order_by('name')
    serializer_class = LeagueSerializer
    permission_classes = [AllowAny]
    pagination_class = None


class ScrapeRangeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Coleta do mês passado até hoje + 3 dias
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=30)
        end_date = today + datetime.timedelta(days=3)
        results = []
        for n in range((end_date - start_date).days + 1):
            d = start_date + datetime.timedelta(days=n)
            date_str = d.strftime('%Y%m%d')
            try:
                result = scrape_predictz_selenium(date_str)
                print(f'Resultado para {date_str}: {result.get("added", 0)} adicionados, {result.get("updated", 0)} atualizados')
                results.append({'date': date_str, 'added': result.get('added', 0), 'updated': result.get('updated', 0)})
            except Exception as e:
                print(f'Erro ao processar {date_str}: {e}')
                results.append({'date': date_str, 'error': str(e)})
        return Response({'detail': 'Coleta concluída.', 'results': results})


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'list':
            return TeamStatsSerializer
        return TeamSerializer

    def get_queryset(self):
        queryset = Team.objects.annotate(
            num_matches=Count('home_matches', distinct=True) + Count('away_matches', distinct=True),
            wins=Count('home_matches', filter=Q(home_matches__actual_home_score__gt=F('home_matches__actual_away_score'))) +
                 Count('away_matches', filter=Q(away_matches__actual_away_score__gt=F('away_matches__actual_home_score'))),
            draws=Count('home_matches', filter=Q(home_matches__actual_home_score=F('home_matches__actual_away_score'))) +
                  Count('away_matches', filter=Q(away_matches__actual_away_score=F('away_matches__actual_home_score'))),
            losses=Count('home_matches', filter=Q(home_matches__actual_home_score__lt=F('home_matches__actual_away_score'))) +
                   Count('away_matches', filter=Q(away_matches__actual_away_score__lt=F('away_matches__actual_home_score'))),
        ).prefetch_related('home_matches__league', 'away_matches__league')

        # Adiciona as ligas distintas
        leagues_subquery = League.objects.filter(
            matches__home_team=OuterRef('pk')
        ).distinct().union(
            League.objects.filter(matches__away_team=OuterRef('pk')).distinct()
        )
        queryset = queryset.annotate(
            leagues_list=Subquery(leagues_subquery.values('name'))
        )

        # Filtros
        league_id = self.request.query_params.get('league_id')
        name = self.request.query_params.get('name')
        if league_id:
            queryset = queryset.filter(Q(home_matches__league_id=league_id) | Q(away_matches__league_id=league_id)).distinct()
        if name:
            queryset = queryset.filter(name__icontains=name)

        return queryset.order_by('name')

    @action(detail=True, methods=['get'])
    def matches(self, request, pk=None):
        team = self.get_object()
        # Busca partidas onde o time é mandante ou visitante
        matches = Match.objects.filter(
            Q(home_team=team) | Q(away_team=team)
        ).order_by('-match_date')
        paginator = LimitOffsetPagination()
        paginated = paginator.paginate_queryset(matches, request)
        serializer = MatchSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)


# Endpoints para exportar/importar dados em CSV
class DataExportImportView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Exporta todos os dados em CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="dados_predictz.csv"'
        writer = csv.writer(response)

        # Exporta ligas
        writer.writerow(['LEAGUES'])
        writer.writerow(['id', 'name'])
        for league in League.objects.all():
            writer.writerow([league.id, league.name])

        # Exporta times
        writer.writerow([])
        writer.writerow(['TEAMS'])
        writer.writerow(['id', 'name'])
        for team in Team.objects.all():
            writer.writerow([team.id, team.name])

        # Exporta partidas
        writer.writerow([])
        writer.writerow(['MATCHES'])
        writer.writerow(
            ['id', 'league_id', 'home_team_id', 'away_team_id', 'match_date', 'status', 'predictz_home_score',
             'predictz_away_score', 'user_predicted_home_score', 'user_predicted_away_score', 'actual_home_score',
             'actual_away_score'])
        for match in Match.objects.all():
            writer.writerow([
                match.id, match.league_id, match.home_team_id, match.away_team_id,
                match.match_date, match.status, match.predictz_home_score, match.predictz_away_score,
                match.user_predicted_home_score, match.user_predicted_away_score,
                match.actual_home_score, match.actual_away_score
            ])
        return response

    def post(self, request):
        # Importa dados de um arquivo CSV enviado
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Arquivo CSV não enviado.'}, status=400)
        decoded = file.read().decode('utf-8').splitlines()
        reader = csv.reader(decoded)
        mode = None
        for row in reader:
            if not row:
                continue
            if row[0] == 'LEAGUES':
                mode = 'league'
                next(reader)  # pula header
                continue
            if row[0] == 'TEAMS':
                mode = 'team'
                next(reader)
                continue
            if row[0] == 'MATCHES':
                mode = 'match'
                next(reader)
                continue
            if mode == 'league':
                League.objects.update_or_create(id=row[0], defaults={'name': row[1]})
            elif mode == 'team':
                Team.objects.update_or_create(id=row[0], defaults={'name': row[1]})
            elif mode == 'match':
                Match.objects.update_or_create(
                    id=row[0],
                    defaults={
                        'league_id': row[1],
                        'home_team_id': row[2],
                        'away_team_id': row[3],
                        'match_date': row[4],
                        'status': row[5],
                        'predictz_home_score': row[6],
                        'predictz_away_score': row[7],
                        'user_predicted_home_score': row[8] or None,
                        'user_predicted_away_score': row[9] or None,
                        'actual_home_score': row[10] or None,
                        'actual_away_score': row[11] or None,
                    }
                )
        return Response({'detail': 'Importação concluída.'})

    def delete(self, request):
        Match.objects.all().delete()
        Team.objects.all().delete()
        League.objects.all().delete()
        return Response({'detail': 'Todos os dados foram excluídos.'}, status=200)


# Endpoint para acionar o scraping
class ScrapePredictzView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Recebe a data do frontend (YYYY-MM-DD ou YYYYMMDD)
        date_str = request.data.get('date')
        # Data de hoje e amanhã
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        if not date_str:
            scrape_date = 'today'
        else:
            # Converte para objeto date
            if '-' in date_str:
                try:
                    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                except Exception:
                    date_obj = today
            else:
                try:
                    date_obj = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                except Exception:
                    date_obj = today

            # if date_obj == today:
            #     scrape_date = 'today'
            # elif date_obj == tomorrow:
            #     scrape_date = 'tomorrow'
            # else:
            scrape_date = date_obj.strftime('%Y%m%d')

        try:
            result = scrape_predictz_selenium(scrape_date)
            return Response({'detail': 'Scraping executado com sucesso.', 'result': result})
        except Exception as e:
            return Response({'detail': f'Erro ao executar scraping: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MatchViewSet(viewsets.ModelViewSet):
    serializer_class = MatchSerializer
    permission_classes = [AllowAny]
    queryset = Match.objects.all()

    def list(self, request, *args, **kwargs):
        # filtra por data apenas na listagem
        date_str = self.request.query_params.get('date')
        queryset = Match.objects.all()
        if date_str:
            try:
                if '-' in date_str:
                    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                else:
                    date_obj = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                queryset = queryset.filter(match_date__date=date_obj)
            except Exception:
                pass
        else:
            today = datetime.date.today()
            queryset = queryset.filter(match_date__date=today)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data
        updated = False
        # Atualiza placar real
        if 'actual_home_score' in data:
            instance.actual_home_score = data['actual_home_score']
            updated = True
        if 'actual_away_score' in data:
            instance.actual_away_score = data['actual_away_score']
            updated = True
        # Se ambos preenchidos, marca como FINISHED
        if instance.actual_home_score is not None and instance.actual_away_score is not None:
            instance.status = 'FINISHED'
        if updated:
            instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='update-prediction')
    def update_prediction(self, request, pk=None):
        instance = self.get_object()
        data = request.data
        updated = False
        if 'user_predicted_home_score' in data:
            instance.user_predicted_home_score = data['user_predicted_home_score']
            updated = True
        if 'user_predicted_away_score' in data:
            instance.user_predicted_away_score = data['user_predicted_away_score']
            updated = True
        if updated:
            instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class StatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        matches = Match.objects.filter(status='FINISHED')
        total = matches.count()
        # Só conta para o usuário se ele fez palpite
        user_predicted_matches = matches.filter(user_predicted_home_score__isnull=False,
                                                user_predicted_away_score__isnull=False)
        user_total = user_predicted_matches.count()
        user_outcome_hits = sum(1 for match in user_predicted_matches if match.user_outcome_correct)
        user_score_hits = sum(1 for match in user_predicted_matches if match.user_score_correct)
        predictz_outcome_hits = sum(1 for match in matches if match.predictz_outcome_correct)
        predictz_score_hits = sum(1 for match in matches if match.predictz_score_correct)

        return Response({
            'total': total,
            'user_total': user_total,
            'user_outcome_hits': user_outcome_hits,
            'user_score_hits': user_score_hits,
            'predictz_outcome_hits': predictz_outcome_hits,
            'predictz_score_hits': predictz_score_hits,
        })


class StatsResultsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
            # Paginação por limit/offset
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            league_id = request.query_params.get('league_id')
            start_date = request.query_params.get('start_date')  # formato: YYYY-MM-DD
            end_date = request.query_params.get('end_date')      # formato: YYYY-MM-DD

            matches_qs = Match.objects.filter(status='FINISHED')
            if league_id:
                matches_qs = matches_qs.filter(league_id=league_id)
            if start_date:
                matches_qs = matches_qs.filter(match_date__date__gte=start_date)
            if end_date:
                matches_qs = matches_qs.filter(match_date__date__lte=end_date)
            matches_qs = matches_qs.order_by('-match_date')
            total = matches_qs.count()
            matches = matches_qs[offset:offset + limit]

            results = []
            for match in matches:
                user_outcome = match.user_outcome
                user_score = (match.user_predicted_home_score, match.user_predicted_away_score)
                actual_score = (match.actual_home_score, match.actual_away_score)
                predictz_outcome = match.predictz_outcome
                predictz_score = (match.predictz_home_score, match.predictz_away_score)
                results.append({
                    'id': match.id,
                    'home_team': str(match.home_team),
                    'away_team': str(match.away_team),
                    'league': str(match.league),
                    'league_id': match.league_id,
                    'date': match.match_date,
                    'user_score': user_score,
                    'actual_score': actual_score,
                    'predictz_score': predictz_score,
                    'user_outcome': user_outcome,
                    'actual_outcome': match.actual_outcome,
                    'predictz_outcome': predictz_outcome,
                    'user_outcome_correct': match.user_outcome_correct,
                    'user_score_correct': match.user_score_correct,
                    'predictz_outcome_correct': match.predictz_outcome_correct,
                    'predictz_score_correct': match.predictz_score_correct,
                })

            return Response({
                'count': total,
                'limit': limit,
                'offset': offset,
                'results': results
            })


class StatsAdvancedView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        matches = Match.objects.filter(status='FINISHED')
        total = matches.count()
        if total == 0:
            return Response({
                'total': 0,
                'user_vs_predictz': None,
                'avg_score_diff_user': None,
                'avg_score_diff_predictz': None,
                'user_streak': [],
                'predictz_streak': [],
                'max_discrepancy_matches': [],
                'trend': None,
            })

        # Só conta para o usuário se ele fez palpite
        user_predicted_matches = matches.filter(user_predicted_home_score__isnull=False,
                                                user_predicted_away_score__isnull=False)
        user_total = user_predicted_matches.count()
        # Comparação direta: quem acerta mais
        user_hits = sum(1 for m in user_predicted_matches if m.user_outcome_correct)
        predictz_hits = sum(1 for m in matches if m.predictz_outcome_correct)
        user_vs_predictz = {
            'user_hits': user_hits,
            'predictz_hits': predictz_hits,
            'winner': 'user' if user_hits > predictz_hits else ('predictz' if predictz_hits > user_hits else 'draw'),
            'user_total': user_total,
            'predictz_total': total,
        }

        # Diferença média entre placar previsto e real
        def score_diff(pred_home, pred_away, act_home, act_away):
            if None in [pred_home, pred_away, act_home, act_away]:
                return None
            return abs(pred_home - act_home) + abs(pred_away - act_away)

        user_diffs = [score_diff(m.user_predicted_home_score, m.user_predicted_away_score, m.actual_home_score,
                                 m.actual_away_score) for m in user_predicted_matches]
        predictz_diffs = [
            score_diff(m.predictz_home_score, m.predictz_away_score, m.actual_home_score, m.actual_away_score) for m in
            matches]
        avg_score_diff_user = round(sum(user_diffs) / len(user_diffs), 2) if user_diffs else None
        avg_score_diff_predictz = round(sum(predictz_diffs) / len(predictz_diffs), 2) if predictz_diffs else None

        # Sequência de acertos/erros (streaks)
        def get_streaks(matches, correct_fn):
            streaks = []
            current = None
            count = 0
            for m in matches:
                correct = correct_fn(m)
                if current is None:
                    current = correct
                    count = 1
                elif correct == current:
                    count += 1
                else:
                    streaks.append({'type': 'hit' if current else 'miss', 'length': count})
                    current = correct
                    count = 1
            if count > 0:
                streaks.append({'type': 'hit' if current else 'miss', 'length': count})
            return streaks

        user_streak = get_streaks(user_predicted_matches, lambda m: m.user_outcome_correct)
        predictz_streak = get_streaks(matches, lambda m: m.predictz_outcome_correct)

        # Partidas com maior discrepância entre previsão e resultado
        discrepancy_matches = []
        for m in matches:
            user_diff = score_diff(m.user_predicted_home_score, m.user_predicted_away_score, m.actual_home_score,
                                   m.actual_away_score) if m.user_predicted_home_score is not None and m.user_predicted_away_score is not None else None
            predictz_diff = score_diff(m.predictz_home_score, m.predictz_away_score, m.actual_home_score,
                                       m.actual_away_score)
            max_diff = max([d for d in [user_diff, predictz_diff] if d is not None], default=None)
            discrepancy_matches.append({
                'id': m.id,
                'home_team': str(m.home_team),
                'away_team': str(m.away_team),
                'date': m.match_date,
                'user_diff': user_diff,
                'predictz_diff': predictz_diff,
                'max_diff': max_diff,
            })
        # Top 5 discrepâncias
        max_discrepancy_matches = sorted(discrepancy_matches,
                                         key=lambda x: x['max_diff'] if x['max_diff'] is not None else -1,
                                         reverse=True)[:5]

        # Tendências: últimos 10 jogos
        last10 = list(matches.order_by('-match_date')[:10])
        last10_user = [m for m in last10 if
                       m.user_predicted_home_score is not None and m.user_predicted_away_score is not None]
        trend = {
            'user_hits': sum(1 for m in last10_user if m.user_outcome_correct),
            'predictz_hits': sum(1 for m in last10 if m.predictz_outcome_correct),
            'user_total': len(last10_user),
            'predictz_total': len(last10),
            'total': len(last10),
        }

        return Response({
            'total': total,
            'user_vs_predictz': user_vs_predictz,
            'avg_score_diff_user': avg_score_diff_user,
            'avg_score_diff_predictz': avg_score_diff_predictz,
            'user_streak': user_streak,
            'predictz_streak': predictz_streak,
            'max_discrepancy_matches': max_discrepancy_matches,
            'trend': trend,
        })


class MyPredictionsPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class MyPredictionsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MatchSerializer
    pagination_class = MyPredictionsPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Filtra partidas que possuem palpites do usuário
        return Match.objects.filter(
            user_predicted_home_score__isnull=False,
            user_predicted_away_score__isnull=False
        ).order_by('-match_date')
