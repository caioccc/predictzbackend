# from django.db import models
from django.db import models
from django.conf import settings
# Create your models here.

class League(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Team(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Match(models.Model):
    STATUS_CHOICES = [
        ('SCHEDULED', 'Agendado'),
        ('FINISHED', 'Finalizado'),
        ('IN_PROGRESS', 'Em andamento'),
    ]

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches')
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    match_date = models.DateTimeField()
    match_link = models.URLField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    predictz_home_score = models.IntegerField()
    predictz_away_score = models.IntegerField()
    user_predicted_home_score = models.IntegerField(null=True, blank=True)
    user_predicted_away_score = models.IntegerField(null=True, blank=True)
    actual_home_score = models.IntegerField(null=True, blank=True)
    actual_away_score = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.home_team} x {self.away_team} ({self.match_date:%d/%m/%Y %H:%M})"

    @staticmethod
    def _get_outcome(home_score, away_score):
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return 'HOME_WIN'
        elif home_score < away_score:
            return 'AWAY_WIN'
        else:
            return 'DRAW'

    @property
    def predictz_outcome(self):
        return self._get_outcome(self.predictz_home_score, self.predictz_away_score)

    @property
    def user_outcome(self):
        if self.user_predicted_home_score is None or self.user_predicted_away_score is None:
            return None
        return self._get_outcome(self.user_predicted_home_score, self.user_predicted_away_score)

    @property
    def actual_outcome(self):
        if self.actual_home_score is None or self.actual_away_score is None:
            return None
        return self._get_outcome(self.actual_home_score, self.actual_away_score)

    @property
    def user_outcome_correct(self):
        return self.user_outcome is not None and self.actual_outcome is not None and self.user_outcome == self.actual_outcome

    @property
    def user_score_correct(self):
        return (
            self.user_predicted_home_score is not None and self.user_predicted_away_score is not None and
            self.actual_home_score is not None and self.actual_away_score is not None and
            self.user_predicted_home_score == self.actual_home_score and self.user_predicted_away_score == self.actual_away_score
        )

    @property
    def predictz_outcome_correct(self):
        return self.predictz_outcome is not None and self.actual_outcome is not None and self.predictz_outcome == self.actual_outcome

    @property
    def predictz_score_correct(self):
        return (
            self.predictz_home_score is not None and self.predictz_away_score is not None and
            self.actual_home_score is not None and self.actual_away_score is not None and
            self.predictz_home_score == self.actual_home_score and self.predictz_away_score == self.actual_away_score
        )
