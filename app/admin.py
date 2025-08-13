from django.contrib import admin
from .models import League, Team, Match, ScrapeJob


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ScrapeJob)
class ScrapeJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'created_at', 'updated_at')
    search_fields = ('id',)
    actions = None


class HomeMatchInline(admin.TabularInline):
    model = Match
    fk_name = 'home_team'
    extra = 0
    verbose_name = 'Partida como Mandante'
    verbose_name_plural = 'Partidas como Mandante'
    fields = ('league', 'home_team', 'away_team', 'match_date', 'status')
    readonly_fields = ('league', 'home_team', 'away_team', 'match_date', 'status')

class AwayMatchInline(admin.TabularInline):
    model = Match
    fk_name = 'away_team'
    extra = 0
    verbose_name = 'Partida como Visitante'
    verbose_name_plural = 'Partidas como Visitante'
    fields = ('league', 'home_team', 'away_team', 'match_date', 'status')
    readonly_fields = ('league', 'home_team', 'away_team', 'match_date', 'status')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    inlines = [HomeMatchInline, AwayMatchInline]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('id',
                    'home_team', 'away_team', 'league', 'match_date', 'status',
                    'predictz_home_score', 'predictz_away_score',
                    'user_predicted_home_score', 'user_predicted_away_score',
                    'actual_home_score', 'actual_away_score',
                    'match_link',
                    )
    list_filter = ('status', 'league', 'match_date')
    list_editable = (
        'predictz_home_score', 'predictz_away_score',
        'user_predicted_home_score', 'user_predicted_away_score',
        'actual_home_score', 'actual_away_score',
        'match_link',
    )
    search_fields = ('home_team__name', 'away_team__name', 'league__name')
