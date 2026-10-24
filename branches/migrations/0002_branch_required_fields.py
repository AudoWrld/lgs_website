from django.db import migrations, models


def backfill_existing_branches(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    for branch in Branch.objects.all():
        changed = False
        if not branch.location:
            branch.location = "Not specified"
            changed = True
        if not branch.phone:
            branch.phone = "+255 000 000 000"
            changed = True
        if not branch.email:
            branch.email = "branch@example.com"
            changed = True
        if changed:
            branch.save(update_fields=["location", "phone", "email"])


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_existing_branches, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="branch",
            name="email",
            field=models.EmailField(max_length=254),
        ),
        migrations.AlterField(
            model_name="branch",
            name="location",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="branch",
            name="phone",
            field=models.CharField(max_length=20),
        ),
    ]