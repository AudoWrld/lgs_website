from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import administrator_required
from accounts.models import User

SESSION_KEY = "admin_branch_id"
PER_PAGE = 10


def _resolve_branches(request):
    branches = list(
        request.accessible_branches.filter(is_active=True)
        .order_by("pk")
        .values("id", "name")
    )
    active_ids = {branch["id"] for branch in branches}

    if request.user.branch_id in active_ids:
        default_id = request.user.branch_id
    elif branches:
        default_id = branches[0]["id"]
    else:
        default_id = None

    selected_id = request.session.get(SESSION_KEY)
    if selected_id not in active_ids:
        selected_id = default_id

    return branches, default_id, selected_id


def get_selected_branch(request):
    _, _, selected_id = _resolve_branches(request)
    if selected_id is None:
        return None
    return request.accessible_branches.filter(pk=selected_id).first()



@administrator_required
def admin_dashboard(request):
    return render(
        request,
        "administrator/dashboard.html",
        {"selected_branch": get_selected_branch(request)},
    )


@administrator_required
@require_GET
def branch_options(request):
    branches, default_id, selected_id = _resolve_branches(request)
    return JsonResponse(
        {
            "branches": branches,
            "default_id": default_id,
            "selected_id": selected_id,
        }
    )


@administrator_required
@require_POST
def set_branch(request):
    branches, _, _ = _resolve_branches(request)
    active_ids = {branch["id"] for branch in branches}

    try:
        branch_id = int(request.POST.get("branch_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid branch."}, status=400)

    if branch_id not in active_ids:
        return JsonResponse({"ok": False, "error": "Branch not allowed."}, status=403)

    request.session[SESSION_KEY] = branch_id
    return JsonResponse({"ok": True, "branch_id": branch_id})


@administrator_required
def client_list(request):
    branch = get_selected_branch(request)

    if branch is None:
        customers = []
    else:
        customers = list(
            User.objects.filter(
                role=User.CUSTOMER, branch=branch, is_deleted=False
            )
            .select_related("client_profile", "branch", "created_by")
            .order_by("-date_joined")
        )

    return render(
        request,
        "administrator/client_list.html",
        {
            "selected_branch": branch,
            "customers": customers,
        },
    )


@administrator_required
def employee_list(request):
    branch = get_selected_branch(request)

    if branch is None:
        employees = []
    else:
        employees = list(
            User.objects.filter(
                role__in=User.STAFF_ROLES, branch=branch, is_deleted=False
            )
            .select_related("branch", "created_by")
            .order_by("role", "first_name", "last_name", "email")
        )

    for employee in employees:
        employee.is_self = employee.pk == request.user.pk

    return render(
        request,
        "administrator/employee_list.html",
        {
            "selected_branch": branch,
            "employees": employees,
        },
    )