import re

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import administrator_required
from accounts.models import Client, ClientEditLog, EmployeeActivity, User

from .views import _paginate, _resolve_branches, get_selected_branch

PHONE_PATTERN = re.compile(r"^\+?[0-9\s\-]{7,20}$")
EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_/]{2,30}$")
TEMP_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

EMPLOYEE_CREATORS = {
    User.RECEPTION: "create_reception",
    User.CHEMIST: "create_chemist",
    User.QUANTITY_CONTROL: "create_quantity_control",
    User.ACCOUNTANT: "create_accountant",
    User.ADMINISTRATOR: "create_administrator",
}


def _split_name(full_name):
    parts = full_name.split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def _display_name(user):
    profile = getattr(user, "client_profile", None)
    if profile is not None and profile.client_name:
        return profile.client_name
    return user.get_full_name() or user.email


def _json_ok(request, message, flash=True, **extra):
    if flash:
        messages.success(request, message)
    payload = {"ok": True, "message": message}
    payload.update(extra)
    return JsonResponse(payload)


def _json_error(message, status):
    return JsonResponse(
        {"ok": False, "error": message, "message": message}, status=status
    )


def _role_choices(request, instance=None):
    roles = [
        (User.QUANTITY_CONTROL, "Quality Control"),
        (User.CHEMIST, "Chemist"),
        (User.RECEPTION, "Reception"),
        (User.ACCOUNTANT, "Accountant"),
    ]
    if request.user.is_superuser or (
        instance is not None and instance.role == User.ADMINISTRATOR
    ):
        roles.insert(0, (User.ADMINISTRATOR, "Administrator"))
    return roles


def _read_form(request):
    post = request.POST
    return {
        "full_name": " ".join(post.get("full_name", "").split()),
        "employee_id": post.get("employee_id", "").strip(),
        "whatsapp_number": post.get("whatsapp_number", "").strip(),
        "email": post.get("email", "").strip().lower(),
        "password": post.get("password", ""),
        "branch_id": post.get("branch_id", "").strip(),
        "role": post.get("role", "").strip(),
        "client_type": post.get("client_type", "").strip(),
        "contact_person": " ".join(post.get("contact_person", "").split()),
    }


def _validate_form(data, branch_ids, kind, instance=None, allowed_roles=()):
    errors = {}

    if not data["full_name"]:
        errors["full_name"] = "Full name is required."
    elif len(data["full_name"]) > 200:
        errors["full_name"] = "Full name is too long."

    if not data["whatsapp_number"]:
        errors["whatsapp_number"] = "Phone / WhatsApp number is required."
    elif not PHONE_PATTERN.match(data["whatsapp_number"]):
        errors["whatsapp_number"] = "Enter a valid phone number."

    if not data["email"]:
        errors["email"] = "Email address is required."
    else:
        try:
            validate_email(data["email"])
        except ValidationError:
            errors["email"] = "Enter a valid email address."
        else:
            duplicates = User.objects.filter(email__iexact=data["email"])
            if instance is not None:
                duplicates = duplicates.exclude(pk=instance.pk)
            if duplicates.exists():
                errors["email"] = "A user with this email already exists."

    if instance is None and not data["password"]:
        errors["password"] = "Password is required."
    elif data["password"]:
        try:
            validate_password(data["password"], user=instance)
        except ValidationError as exc:
            errors["password"] = " ".join(exc.messages)

    try:
        branch_id = int(data["branch_id"])
    except (TypeError, ValueError):
        branch_id = None
    if branch_id is None or branch_id not in branch_ids:
        errors["branch_id"] = "Select a valid branch."

    if kind == "employee":
        if data["role"] not in allowed_roles:
            errors["role"] = "Select a valid role."
        if data["employee_id"]:
            if not EMPLOYEE_ID_PATTERN.match(data["employee_id"]):
                errors["employee_id"] = "Use 2-30 letters, numbers, dashes or slashes."
            else:
                duplicates = User.objects.filter(
                    employee_id__iexact=data["employee_id"]
                )
                if instance is not None:
                    duplicates = duplicates.exclude(pk=instance.pk)
                if duplicates.exists():
                    errors["employee_id"] = "This employee ID is already in use."
    else:
        valid_types = {value for value, _ in Client.CLIENT_TYPE_CHOICES}
        if data["client_type"] not in valid_types:
            errors["client_type"] = "Select a valid client type."
        if not data["contact_person"]:
            errors["contact_person"] = "Contact person is required."
        elif len(data["contact_person"]) > 150:
            errors["contact_person"] = "Contact person name is too long."

    return errors, branch_id


