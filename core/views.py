from django.shortcuts import render


def home(request):
    """
    Public landing page.
    Logged-out users land here.
    Logged-in users still see this unless redirected elsewhere later.
    """
    return render(request, "core/home.html")
