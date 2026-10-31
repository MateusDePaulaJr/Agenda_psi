from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def agenda(request):
    return render(request, "core/agenda.html")
