from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from accounts.decorators import administrator_required
from .forms import BranchForm
from .models import Branch

BRANCHES_PER_PAGE = 10


def _clean_query(raw):
    source = QueryDict(raw or "")
    cleaned = QueryDict(mutable=True)

    search = source.get("q", "").strip()
    page = source.get("page", "").strip()

    if search:
        cleaned["q"] = search
    if page.isdigit():
        cleaned["page"] = page

    return cleaned.urlencode()


def _redirect_to_list(request):
    url = reverse("branches:branch_list")
    query = _clean_query(request.POST.get("next_query", ""))

    if query:
        url = f"{url}?{query}"

    return redirect(url)


def _branch_context(request, form, open_modal=False, editing_branch=None):
    search = request.GET.get("q", "").strip()

    stats = Branch.objects.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=Q(is_active=True)),
    )

    queryset = Branch.objects.order_by("pk")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(location__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
        )

    paginator = Paginator(queryset, BRANCHES_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    page_items = [
        None if number == paginator.ELLIPSIS else number
        for number in paginator.get_elided_page_range(
            page_obj.number, on_each_side=1, on_ends=1
        )
    ]

    current_query = _clean_query(
        request.GET.urlencode() or request.POST.get("next_query", "")
    )

    return {
        "branches": page_obj,
        "page_obj": page_obj,
        "page_items": page_items,
        "search_query": search,
        "current_query": current_query,
        "form": form,
        "editing_branch": editing_branch,
        "open_modal": open_modal,
        "total_branches": stats["total"],
        "active_branches": stats["active"],
        "inactive_branches": stats["total"] - stats["active"],
    }


@administrator_required
def branch_list(request):
    return render(
        request,
        "branches/branch_list.html",
        _branch_context(request, BranchForm()),
    )


@administrator_required
@require_POST
def branch_save(request, pk=None):
    branch = get_object_or_404(Branch, pk=pk) if pk is not None else None
    form = BranchForm(request.POST, instance=branch)

    if form.is_valid():
        saved = form.save()
        action = "updated" if pk is not None else "added"
        messages.success(request, f'Branch "{saved.name}" {action} successfully.')
        return _redirect_to_list(request)

    editing_branch = Branch.objects.filter(pk=pk).first() if pk is not None else None

    return render(
        request,
        "branches/branch_list.html",
        _branch_context(request, form, open_modal=True, editing_branch=editing_branch),
    )


@administrator_required
@require_POST
def branch_toggle_status(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    branch.is_active = not branch.is_active
    branch.save(update_fields=["is_active", "updated_at"])

    status = "activated" if branch.is_active else "deactivated"
    messages.success(request, f'Branch "{branch.name}" {status} successfully.')

    return _redirect_to_list(request)
