from rest_framework import serializers
from .models import League, Team, Match, ScrapeJob
from django.db.models import Q, F

class LeagueSerializer(serializers.ModelSerializer):
    class Meta:
        model = League
        fields = ['id', 'name']

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name']

class TeamStatsSerializer(serializers.ModelSerializer):
    num_matches = serializers.SerializerMethodField()
    wins = serializers.SerializerMethodField()
    draws = serializers.SerializerMethodField()
    losses = serializers.SerializerMethodField()
    leagues = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'num_matches', 'wins', 'draws', 'losses', 'leagues']

    def get_leagues(self, obj):
        leagues = set()
        for match in obj.home_matches.all():
            if match.league:
                leagues.add(match.league.name)
        for match in obj.away_matches.all():
            if match.league:
                leagues.add(match.league.name)
        return list(leagues)

    def get_num_matches(self, obj):
        return Match.objects.filter(Q(home_team=obj) | Q(away_team=obj), status='FINISHED').count()

    def get_wins(self, obj):
        return Match.objects.filter(
            Q(home_team=obj, actual_home_score__gt=F('actual_away_score')) |
            Q(away_team=obj, actual_away_score__gt=F('actual_home_score')),
            status='FINISHED'
        ).count()

    def get_draws(self, obj):
        return Match.objects.filter(
            Q(home_team=obj, actual_home_score=F('actual_away_score')) |
            Q(away_team=obj, actual_away_score=F('actual_home_score')),
            status='FINISHED'
        ).count()

    def get_losses(self, obj):
        return Match.objects.filter(
            Q(home_team=obj, actual_home_score__lt=F('actual_away_score')) |
            Q(away_team=obj, actual_away_score__lt=F('actual_home_score')),
            status='FINISHED'
        ).count()

class MatchSerializer(serializers.ModelSerializer):
    league = serializers.StringRelatedField()
    home_team = serializers.StringRelatedField()
    away_team = serializers.StringRelatedField()
    home_team_id = serializers.IntegerField(source='home_team.id', read_only=True)
    away_team_id = serializers.IntegerField(source='away_team.id', read_only=True)

    match_link = serializers.URLField(required=False, allow_null=True)

    class Meta:
        model = Match
        fields = [
            'id', 'league', 'home_team', 'home_team_id', 'away_team', 'away_team_id', 'match_date', 'status',
            'predictz_home_score', 'predictz_away_score',
            'user_predicted_home_score', 'user_predicted_away_score',
            'actual_home_score', 'actual_away_score',
            'match_link'
        ]

class ScrapeJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapeJob
        fields = ['id', 'status', 'payload', 'result', 'created_at', 'updated_at']
