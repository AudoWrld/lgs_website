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


def _page_items(page_obj):
    total = page_obj.paginator.num_pages
    current = page_obj.number
    pages = sorted(
        {1, total} | {p for p in range(current - 1, current + 2) if 1 <= p <= total}
    )
    items = []
    previous = None
    for number in pages:
        if previous is not None and number - previous > 1:
            items.append(None)
        items.append(number)
        previous = number
    return items


def _paginate(request, queryset):
    paginator = Paginator(queryset, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return page_obj, _page_items(page_obj)


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
    search_query = request.GET.get("q", "").strip()

    if branch is None:
        customers = User.objects.none()
    else:
        customers = User.objects.filter(
            role=User.CUSTOMER, branch=branch, is_deleted=False
        ).select_related("client_profile", "branch", "created_by")

        if search_query:
            customers = customers.filter(
                Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(whatsapp_number__icontains=search_query)
                | Q(client_profile__client_name__icontains=search_query)
                | Q(client_profile__contact_person__icontains=search_query)
            )

        customers = customers.order_by("-date_joined")

    page_obj, page_items = _paginate(request, customers)

    return render(
        request,
        "administrator/client_list.html",
        {
            "selected_branch": branch,
            "page_obj": page_obj,
            "page_items": page_items,
            "customers": page_obj.object_list,
            "search_query": search_query,
        },
    )


@administrator_required
def employee_list(request):
    branch = get_selected_branch(request)
    search_query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if branch is None:
        employees = User.objects.none()
    else:
        employees = User.objects.filter(
            role__in=User.STAFF_ROLES, branch=branch, is_deleted=False
        ).select_related("branch", "created_by")

        if status == "active":
            employees = employees.filter(is_active=True)
        elif status == "inactive":
            employees = employees.filter(is_active=False)

        if search_query:
            employees = employees.filter(
                Q(email__icontains=search_query)
                | Q(employee_id__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(whatsapp_number__icontains=search_query)
                | Q(role__icontains=search_query.replace(" ", "_"))
            )

        employees = employees.order_by("role", "first_name", "last_name", "email")

    page_obj, page_items = _paginate(request, employees)

    employee_rows = list(page_obj.object_list)
    for employee in employee_rows:
        employee.is_self = employee.pk == request.user.pk

    return render(
        request,
        "administrator/employee_list.html",
        {
            "selected_branch": branch,
            "page_obj": page_obj,
            "page_items": page_items,
            "employees": employee_rows,
            "search_query": search_query,
            "status": status,
        },
    )