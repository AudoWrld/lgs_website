from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import accountant_required
from commercial.models import CommercialInvoice
from commercial.pdf import render_invoice_pdf
from commercial.services import create_invoice, lookup


@accountant_required
def commercial_invoice_create(request):
    context = {"reference": ""}

    if request.method == "POST":
        if request.POST.get("action") == "confirm":
            client_id = request.POST.get("client_id", "")
            raw_ids = request.POST.getlist("submission_ids")
            try:
                invoice = create_invoice(
                    int(client_id), [int(pk) for pk in raw_ids], request.user
                )
            except (ValidationError, ValueError) as exc:
                text = (
                    "; ".join(exc.messages)
                    if isinstance(exc, ValidationError)
                    else "Invalid selection."
                )
                messages.error(request, text)
                return redirect("accountant:commercial_invoice_create")
            messages.success(
                request, f"Commercial Invoice {invoice.invoice_number} generated."
            )
            return redirect("accountant:commercial_invoice_list")

        reference = request.POST.get("reference", "").strip()
        context["reference"] = reference
        if not reference:
            messages.error(request, "Enter a Reference Number.")
        else:
            result = lookup(reference)
            if result is None:
                messages.error(request, f"Reference {reference} was not found.")
            else:
                context.update(result)

    return render(request, "accountant/commercial_invoice_form.html", context)


@accountant_required
def commercial_invoice_list(request):
    query = request.GET.get("q", "").strip()
    invoices = CommercialInvoice.objects.select_related("client").prefetch_related(
        "references__submission"
    )
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query)
            | Q(client__client_name__icontains=query)
            | Q(references__submission__reference__icontains=query)
        ).distinct()
    return render(
        request,
        "accountant/commercial_invoice_list.html",
        {"invoices": invoices, "query": query},
    )


@accountant_required
def commercial_invoice_pdf(request, pk):
    invoice = get_object_or_404(
        CommercialInvoice.objects.select_related("client").prefetch_related(
            "lines", "references__submission"
        ),
        pk=pk,
    )
    response = HttpResponse(render_invoice_pdf(invoice), content_type="application/pdf")
    name = invoice.invoice_number.replace("/", "-")
    response["Content-Disposition"] = f'attachment; filename="commercial-invoice-{name}.pdf"'
    return response