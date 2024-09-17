# api/views.py

from django.shortcuts import render
from .models import Game

def game_list(request):
    games = Game.objects.all().order_by('week')
    return render(request, 'game_list.html', {'games': games})


