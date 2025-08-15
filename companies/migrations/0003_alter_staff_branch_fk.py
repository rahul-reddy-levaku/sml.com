from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0002_prep_staff_branch'),
    ]
    operations = [
        migrations.AlterField(
            model_name='staff',
            name='branch',
            field=models.ForeignKey(
                to='companies.branch',
                to_field='code',
                db_column='branch',
                related_name='staff',
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
            ),
        ),
    ]
