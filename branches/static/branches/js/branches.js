document.addEventListener("DOMContentLoaded", function () {
  var page = document.querySelector(".branch-page");
  var ADD_URL = page.dataset.addUrl;
  var OPEN_MODAL = page.dataset.openModal === "true";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var TZ_NATIONAL = /^(?:(?:6[1-9]|7[1-8])\d{7}|2\d{8})$/;
  var PHONE_MESSAGE =
    "Enter a valid Tanzanian number, e.g. +255 712 345 678 or 0712 345 678.";

  var branchModal = document.getElementById("branchModal");
  var detailsModal = document.getElementById("branchDetailsModal");
  var branchForm = document.getElementById("branchForm");
  var modalTitle = document.getElementById("branchModalTitle");
  var submitButton = document.getElementById("branchSubmitButton");

  var confirmModal = document.getElementById("confirmModal");
  var confirmTitleText = document.getElementById("confirmTitleText");
  var confirmMessage = document.getElementById("confirmMessage");
  var confirmAcceptButton = document.getElementById("confirmAcceptButton");
  var pendingForm = null;

  var selectedBranchId = null;

  function icon(name, extraClass) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "br-icon" + (extraClass ? " " + extraClass : ""));
    var use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function setContent(element, iconName, label, iconClass) {
    element.textContent = "";
    element.appendChild(icon(iconName, iconClass));
    element.appendChild(document.createTextNode(" " + label));
  }

  function setText(id, value) {
    document.getElementById(id).textContent =
      value && value.trim() ? value : "Not provided";
  }

  function clearErrors() {
    branchForm
      .querySelectorAll(".field-error-msg, .form-error-alert")
      .forEach(function (element) {
        element.remove();
      });
    branchForm.querySelectorAll(".is-invalid").forEach(function (element) {
      element.classList.remove("is-invalid");
    });
  }

  function setFieldValue(name, value) {
    branchForm.querySelector('[name="' + name + '"]').value = value || "";
  }

  function showFieldError(input, message) {
    input.classList.add("is-invalid");
    var error = document.createElement("div");
    error.className = "field-error-msg";
    error.textContent = message;
    input.insertAdjacentElement("afterend", error);
  }

  function isValidTzPhone(raw) {
    var value = raw.trim();

    if (!value) {
      return true;
    }

    if (/[^\d+\s\-().]/.test(value)) {
      return false;
    }

    var digits = value.replace(/[\s\-().]/g, "");
    var national;

    if (digits.indexOf("+255") === 0) {
      national = digits.slice(4);
    } else if (digits.indexOf("00255") === 0) {
      national = digits.slice(5);
    } else if (digits.indexOf("255") === 0) {
      national = digits.slice(3);
    } else if (digits.indexOf("0") === 0) {
      national = digits.slice(1);
    } else {
      return false;
    }

    return TZ_NATIONAL.test(national);
  }

  function openDialog(dialog) {
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function openAddModal() {
    clearErrors();

    ["name", "location", "phone", "email"].forEach(function (field) {
      setFieldValue(field, "");
    });

    branchForm.action = ADD_URL;
    selectedBranchId = null;

    setContent(modalTitle, "plus", "Add New Branch", "br-icon-lg");
    setContent(submitButton, "save", "Save Branch");

    openDialog(branchModal);
  }

  function openEditModal(button) {
    clearErrors();

    selectedBranchId = button.dataset.id;
    branchForm.action = button.dataset.editUrl;

    setFieldValue("name", button.dataset.name);
    setFieldValue("location", button.dataset.location);
    setFieldValue("phone", button.dataset.phone);
    setFieldValue("email", button.dataset.email);

    setContent(modalTitle, "edit", "Edit Branch", "br-icon-lg");
    setContent(submitButton, "check", "Update Branch");

    openDialog(branchModal);
  }

  function openDetailsModal(button) {
    selectedBranchId = button.dataset.id;

    setText("detailId", button.dataset.id);
    setText("detailName", button.dataset.name);
    setText("detailLocation", button.dataset.location);
    setText("detailPhone", button.dataset.phone);
    setText("detailEmail", button.dataset.email);
    setText("detailCreated", button.dataset.created);
    setText("detailUpdated", button.dataset.updated);

    var status = button.dataset.status || "Inactive";
    var isActive = status === "Active";
    var statusElement = document.getElementById("detailStatus");

    statusElement.textContent = "";

    var badge = document.createElement("span");
    badge.className =
      "status-pill " + (isActive ? "status-active" : "status-inactive");
    badge.appendChild(
      icon(isActive ? "check-circle" : "x-circle", "br-icon-sm"),
    );
    badge.appendChild(document.createTextNode(status));
    statusElement.appendChild(badge);

    openDialog(detailsModal);
  }

  document
    .getElementById("addBranchButton")
    .addEventListener("click", openAddModal);

  document.querySelectorAll(".js-add-trigger").forEach(function (button) {
    button.addEventListener("click", openAddModal);
  });

  document.querySelectorAll(".js-edit").forEach(function (button) {
    button.addEventListener("click", function () {
      openEditModal(button);
    });
  });

  document.querySelectorAll(".js-view").forEach(function (button) {
    button.addEventListener("click", function () {
      openDetailsModal(button);
    });
  });

  document
    .getElementById("detailEditButton")
    .addEventListener("click", function () {
      if (!selectedBranchId) {
        return;
      }

      var editButton = document.querySelector(
        '.js-edit[data-id="' + selectedBranchId + '"]',
      );

      if (!editButton) {
        return;
      }

      detailsModal.close();
      openEditModal(editButton);
    });

  [branchModal, detailsModal, confirmModal].forEach(function (dialog) {
    dialog.querySelectorAll("[data-close]").forEach(function (button) {
      button.addEventListener("click", function () {
        dialog.close();
      });
    });

    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });

  branchForm.addEventListener("submit", function (event) {
    clearErrors();

    var nameInput = branchForm.querySelector('[name="name"]');
    var phoneInput = branchForm.querySelector('[name="phone"]');
    var valid = true;

    if (!nameInput.value.trim()) {
      showFieldError(nameInput, "This field is required.");
      valid = false;
    }

    if (!isValidTzPhone(phoneInput.value)) {
      showFieldError(phoneInput, PHONE_MESSAGE);
      valid = false;
    }

    if (!valid) {
      event.preventDefault();
      var firstInvalid = branchForm.querySelector(".is-invalid");
      if (firstInvalid) {
        firstInvalid.focus();
      }
    }
  });

  document.querySelectorAll(".js-toggle-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var button = form.querySelector("button[type='submit']");
      var branchName = form
        .closest("tr")
        .querySelector(".branch-name")
        .textContent.trim();
      var deactivating = button.dataset.action === "deactivate";

      pendingForm = form;

      confirmTitleText.textContent = deactivating
        ? "Deactivate branch"
        : "Activate branch";
      confirmMessage.textContent =
        "Are you sure you want to " +
        (deactivating ? "deactivate" : "activate") +
        ' "' +
        branchName +
        '"?';
      confirmAcceptButton.textContent = deactivating
        ? "Deactivate"
        : "Activate";
      confirmAcceptButton.classList.toggle("br-btn-danger", deactivating);
      confirmAcceptButton.classList.toggle("br-btn-primary", !deactivating);

      openDialog(confirmModal);
    });
  });

  confirmAcceptButton.addEventListener("click", function () {
    if (!pendingForm) {
      return;
    }

    var form = pendingForm;
    pendingForm = null;
    confirmAcceptButton.disabled = true;
    form.submit();
  });

  confirmModal.addEventListener("close", function () {
    pendingForm = null;
  });

  if (OPEN_MODAL) {
    openDialog(branchModal);
  }
});