def _form_context(request, branches, data, errors, **extra):
    context = {
        "branches": branches,
        "form": data,
        "errors": errors,
        "selected_branch": get_selected_branch(request),
    }
    context.update(extra)
    return context


def _get_target(request, user_id, roles):
    target = (
        User.objects.filter(
            pk=user_id,
            role__in=roles,
            is_deleted=False,
            branch__in=request.accessible_branches,
        )
        .select_related("branch", "client_profile")
        .first()
    )
    if target is None:
        raise Http404("User not found.")
    return target


def _guard_admin_target(request, target):
    if target.pk == request.user.pk:
        return
    if (target.role == User.ADMINISTRATOR or target.is_superuser) and not (
        request.user.is_superuser
    ):
        raise PermissionDenied("Only a superuser may manage Administrator accounts.")


def _revoke_sessions(user):
    user_key = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == user_key:
            session.delete()


def _log_activity(employee, actor, action, detail=""):
    EmployeeActivity.objects.create(
        employee=employee,
        actor=actor,
        action=action,
        detail=detail,
    )


def _soft_delete_client(user):
    with transaction.atomic():
        profile = getattr(user, "client_profile", None)
        if profile is not None:
            profile.edit_logs.all().delete()
            profile.client_name = "Deleted client"
            profile.contact_person = ""
            profile.email = ""
            profile.whatsapp_number = ""
            profile.slug = f"deleted-client-{profile.pk}"
            profile.registered_by = None
            profile.is_active = False
            profile.save()

        user.email = f"deleted-{user.pk}@deleted.invalid"
        user.first_name = ""
        user.last_name = ""
        user.whatsapp_number = ""
        user.initial_temp_password = None
        user.must_change_password = False
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.is_deleted = True
        user.deleted_at = timezone.now()
        user.set_unusable_password()
        user.save()
        user.groups.clear()
        user.user_permissions.clear()

    _revoke_sessions(user)


