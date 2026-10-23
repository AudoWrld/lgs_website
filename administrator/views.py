from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import administrator_required
from accounts.models import User
from coa.models import COA
from expenses.models import Expense
from payments.models import Payment, PaymentTransaction

SESSION_KEY = "admin_branch_id"
MONEY = DecimalField(max_digits=14, decimal_places=2)
CHART_DAYS = 30


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


def _dashboard_stats(branch):
    zero = Decimal("0.00")
    today = timezone.localdate()

    stats = {
        "date": today,
        "expenses_total": zero,
        "coas_generated": 0,
        "submissions_count": 0,
        "revenue": zero,
        "paid": zero,
        "unpaid_balance": zero,
        "unpaid_count": 0,
    }

    if branch is None:
        return stats

    stats["expenses_total"] = (
        Expense.objects.filter(branch=branch, expense_date=today).aggregate(
            total=Sum("amount")
        )["total"]
        or zero
    )

    stats["coas_generated"] = COA.objects.filter(
        submission__branch=branch, created_at__date=today
    ).count()

    payments = Payment.objects.filter(
        branch=branch,
        submission__is_submitted=True,
        submission__receiving_date=today,
    ).annotate(
        net=ExpressionWrapper(F("gross_amount") - F("discount"), output_field=MONEY),
        balance=ExpressionWrapper(
            F("gross_amount") - F("discount") - F("total_amount_paid"),
            output_field=MONEY,
        ),
    )

    totals = payments.aggregate(
        count=Count("pk"),
        revenue=Sum("net"),
        paid=Sum("total_amount_paid"),
    )
    stats["submissions_count"] = totals["count"] or 0
    stats["revenue"] = totals["revenue"] or zero
    stats["paid"] = totals["paid"] or zero

    unpaid = payments.filter(balance__gt=0).aggregate(
        total=Sum("balance"), count=Count("pk")
    )
    stats["unpaid_balance"] = unpaid["total"] or zero
    stats["unpaid_count"] = unpaid["count"] or 0

    return stats


def _chart_data(branch):
    today = timezone.localdate()
    start = today - timedelta(days=CHART_DAYS - 1)
    days = [start + timedelta(days=i) for i in range(CHART_DAYS)]

    data = {
        "labels": [day.strftime("%d %b") for day in days],
        "billed": [0.0] * CHART_DAYS,
        "collected": [0.0] * CHART_DAYS,
        "methods": {"labels": [], "values": []},
    }

    if branch is None:
        return data

    index = {day: i for i, day in enumerate(days)}

    billed_rows = (
        Payment.objects.filter(
            branch=branch,
            submission__is_submitted=True,
            submission__receiving_date__gte=start,
            submission__receiving_date__lte=today,
        )
        .values("submission__receiving_date")
        .annotate(
            total=Sum(
                ExpressionWrapper(F("gross_amount") - F("discount"), output_field=MONEY)
            )
        )
        .order_by()
    )
    for row in billed_rows:
        position = index.get(row["submission__receiving_date"])
        if position is not None:
            data["billed"][position] = float(row["total"] or 0)

    transactions = PaymentTransaction.objects.filter(
        payment__branch=branch, created_at__date__gte=start
    )

    collected_rows = (
        transactions.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("amount"))
        .order_by()
    )
    for row in collected_rows:
        position = index.get(row["day"])
        if position is not None:
            data["collected"][position] = float(row["total"] or 0)

    method_names = dict(Payment.METHOD_CHOICES)
    method_rows = (
        transactions.values("payment_method")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    for row in method_rows:
        data["methods"]["labels"].append(
            method_names.get(row["payment_method"], row["payment_method"])
        )
        data["methods"]["values"].append(float(row["total"] or 0))

    return data


def _top_submissions(branch):
    if branch is None:
        return []
    return list(
        Payment.objects.filter(branch=branch, submission__is_submitted=True)
        .select_related("submission__client")
        .annotate(sample_count=Count("submission__samples"))
        .order_by("-submission__created_at")[:10]
    )


@administrator_required
def admin_dashboard(request):
    branch = get_selected_branch(request)
    chart_data = _chart_data(branch)
    return render(
        request,
        "administrator/dashboard.html",
        {
            "selected_branch": branch,
            "stats": _dashboard_stats(branch),
            "chart_data": chart_data,
            "has_method_data": bool(chart_data["methods"]["values"]),
            "top_submissions": _top_submissions(branch),
            "chart_days": CHART_DAYS,
        },
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
            User.objects.filter(role=User.CUSTOMER, branch=branch, is_deleted=False)
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


def profile_view(request):
    return render(request, "administrator/profile_view.html")
