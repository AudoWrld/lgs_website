from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import EmailAuthenticationForm

User = get_user_model()


def login_view(request):
    if request.user.is_authenticated:
        return redirect("post_login_redirect")

    if request.method == "POST":
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("accounts:post_login_redirect")
    else:
        form = EmailAuthenticationForm(request)

    return render(request, "accounts/login.html", {"form": form})


@login_required
def post_login_redirect(request):
    user = request.user

    if user.must_change_password:
        return redirect("force_password_change")

    if user.is_customer:
        return redirect("customer_dashboard")
    if user.is_reception:
        return redirect("reception_dashboard")
    if user.is_administrator or user.is_superuser:
        return redirect("administrator_dashboard")

    return redirect("login")