@administrator_required
@require_http_methods(["GET", "POST"])
def add_client(request):
    branches, _, selected_id = _resolve_branches(request)
    branch_ids = {branch["id"] for branch in branches}
    client_types = Client.CLIENT_TYPE_CHOICES

    if request.method == "POST":
        data = _read_form(request)
        errors, branch_id = _validate_form(data, branch_ids, "client")

        if not errors:
            branch = request.accessible_branches.get(pk=branch_id)
            first_name, last_name = _split_name(data["full_name"])
            with transaction.atomic():
                user = User.objects.create_customer(
                    email=data["email"],
                    password=data["password"],
                    created_by=request.user,
                    branch=branch,
                    first_name=first_name,
                    last_name=last_name,
                    whatsapp_number=data["whatsapp_number"],
                    initial_temp_password=data["password"],
                )
                Client.objects.create(
                    portal_user=user,
                    client_type=data["client_type"],
                    client_name=data["full_name"],
                    contact_person=data["contact_person"],
                    email=data["email"],
                    whatsapp_number=data["whatsapp_number"],
                )
            messages.success(
                request, f"Client {data['full_name']} was added successfully."
            )
            return redirect("administrator:client_list")

        data["password"] = ""
        messages.error(request, "Please correct the errors below.")
        return render(
            request,
            "administrator/user_management/add_client.html",
            _form_context(request, branches, data, errors, client_types=client_types),
        )

    data = {
        "full_name": "",
        "whatsapp_number": "",
        "email": "",
        "password": "",
        "branch_id": str(selected_id or ""),
        "client_type": "",
        "contact_person": "",
    }
    return render(
        request,
        "administrator/user_management/add_client.html",
        _form_context(request, branches, data, {}, client_types=client_types),
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def add_employee(request):
    branches, _, selected_id = _resolve_branches(request)
    branch_ids = {branch["id"] for branch in branches}
    roles = _role_choices(request)
    allowed_roles = {value for value, _ in roles}

    if request.method == "POST":
        data = _read_form(request)
        errors, branch_id = _validate_form(
            data, branch_ids, "employee", allowed_roles=allowed_roles
        )

        if not errors:
            branch = request.accessible_branches.get(pk=branch_id)
            first_name, last_name = _split_name(data["full_name"])
            creator = getattr(User.objects, EMPLOYEE_CREATORS[data["role"]])
            try:
                with transaction.atomic():
                    employee = creator(
                        email=data["email"],
                        password=data["password"],
                        created_by=request.user,
                        branch=branch,
                        first_name=first_name,
                        last_name=last_name,
                        whatsapp_number=data["whatsapp_number"],
                        employee_id=data["employee_id"] or None,
                    )
                    _log_activity(
                        employee,
                        request.user,
                        EmployeeActivity.CREATED,
                        f"Role: {employee.get_role_display()}; Branch: {branch.name}",
                    )
            except PermissionDenied as exc:
                errors["role"] = str(exc)
            else:
                messages.success(
                    request, f"Employee {data['full_name']} was added successfully."
                )
                return redirect("administrator:employee_list")

        data["password"] = ""
        messages.error(request, "Please correct the errors below.")
        return render(
            request,
            "administrator/user_management/add_employee.html",
            _form_context(request, branches, data, errors, roles=roles),
        )

    data = {
        "full_name": "",
        "employee_id": "",
        "whatsapp_number": "",
        "email": "",
        "password": "",
        "branch_id": str(selected_id or ""),
        "role": "",
    }
    return render(
        request,
        "administrator/user_management/add_employee.html",
        _form_context(request, branches, data, {}, roles=roles),
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def edit_client(request, user_id):
    branches, _, _ = _resolve_branches(request)
    branch_ids = {branch["id"] for branch in branches}
    client_types = Client.CLIENT_TYPE_CHOICES
    target = _get_target(request, user_id, (User.CUSTOMER,))
    profile = getattr(target, "client_profile", None)

    if request.method == "POST":
        data = _read_form(request)
        errors, branch_id = _validate_form(data, branch_ids, "client", instance=target)

        if not errors:
            branch = request.accessible_branches.get(pk=branch_id)
            first_name, last_name = _split_name(data["full_name"])
            with transaction.atomic():
                if profile is None:
                    profile = Client(portal_user=target)
                else:
                    ClientEditLog.objects.create(
                        client=profile,
                        edited_by=None,
                        previous_client_type=profile.client_type,
                        previous_client_name=profile.client_name,
                        previous_contact_person=profile.contact_person,
                        previous_email=profile.email,
                        previous_whatsapp_number=profile.whatsapp_number,
                    )

                profile.client_type = data["client_type"]
                profile.client_name = data["full_name"]
                profile.contact_person = data["contact_person"]
                profile.email = data["email"]
                profile.whatsapp_number = data["whatsapp_number"]
                profile.save()

                target.first_name = first_name
                target.last_name = last_name
                target.email = data["email"]
                target.whatsapp_number = data["whatsapp_number"]
                target.branch = branch
                if data["password"]:
                    target.set_password(data["password"])
                    target.must_change_password = True
                    target.initial_temp_password = data["password"]
                target.save()

            if data["password"]:
                _revoke_sessions(target)

            messages.success(
                request, f"Client {data['full_name']} was updated successfully."
            )
            return redirect("administrator:client_list")

        data["password"] = ""
        messages.error(request, "Please correct the errors below.")
        return render(
            request,
            "administrator/user_management/edit_client.html",
            _form_context(
                request,
                branches,
                data,
                errors,
                client_types=client_types,
                user_id=user_id,
                target_user=target,
            ),
        )

    data = {
        "full_name": profile.client_name if profile else target.get_full_name(),
        "whatsapp_number": target.whatsapp_number,
        "email": target.email,
        "password": "",
        "branch_id": str(target.branch_id),
        "client_type": profile.client_type if profile else "",
        "contact_person": profile.contact_person if profile else "",
    }
    return render(
        request,
        "administrator/user_management/edit_client.html",
        _form_context(
            request,
            branches,
            data,
            {},
            client_types=client_types,
            user_id=user_id,
            target_user=target,
        ),
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def edit_employee(request, user_id):
    branches, _, _ = _resolve_branches(request)
    branch_ids = {branch["id"] for branch in branches}
    target = _get_target(request, user_id, User.STAFF_ROLES)
    _guard_admin_target(request, target)

    role_locked = target.pk == request.user.pk or target.is_superuser
    roles = _role_choices(request, target)
    allowed_roles = {value for value, _ in roles}

    if request.method == "POST":
        data = _read_form(request)
        if role_locked:
            data["role"] = target.role
            allowed_roles = allowed_roles | {target.role}
        errors, branch_id = _validate_form(
            data, branch_ids, "employee", instance=target, allowed_roles=allowed_roles
        )

        if not errors:
            branch = request.accessible_branches.get(pk=branch_id)
            first_name, last_name = _split_name(data["full_name"])
            old_role = target.role
            old_branch = target.branch
            role_changed = not role_locked and data["role"] != old_role
            branch_changed = branch.pk != old_branch.pk

            with transaction.atomic():
                target.first_name = first_name
                target.last_name = last_name
                target.email = data["email"]
                target.employee_id = data["employee_id"] or None
                target.whatsapp_number = data["whatsapp_number"]
                target.branch = branch
                if role_changed:
                    target.role = data["role"]
                    target.is_staff = data["role"] == User.ADMINISTRATOR
                if data["password"]:
                    target.set_password(data["password"])
                    if target.pk != request.user.pk:
                        target.must_change_password = True
                target.save()

                _log_activity(target, request.user, EmployeeActivity.UPDATED)
                if role_changed:
                    _log_activity(
                        target,
                        request.user,
                        EmployeeActivity.ROLE_CHANGED,
                        f"{old_role} -> {target.role}",
                    )
                if branch_changed:
                    _log_activity(
                        target,
                        request.user,
                        EmployeeActivity.BRANCH_TRANSFERRED,
                        f"{old_branch.name} -> {branch.name}",
                    )
                if data["password"]:
                    _log_activity(target, request.user, EmployeeActivity.PASSWORD_RESET)

            if target.pk == request.user.pk:
                if data["password"]:
                    update_session_auth_hash(request, target)
            elif data["password"] or role_changed:
                _revoke_sessions(target)

            name = _display_name(target)
            if role_changed:
                messages.success(
                    request,
                    f"Employee {name} was updated and their role changed to {target.get_role_display()}.",
                )
            else:
                messages.success(request, f"Employee {name} was updated successfully.")
            return redirect("administrator:employee_list")

        data["password"] = ""
        messages.error(request, "Please correct the errors below.")
        return render(
            request,
            "administrator/user_management/edit_employee.html",
            _form_context(
                request,
                branches,
                data,
                errors,
                roles=roles,
                role_locked=role_locked,
                user_id=user_id,
                target_user=target,
            ),
        )

    data = {
        "full_name": target.get_full_name(),
        "employee_id": target.employee_id or "",
        "whatsapp_number": target.whatsapp_number,
        "email": target.email,
        "password": "",
        "branch_id": str(target.branch_id),
        "role": target.role,
    }
    return render(
        request,
        "administrator/user_management/edit_employee.html",
        _form_context(
            request,
            branches,
            data,
            {},
            roles=roles,
            role_locked=role_locked,
            user_id=user_id,
            target_user=target,
        ),
    )


@administrator_required
@require_POST
def delete_user(request, user_id):
    branch = get_selected_branch(request)
    if branch is None:
        return _json_error("No branch selected.", 400)

    try:
        user = User.objects.select_related("client_profile").get(
            pk=user_id, branch=branch, role=User.CUSTOMER, is_deleted=False
        )
    except User.DoesNotExist:
        return _json_error("Client not found.", 404)

    name = _display_name(user)
    _soft_delete_client(user)
    return _json_ok(request, f"Client {name} was deleted.", user_id=user_id)


@administrator_required
@require_POST
def toggle_employee(request, user_id):
    try:
        target = _get_target(request, user_id, User.STAFF_ROLES)
        _guard_admin_target(request, target)
    except Http404:
        return _json_error("Employee not found.", 404)
    except PermissionDenied as exc:
        return _json_error(str(exc), 403)

    if target.pk == request.user.pk:
        return _json_error("You cannot deactivate your own account.", 400)

    with transaction.atomic():
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        _log_activity(
            target,
            request.user,
            (
                EmployeeActivity.ACTIVATED
                if target.is_active
                else EmployeeActivity.DEACTIVATED
            ),
        )

    if not target.is_active:
        _revoke_sessions(target)

    state = "activated" if target.is_active else "deactivated"
    return _json_ok(
        request,
        f"Employee {_display_name(target)} was {state}.",
        user_id=user_id,
        is_active=target.is_active,
    )


@administrator_required
@require_POST
def reset_employee_password(request, user_id):
    try:
        target = _get_target(request, user_id, User.STAFF_ROLES)
        _guard_admin_target(request, target)
    except Http404:
        return _json_error("Employee not found.", 404)
    except PermissionDenied as exc:
        return _json_error(str(exc), 403)

    if target.pk == request.user.pk:
        return _json_error("Use the edit page to change your own password.", 400)

    temp_password = get_random_string(12, TEMP_PASSWORD_ALPHABET)

    with transaction.atomic():
        target.set_password(temp_password)
        target.must_change_password = True
        target.save(update_fields=["password", "must_change_password"])
        _log_activity(target, request.user, EmployeeActivity.PASSWORD_RESET)

    _revoke_sessions(target)

    return _json_ok(
        request,
        f"Password for {_display_name(target)} was reset.",
        flash=False,
        user_id=user_id,
        temp_password=temp_password,
    )


@administrator_required
@require_POST
def reset_client_password(request, user_id):
    try:
        target = _get_target(request, user_id, (User.CUSTOMER,))
    except Http404:
        return _json_error("Client not found.", 404)

    temp_password = get_random_string(12, TEMP_PASSWORD_ALPHABET)

    with transaction.atomic():
        target.set_password(temp_password)
        target.must_change_password = True
        target.initial_temp_password = temp_password
        target.save(
            update_fields=["password", "must_change_password", "initial_temp_password"]
        )

    _revoke_sessions(target)

    return _json_ok(
        request,
        f"Password for {_display_name(target)} was reset.",
        flash=False,
        user_id=user_id,
        temp_password=temp_password,
    )


@administrator_required
def employee_activity(request, user_id):
    target = _get_target(request, user_id, User.STAFF_ROLES)
    _guard_admin_target(request, target)

    logs = target.activity_log.select_related("actor")
    page_obj, page_items = _paginate(request, logs)

    return render(
        request,
        "administrator/user_management/employee_activity.html",
        {
            "selected_branch": get_selected_branch(request),
            "target_user": target,
            "page_obj": page_obj,
            "page_items": page_items,
            "logs": page_obj.object_list,
        },
    )
