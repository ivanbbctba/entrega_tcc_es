from django.shortcuts import render

# Create your views here.
def index(request):
    """
    View function for the home page of the site.
    """
    return render(request, 'public/index.html')
