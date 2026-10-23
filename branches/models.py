from django.db import models

from .utils import to_title_case


class Branch(models.Model):
    name = models.CharField(max_length=150, unique=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Branch"
        verbose_name_plural = "Branches"

    def save(self, *args, **kwargs):
        self.name = to_title_case(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BranchScopedQuerySet(models.QuerySet):
    def for_branch(self, branch):
        return self.filter(branch=branch)

    def for_branches(self, branches):
        return self.filter(branch__in=branches)


class BranchScopedModel(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    objects = BranchScopedQuerySet.as_manager()

    class Meta:
        abstract = True
